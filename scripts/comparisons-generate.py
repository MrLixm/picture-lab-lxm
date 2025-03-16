import abc
import argparse
import dataclasses
import json
import logging
import subprocess
import time
import shutil
import sys
from pathlib import Path

import PyOpenColorIO as ocio

import lxmpicturelab
from lxmpicturelab.browse import WORKBENCH_DIR
from lxmpicturelab.browse import get_imagery_asset
from lxmpicturelab.browse import get_imagery_set
from lxmpicturelab.download import download_file
from lxmpicturelab.download import download_file_advanced
from lxmpicturelab.download import extract_zip
from lxmpicturelab.renderer import OcioConfigRenderer
from lxmpicturelab.oiiotoolio import oiiotool_export
from lxmpicturelab.oiiotoolio import oiiotool_generate_expo_bands
from lxmpicturelab.oiiotoolio import oiiotool_auto_mosaic

LOGGER = logging.getLogger(__name__)

OIIOTOOL = Path(shutil.which("oiiotool"))
assert OIIOTOOL.exists()

WORKBENCH_DIR.mkdir(exist_ok=True)
WORK_DIR = WORKBENCH_DIR / "comparisons-generate"
WORK_DIR.mkdir(exist_ok=True)


class BaseGenerator(abc.ABC):
    """
    A method of generating an image with oiiotool.
    """

    @classmethod
    @abc.abstractmethod
    def shortname(cls) -> str:
        pass

    @abc.abstractmethod
    def run(
        self,
        src_path: Path,
        renderer: OcioConfigRenderer,
        target_dir: Path,
    ) -> Path:
        pass


@dataclasses.dataclass
class GeneratorExposureBands(BaseGenerator):
    # 0-1 range, percentage of image width
    band_offset: float = 0.0

    @classmethod
    def shortname(cls):
        return "exposures"

    def _run(
        self,
        src_path: Path,
        dst_path: Path,
        ocio_command: list[str],
        text_left: str,
        text_right: str,
    ):
        command = [str(OIIOTOOL)]
        command += oiiotool_generate_expo_bands(
            src_path=src_path,
            band_number=7,
            band_exposure_offset=2,
            band_width=0.2,
            band_x_offset=self.band_offset,
            band_extra_args=ocio_command,
        )
        command += [
            "--resize:filter=box",
            "0x864",
            "--cut",
            "0,0,{TOP.width},{TOP.height+100}",
            "--text:x=40:y={TOP.height-45}:shadow=0:size=34:color=1,1,1,1:yalign=center",
            text_left,
            "--text:x={TOP.width-40}:y={TOP.height-45}:shadow=0:size=24:color=1,1,1,1:yalign=center:xalign=right",
            text_right,
        ]
        command += oiiotool_export(
            target_path=dst_path,
            # assume dst_path is .jpg
            bitdepth="uint8",
            compression="jpeg:98",
        )
        LOGGER.debug(f"subprocess.run({' '.join(command)})")
        subprocess.run(command)

    def run(
        self,
        src_path: Path,
        renderer: OcioConfigRenderer,
        target_dir: Path,
    ) -> Path:
        look_str = f", look='{renderer.look}'" if renderer.look else ""
        ocio_command = renderer.to_oiiotool_command()
        dst_name = f"{src_path.stem}.exposures.{renderer.filename}.jpg"
        dst_path = target_dir / dst_name
        text_left = f"{src_path.stem} - {renderer.name}"
        text_right = f"(display='{renderer.display}', view='{renderer.view}'{look_str})"
        self._run(
            src_path=src_path,
            dst_path=dst_path,
            ocio_command=ocio_command,
            text_left=text_left,
            text_right=text_right,
        )
        return dst_path


