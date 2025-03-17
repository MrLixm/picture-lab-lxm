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
from lxmpicturelab.browse import find_asset
from lxmpicturelab.comparison import ComparisonSession
from lxmpicturelab.download import download_file
from lxmpicturelab.download import download_file_advanced
from lxmpicturelab.download import extract_zip
from lxmpicturelab.renderer import OcioConfigRenderer
from lxmpicturelab.oiiotoolio import oiiotool_export_auto_mosaic
from lxmpicturelab.comparison import ComparisonRender
from lxmpicturelab.comparison import BaseGenerator
from lxmpicturelab.comparison import GeneratorFull
from lxmpicturelab.comparison import GeneratorExposureBands

LOGGER = logging.getLogger(Path(__file__).stem)


WORKBENCH_DIR.mkdir(exist_ok=True)
WORK_DIR = WORKBENCH_DIR / "comparisons-generate"
WORK_DIR.mkdir(exist_ok=True)


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
        description="The original AgX algorithm by Troy Sobotka.",
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
        description="The improved AgX algorithm implemented in Blender.",
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
        description="Another custom variant of AgX.",
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
        description="Another custom variant of AgX, closer to Blender variant. Not yet released.",
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
        description="Filmlight's algorithm which is best working in the context of their grading tools.",
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
        description='The ARRI "color-science" pipeline, based on their provided display LUTs.',
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
        description='The Academy Color Encoding System on major version 1, with their "Gamut Compression" look.',
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
        description='The Academy Color Encoding System on major version 2, with their "Gamut Compression" look.',
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
        description="The Academy Color Encoding System on major version 2.",
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
        description="No picture formation is applied, anything outside the target volume is clipped.",
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
        "asset_id",
        type=str,
        help="Identifier of the asset to generate comparison for.",
    )
    parser.add_argument(
        "--build-renderer-only",
        action="store_true",
        help="Don't perform any asset processing and just build the renderers.",
    )
    parser.add_argument(
        "--generator-exposures",
        type=float,
        default=None,
        help=(
            "If specified, generate bands of gradually increasing exposure. "
            "Value is the percentage of image to offset on the x axis in 0-1 range."
        ),
    )
    parser.add_argument(
        "--generator-full",
        type=int,
        default=None,
        help=(
            "If specified, render the whole area of the image and resize "
            "its height to the given size (in pixels)."
        ),
    )
    parser.add_argument(
        "--combined-renderers",
        action="store_true",
        help=(
            "If specified, create an additional image which combine all the image "
            "generated for each renderer."
        ),
    )
    parser.add_argument(
        "--target-dir",
        type=Path,
        default=None,
        help="filesystem path to a directory that may not exist.",
    )
    parser.add_argument(
        "--renderer-dir",
        type=Path,
        default=WORK_DIR / "renderers",
        help="filesystem path to a directory that may not exist.",
    )
    parsed = parser.parse_args(argv)
    return parsed


def main(argv: list[str] | None = None):
    cli = get_cli(argv)
    stime = time.time()

    asset_id: str = cli.asset_id
    renderer_work_dir: Path = cli.renderer_dir
    target_dir: Path | None = cli.target_dir
    generator_exposure: float | None = cli.generator_exposures
    generator_full: int | None = cli.generator_full
    combined_renderers: bool = cli.combined_renderers
    build_renderer_only: bool = cli.build_renderer_only

    LOGGER.debug(f"{asset_id=}")
    LOGGER.debug(f"{target_dir=}")
    LOGGER.debug(f"{renderer_work_dir=}")
    LOGGER.debug(f"{combined_renderers=}")

    renderer_work_dir.mkdir(exist_ok=True)
    LOGGER.info(f"building renderers to '{renderer_work_dir}'")
    renderers = build_renderers(renderer_work_dir)
    for renderer in renderers:
        as_json = renderer.to_json(indent=4, sort_keys=True)
        renderer_path = renderer_work_dir / f"{renderer.filename}.json"
        LOGGER.info(f"writing '{renderer_path}'")
        renderer_path.write_text(as_json)

    if build_renderer_only:
        LOGGER.info("requested to only build renderer; exiting early ...")
        LOGGER.info(f"✅ finished in {time.time() - stime:.1f}s")
        return

    asset = find_asset(asset_id)
    if not asset:
        LOGGER.error(f"No asset with identifier '{asset_id}' found.")
        sys.exit(1)

    target_dir = target_dir or WORKBENCH_DIR / "comparisons" / asset.identifier
    if target_dir.exists():
        LOGGER.debug(f"shutil.rmtree({target_dir})")
        shutil.rmtree(target_dir)
    target_dir.mkdir(exist_ok=True, parents=True)

    generators: list[BaseGenerator] = []
    if generator_exposure is not None:
        generators.append(GeneratorExposureBands(generator_exposure))
    if generator_full is not None:
        generators.append(GeneratorFull(generator_full))

    session = ComparisonSession(asset=asset)

    for generator in generators:
        generator_results: dict[str, Path] = {}
        generator_name = generator.shortname
        comparison_src_path = asset.image_path

        for renderer in renderers:
            generation_dst_name = (
                f"{asset.identifier}.{generator_name}.{renderer.filename}.jpg"
            )
            comparison_dst_path = target_dir / generation_dst_name
            comparison = ComparisonRender(
                generator=generator,
                renderer=renderer,
                src_paths=[comparison_src_path],
                dst_path=comparison_dst_path,
            )
            LOGGER.info(f"💫 generating '{comparison_dst_path}'")
            comparison.run()
            session.add_render(comparison)

        # this is an extra comparison but without renderer
        if combined_renderers:
            combined_name = f"{asset.identifier}.{generator_name}.__combined__.jpg"
            combined_path = target_dir / combined_name
            comparison = ComparisonRender(
                generator=generator,
                renderer=None,
                src_paths=list(generator_results.values()),
                dst_path=combined_path,
            )
            LOGGER.info(f"💫 generating combined image to '{combined_path}'")
            comparison.run()
            session.add_render(comparison)

    metadata: str = session.to_json(indent=4)
    metadata_path = target_dir / f"{asset.identifier}.metadata.json"
    LOGGER.info(f"writing metadata to '{metadata_path}'")
    metadata_path.write_text(metadata, encoding="utf-8")

    LOGGER.info(f"✅ finished in {time.time() - stime:.1f}s")


if __name__ == "__main__":
    lxmpicturelab.configure_logging()
    main()