@dataclasses.dataclass
class GeneratorFull(BaseGenerator):
    """
    Render the full size of the image with a legend in a bottom footer.
    """

    max_height: int

    @classmethod
    def shortname(cls):
        return "full"

    def _run(
        self,
        src_path: Path,
        dst_path: Path,
        ocio_command: list[str],
        text_left: tuple[str, str],
        text_right: str,
    ):
        command = [
            str(OIIOTOOL),
            "-i",
            str(src_path),
        ]
        command += ocio_command
        command += ["--ch", "R,G,B"]
        command += [
            "--resize:filter=box",
            f"0x{self.max_height}",
            "--cut",
            "0,0,{TOP.width},{TOP.height+100}",
            "--text:x=40:y={TOP.height-47}:shadow=0:size=34:color=1,1,1,1:yalign=bottom",
            text_left[0],
            "--text:x=40:y={TOP.height-42}:shadow=0:size=24:color=1,1,1,1:yalign=top",
            text_left[1],
            "--text:x={TOP.width-40}:y={TOP.height-45}:shadow=0:size=34:color=1,1,1,1:yalign=center:xalign=right",
            text_right,
        ]
        command += oiiotool_export(
            target_path=dst_path,
            # assume dst_path is .jpg
            bitdepth="uint8",
            compression="jpeg:98",
        )
        LOGGER.debug(f"subprocess.run({' '.join(command)})")
        subprocess.run(command)

    def run(
        self,
        src_path: Path,
        renderer: OcioConfigRenderer,
        target_dir: Path,
    ) -> Path:
        look_str = f", look='{renderer.look}'" if renderer.look else ""
        ocio_command = renderer.to_oiiotool_command()

        dst_name = f"{src_path.stem}.full.{renderer.filename}.jpg"
        dst_path = target_dir / dst_name
        text_left = (
            f"{renderer.name}",
            f"(display='{renderer.display}', view='{renderer.view}'{look_str})",
        )
        text_right = f"{src_path.stem}"
        self._run(
            src_path=src_path,
            dst_path=dst_path,
            ocio_command=ocio_command,
            text_left=text_left,
            text_right=text_right,
        )
        return dst_path


def generate_combine(image_paths: list[Path], dst_path: Path):
    command = [("-i", str(path)) for path in image_paths]
    command = [arg for args in command for arg in args]
    command += oiiotool_auto_mosaic(len(image_paths))
    command += oiiotool_export(
        target_path=dst_path,
        bitdepth="uint8",
        compression="jpeg:98",
    )
    command.insert(0, str(OIIOTOOL))
    LOGGER.debug(f"subprocess.run({' '.join(command)})")
    subprocess.run(command)


@dataclasses.dataclass
class SourceAsset:
    path: Path
    filename: str
    generators: list[BaseGenerator]


def _build_AgX_renderer(work_dir: Path) -> OcioConfigRenderer:
    repo_url = "https://github.com/sobotka/AgX/archive/refs/heads/main.zip"
    if not work_dir.exists():
        work_dir.mkdir()
        repo_path = work_dir / "AgX.zip"
        download_file(repo_url, repo_path)
        extract_zip(repo_path, remove_zip=True)
    config_path = work_dir / "AgX-main" / "config.ocio"
    return OcioConfigRenderer(
        name=f"AgX",
        filename="AgX",
        config_path=config_path,
        srgb_lin="Linear BT.709",
        display="sRGB",
        view="Appearance Punchy",
        reference_url=repo_url,
    )


def _build_AgX_blender_renderer(work_dir: Path) -> OcioConfigRenderer:
    repo_url = "https://projects.blender.org/blender/blender/archive/v4.2.7.zip"
    src_dir = work_dir / "blender" / "release" / "datafiles" / "colormanagement"
    dst_dir = work_dir / "ocio"

    if not work_dir.exists():
        work_dir.mkdir()
        repo_path = work_dir / "blender.zip"
        download_file(repo_url, repo_path)
        extract_zip(repo_path, remove_zip=True)
        shutil.copytree(src_dir, dst_dir)

    config_path = dst_dir / "config.ocio"
    return OcioConfigRenderer(
        name=f"AgX Blender-4.2.7",
        filename="AgX.blender",
        config_path=config_path,
        srgb_lin="Linear Rec.709",
        display="sRGB",
        view="AgX",
        look="AgX - Punchy",
        reference_url=repo_url,
    )


def _build_AgXc_renderer(work_dir: Path) -> OcioConfigRenderer:
    version = "0.11.4"
    repo_url = f"https://github.com/MrLixm/AgXc/archive/refs/tags/v{version}.zip"
    if not work_dir.exists():
        work_dir.mkdir()
        repo_path = work_dir / "AgXc.zip"
        download_file(repo_url, repo_path)
        extract_zip(repo_path, remove_zip=True)
    config_path = work_dir / f"AgXc-{version}" / "ocio" / "config.ocio"
    config_version = config_path.read_text("utf-8")
    config_version = config_version.split("\n")[0].replace("# version: ", "")
    return OcioConfigRenderer(
        name=f"AgXc v{config_version}",
        filename=f"AgXc.{config_version}",
        config_path=config_path,
        srgb_lin="Linear sRGB",
        display="sRGB",
        view="AgX Punchy",
        reference_url=repo_url,
    )


def _build_AgXc_rc_renderer(work_dir: Path) -> OcioConfigRenderer:
    repo_url = (
        f"https://github.com/MrLixm/AgXc/archive/refs/heads/refacto/ocio-overhaul.zip"
    )
    if not work_dir.exists():
        work_dir.mkdir()
        repo_path = work_dir / "AgXc.zip"
        download_file(repo_url, repo_path)
        extract_zip(repo_path, remove_zip=True)
    config_path = (
        work_dir
        / "AgXc-refacto-ocio-overhaul"
        / "ocio"
        / "AgXc_default_OCIO-v2"
        / "config.ocio"
    )
    config_version = config_path.read_text("utf-8")
    config_version = config_version.split("\n")[0].replace("# version: ", "")
    return OcioConfigRenderer(
        name=f"AgXc v{config_version}",
        filename=f"AgXc.{config_version}",
        config_path=config_path,
        srgb_lin="sRGB-linear",
        display="sRGB-2.2",
        view="AgXc.base Punchy",
        reference_url=repo_url,
    )


def _build_TCAM_renderer(work_dir: Path) -> OcioConfigRenderer:
    url = f"https://www.filmlight.ltd.uk/resources/download.php"
    if not work_dir.exists():
        work_dir.mkdir()
        repo_path = work_dir / "TCAM.zip"
        download_file_advanced(
            url,
            repo_path,
            params={
                "access": "public",
                "download": "colourspaces/TCS_TCAMv3.zip",
                "last_page": "/support/customer-login/colourspaces/colourspaces.php",
                "button.x": "9",
                "button.y": "6",
            },
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:136.0) Gecko/20100101 Firefox/136.0",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        extract_zip(repo_path, remove_zip=True)
    config_path = work_dir / "TCS_TCAMv3" / "TCS_TCAMv3.ocio"

    return OcioConfigRenderer(
        name=f"TCAMv3",
        filename=f"TCAMv3",
        config_path=config_path,
        srgb_lin="CGI: Linear : Rec.709",
        display="sRGB Display: 2.2 Gamma : Rec.709 Truelight CAM v3",
        view="sRGB Display: 2.2 Gamma : Rec.709",
        reference_url=url,
    )


def _build_ARRI_renderer(work_dir: Path) -> OcioConfigRenderer:
    """
    ARRI Reveal is only provided as a display-ready LUT from ARRI.

    We use the ACESv3.0.0 config as a base on which we add a new view with the ARRI Lut.
    """
    luts_url = "https://www.arri.com/resource/blob/280728/7933fd1ce4de9165b906936661ab54eb/arri-logc4-lut-package-data.zip"
    aces_url = "https://github.com/AcademySoftwareFoundation/OpenColorIO-Config-ACES/releases/download/v3.0.0/studio-config-all-views-v3.0.0_aces-v2.0_ocio-v2.4.ocio"
    aces_config_path = work_dir / aces_url.split("/")[-1]
    if not work_dir.exists():
        work_dir.mkdir()
        repo_path = work_dir / "arri.zip"
        download_file(luts_url, repo_path)
        extract_zip(repo_path, remove_zip=True)
        download_file(aces_url, aces_config_path)

        src_lut_path = list(
            work_dir.rglob("ARRI_LogC4-to-Gamma24_Rec709-D65_v1-65.cube")
        )[0]
        lut_path = work_dir / src_lut_path.name
        shutil.copy(src_lut_path, lut_path)

        # noinspection PyArgumentList
        config: ocio.Config = ocio.Config.CreateFromFile(str(aces_config_path))
        transforms = ocio.GroupTransform()
        transforms.appendTransform(
            ocio.ColorSpaceTransform(
                src="ACES2065-1",
                dst="ARRI LogC4",
            )
        )
        transforms.appendTransform(
            ocio.FileTransform(
                # lut should be stored next to ocio config
                src=lut_path.name,
                interpolation=ocio.INTERP_LINEAR,
                direction=ocio.TRANSFORM_DIR_FORWARD,
            )
        )
        # the LUT output BT.1886 so convert to 2.2 to stay uniform with other renderers.
        transforms.appendTransform(
            ocio.ColorSpaceTransform(
                src="Gamma 2.4 Encoded Rec.709",
                dst="Gamma 2.2 Encoded Rec.709",
            )
        )
        arri_colorspace_name = "ARRI Gamma24 Rec709-D65 v1"
        arri_colorspace = ocio.ColorSpace(
            referenceSpace=ocio.REFERENCE_SPACE_SCENE,
            name=arri_colorspace_name,
            fromReference=transforms,
        )
        config.addColorSpace(arri_colorspace)
        config.addDisplayView("sRGB - 2.2", "ARRI Reveal", arri_colorspace_name)
        config.setSearchPath(".")
        config.validate()
        LOGGER.debug("writing patched ACES config with ARRI Reveal")
        config.serialize(str(aces_config_path))

    return OcioConfigRenderer(
        name=f"ARRI Reveal",
        filename="ARRIreveal",
        config_path=aces_config_path,
        srgb_lin="Linear Rec.709 (sRGB)",
        display="sRGB - 2.2",
        view="ARRI Reveal",
        reference_url=luts_url,
    )


def _build_ACES13gm_renderer(work_dir: Path) -> OcioConfigRenderer:
    repo_url = "https://github.com/AcademySoftwareFoundation/OpenColorIO-Config-ACES/releases/download/v2.1.0-v2.2.0/studio-config-v2.1.0_aces-v1.3_ocio-v2.1.ocio"
    config_path = work_dir / repo_url.split("/")[-1]
    if not work_dir.exists():
        work_dir.mkdir()
        download_file(repo_url, config_path)
    return OcioConfigRenderer(
        name=f"ACES v1.3 + Gamut Mapping",
        filename="ACESv1.3-gm",
        config_path=config_path,
        srgb_lin="Linear Rec.709 (sRGB)",
        display="sRGB - Display",
        view="ACES 1.0 - SDR Video",
        look="ACES 1.3 Reference Gamut Compression",
        reference_url=repo_url,
    )


def _build_ACES2gm_renderer(work_dir: Path) -> OcioConfigRenderer:
    repo_url = "https://github.com/AcademySoftwareFoundation/OpenColorIO-Config-ACES/releases/download/v3.0.0/studio-config-all-views-v3.0.0_aces-v2.0_ocio-v2.4.ocio"
    config_path = work_dir / repo_url.split("/")[-1]
    if not work_dir.exists():
        work_dir.mkdir()
        download_file(repo_url, config_path)
    return OcioConfigRenderer(
        name=f"ACES v2.0 + Gamut Mapping",
        filename="ACESv2.0-gm",
        config_path=config_path,
        srgb_lin="Linear Rec.709 (sRGB)",
        display="sRGB - Display",
        view="ACES 2.0 - SDR 100 nits (Rec.709)",
        look="ACES 1.3 Reference Gamut Compression",
        reference_url=repo_url,
    )


def build_renderers(renderer_work_dir: Path) -> list[OcioConfigRenderer]:
    renderers = []

    # note: order of renderers matters when generating combined image

    work_dir = renderer_work_dir / "TCAMv3"
    renderer = _build_TCAM_renderer(work_dir)
    renderers.append(renderer)

    work_dir = renderer_work_dir / "ARRI"
    renderer = _build_ARRI_renderer(work_dir)
    renderers.append(renderer)

    work_dir = renderer_work_dir / "AgX"
    renderer = _build_AgX_renderer(work_dir)
    renderers.append(renderer)

    # work_dir = renderer_work_dir / "AgXc"
    # renderer = _build_AgXc_renderer(work_dir)
    # renderers.append(renderer)

    work_dir = renderer_work_dir / "AgXc.blender"
    renderer = _build_AgX_blender_renderer(work_dir)
    renderers.append(renderer)

    work_dir = renderer_work_dir / "AgXc.rc"
    renderer = _build_AgXc_rc_renderer(work_dir)
    renderers.append(renderer)

    work_dir = renderer_work_dir / "ACES13"
    renderer = _build_ACES13gm_renderer(work_dir)
    renderers.append(renderer)

    work_dir = renderer_work_dir / "ACES2"
    renderer = _build_ACES2gm_renderer(work_dir)
    renderers.append(renderer)

    renderer = dataclasses.replace(
        renderer,
        name=f"ACES v2.0 ",
        filename="ACESv2.0",
        srgb_lin="Linear Rec.709 (sRGB)",
        display="sRGB - Display",
        view="ACES 2.0 - SDR 100 nits (Rec.709)",
        look="",
    )
    renderers.append(renderer)

    renderer = dataclasses.replace(
        renderer,
        name=f"Native (no image formation)",
        filename="native",
        srgb_lin="Linear Rec.709 (sRGB)",
        display="sRGB - Display",
        view="Un-tone-mapped",
        look="",
    )
    renderers.insert(0, renderer)

    return renderers


def get_cli(argv: list[str] | None = None) -> argparse.Namespace:
    argv = argv or sys.argv[1:]
    parser = argparse.ArgumentParser(
        description="Generates image to compare image formation algorithm.",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=WORK_DIR / "results",
        help="filesystem path to write the result images to.",
    )
    parser.add_argument(
        "--renderer-dir",
        type=Path,
        default=WORK_DIR / "renderers",
        help="filesystem path to write renderers resource data to.",
    )
    parsed = parser.parse_args(argv)
    return parsed


def main(argv: list[str] | None = None):
    cli = get_cli(argv)

    assets = [
        SourceAsset(
            path=get_imagery_set("al.sorted-color.bg-black"),
            filename="lxmpicturelab-set.al",
            generators=[GeneratorFull(2048)],
        ),
        SourceAsset(
            path=get_imagery_asset("CGts-W0L-sweep").image_path,
            filename="CGts-W0L-sweep",
            generators=[GeneratorFull(864)],
        ),
        SourceAsset(
            path=get_imagery_asset("CAlc-D8T-dragon").image_path,
            filename="CAlc-D8T-dragon",
            generators=[GeneratorExposureBands(0.45), GeneratorFull(864)],
        ),
        SourceAsset(
            path=get_imagery_asset("PAmsk-R65-christmas").image_path,
            filename="PAmsk-R65-christmas",
            generators=[GeneratorExposureBands(0.3), GeneratorFull(864)],
        ),
    ]

    renderer_work_dir = cli.renderer_dir
    renderer_work_dir.mkdir(exist_ok=True)
    LOGGER.info(f"building renderers to '{renderer_work_dir}'")
    renderers = build_renderers(renderer_work_dir)

    for renderer in renderers:
        as_json = renderer.to_json(indent=4, sort_keys=True)
        renderer_path = renderer_work_dir / f"{renderer.filename}.json"
        LOGGER.info(f"writing '{renderer_path}'")
        renderer_path.write_text(as_json)

    results_dir = cli.results_dir
    results_dir.mkdir(exist_ok=True)
    LOGGER.info(f"results will be found at '{results_dir}'")

    stime = time.time()

    for asset in assets:
        asset_results_dir = results_dir / asset.filename
        if asset_results_dir.exists():
            shutil.rmtree(asset_results_dir)
        asset_results_dir.mkdir()

        metadata = {"name": asset.filename, "generators": {}}
        metadata_path = results_dir / f"{asset.filename}.json"

        for generator in asset.generators:
            generator_results: dict[str, Path] = {}
            for renderer in renderers:
                LOGGER.info(
                    f"💫 running asset '{asset.path.stem}' with renderer "
                    f"'{renderer.name}'; generator '{generator.shortname()}'"
                )
                output_path = generator.run(
                    src_path=asset.path,
                    renderer=renderer,
                    target_dir=asset_results_dir,
                )
                generator_results[renderer.name] = output_path

            metadata["generators"][generator.shortname()] = {}
            metadata["generators"][generator.shortname()]["renders"] = {
                renderer_name: str(path.relative_to(metadata_path.parent))
                for renderer_name, path in generator_results.items()
            }

            combined_name = (
                f"{asset.path.stem}.{generator.shortname()}.__combined__.jpg"
            )
            combined_path = asset_results_dir / combined_name
            LOGGER.info(f"💫 generating combined image to '{combined_path}'")
            generate_combine(list(generator_results.values()), combined_path)

            metadata["generators"][generator.shortname()]["combined"] = str(
                combined_path.relative_to(asset_results_dir)
            )

        LOGGER.info(f"writing metadata to '{metadata_path}'")
        with metadata_path.open("w") as metadata_file:
            json.dump(metadata, metadata_file, indent=4)

    LOGGER.info(f"✅ finished in {time.time() - stime:.1f}s")


if __name__ == "__main__":
    lxmpicturelab.configure_logging()
    main()
