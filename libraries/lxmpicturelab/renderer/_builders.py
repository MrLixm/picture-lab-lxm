import abc
import dataclasses
import logging
import os
import shutil
from pathlib import Path

import PyOpenColorIO as ocio

from lxmpicturelab.download import download_file
from lxmpicturelab.download import download_file_advanced
from lxmpicturelab.download import extract_zip
from ._config import OcioConfigRenderer

LOGGER = logging.getLogger(__name__)

THISDIR = Path(__file__).parent


class BaseRendererBuilder:
    """
    Abstract template to define how to build a renderer.

    Args:
        path: filesystem path to an existing empty directory.
    """

    identifier: str = NotImplemented
    source_url: str = NotImplemented

    def __init__(self, path: Path):
        self.path: Path = path

    @abc.abstractmethod
    def get_ocio_config_path(self) -> Path:
        pass

    @abc.abstractmethod
    def get_renderer(self) -> OcioConfigRenderer:
        pass

    @abc.abstractmethod
    def build(self):
        pass


class AgXBuilder(BaseRendererBuilder):
    identifier: str = "AgX"
    git_ref = "1ba3230e6f2c825003d9e139750edd233b6a906e"
    source_url: str = f"https://github.com/sobotka/AgX/archive/{git_ref}.zip"

    def get_ocio_config_path(self) -> Path:
        return self.path / f"AgX-{self.git_ref}" / "config.ocio"

    def get_renderer(self):
        return OcioConfigRenderer(
            name=f"AgX",
            filename=self.identifier,
            description="The original AgX algorithm by Troy Sobotka.",
            config_path=self.get_ocio_config_path(),
            srgb_lin="Linear BT.709",
            display="sRGB",
            view="Appearance Punchy",
            source_url=self.source_url,
            references=[
                "https://github.com/sobotka/AgX",
                "https://blenderartists.org/t/feedback-development-filmic-baby-step-to-a-v2/1361663",
            ],
        )

    def build(self):
        repo_path = self.path / "AgX.zip"
        download_file(self.source_url, repo_path)
        extract_zip(repo_path, remove_zip=True)
        assert self.get_ocio_config_path().exists()


class AgXBlenderBuilder(BaseRendererBuilder):
    identifier: str = "AgX.blender"
    source_url: str = "https://projects.blender.org/blender/blender/archive/v4.2.7.zip"

    def get_ocio_config_path(self) -> Path:
        return self.path / "ocio" / "config.ocio"

    def get_renderer(self):
        return OcioConfigRenderer(
            name=f"AgX Blender-4.2.7",
            filename=self.identifier,
            description="The improved AgX algorithm implemented in Blender.",
            config_path=self.get_ocio_config_path(),
            srgb_lin="Linear Rec.709",
            display="sRGB",
            view="AgX",
            look="AgX - Punchy",
            source_url=self.source_url,
            references=[
                "https://projects.blender.org/blender/blender/pulls/106355",
                "https://github.com/EaryChow/AgX",
                "https://blenderartists.org/t/feedback-development-filmic-baby-step-to-a-v2/1361663",
            ],
        )

    def build(self):
        src_dir = self.path / "blender" / "release" / "datafiles" / "colormanagement"
        repo_path = self.path / "blender.zip"
        download_file(self.source_url, repo_path)
        extract_zip(repo_path, remove_zip=True)
        config_path = self.get_ocio_config_path()
        shutil.copytree(src_dir, config_path.parent)
        shutil.rmtree(self.path / "blender")
        assert config_path.exists()


class AgXcBuilder(BaseRendererBuilder):
    identifier: str = "AgXc"
    git_ref = "3e78f1541b06191ae3a8e2efce1b74c2a8b8d23f"
    source_url: str = f"https://github.com/MrLixm/AgXc/archive/{git_ref}.zip"

    def get_ocio_config_path(self) -> Path:
        return (
            self.path
            / f"AgXc-{self.git_ref}"
            / "ocio"
            / "AgXc_default_OCIO-v2"
            / "config.ocio"
        )

    def get_renderer(self):
        return OcioConfigRenderer(
            name=f"AgXc v1.0",
            filename=self.identifier,
            description="Another custom variant of AgX, closer to Blender variant. Still in development.",
            config_path=self.get_ocio_config_path(),
            srgb_lin="sRGB-linear",
            display="sRGB-2.2",
            view="AgXc.base Punchy",
            source_url=self.source_url,
            references=[
                "https://github.com/MrLixm/AgXc",
                "https://github.com/MrLixm/AgXc/pull/35",
            ],
        )

    def build(self):
        repo_path = self.path / "AgXc.zip"
        download_file(self.source_url, repo_path)
        extract_zip(repo_path, remove_zip=True)
        assert self.get_ocio_config_path().exists()


class TCAMBuilder(BaseRendererBuilder):
    identifier: str = "TCAMv3"
    source_url: str = "https://www.filmlight.ltd.uk/resources/download.php"

    def get_ocio_config_path(self) -> Path:
        return self.path / "TCS_TCAMv3" / "TCS_TCAMv3.ocio"

    def get_renderer(self):
        return OcioConfigRenderer(
            name=f"T-CAM v3",
            filename=f"TCAMv3",
            description="Filmlight's color pipeline. Initially designed for their Baselight grading tool but for which they still provide an OCIO configuration.",
            config_path=self.get_ocio_config_path(),
            srgb_lin="CGI: Linear : Rec.709",
            display="sRGB Display: 2.2 Gamma : Rec.709 Truelight CAM v3",
            view="sRGB Display: 2.2 Gamma : Rec.709",
            source_url=self.source_url,
            references=[
                "https://www.filmlight.ltd.uk/support/customer-login/colourspaces/colourspaces.php",
            ],
        )

    def build(self):
        repo_path = self.path / "TCAM.zip"
        download_file_advanced(
            self.source_url,
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
        assert self.get_ocio_config_path().exists()


class ARRIBuilder(BaseRendererBuilder):
    identifier: str = "ARRIreveal"
    source_url: str = (
        "https://www.arri.com/resource/blob/280728/7933fd1ce4de9165b906936661ab54eb/arri-logc4-lut-package-data.zip"
    )
    aces_url = "https://github.com/AcademySoftwareFoundation/OpenColorIO-Config-ACES/releases/download/v3.0.0/studio-config-all-views-v3.0.0_aces-v2.0_ocio-v2.4.ocio"

    def get_ocio_config_path(self) -> Path:
        return self.path / self.aces_url.split("/")[-1]

    def get_renderer(self):
        config_name = self.aces_url.split("/")[-1]
        return OcioConfigRenderer(
            name=f"ARRI Reveal",
            filename=self.identifier,
            description=f'The ARRI "color-science" pipeline, based on their provided display LUTs. Injected in the {config_name} config.',
            config_path=self.get_ocio_config_path(),
            srgb_lin="Linear Rec.709 (sRGB)",
            display="sRGB - 2.2",
            view="ARRI Reveal",
            source_url=self.source_url,
            references=[
                "https://www.arri.com/en/learn-help/learn-help-camera-system/tools/lut-generator",
                "https://www.arri.com/en/learn-help/learn-help-camera-system/image-science/reveal-color-science",
            ],
        )

    def build(self):
        """
        ARRI Reveal is only provided as a display-ready LUT from ARRI.

        We use the ACESv3.0.0 config as a base on which we add a new view with the ARRI Lut.
        """
        aces_config_path = self.path / self.aces_url.split("/")[-1]
        repo_path = self.path / "arri.zip"
        download_file(self.source_url, repo_path)
        extract_zip(repo_path, remove_zip=True)
        download_file(self.aces_url, aces_config_path)

        src_lut_path = list(
            self.path.rglob("ARRI_LogC4-to-Gamma24_Rec709-D65_v1-65.cube")
        )[0]
        lut_path = self.path / src_lut_path.name
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
        assert self.get_ocio_config_path().exists()


def patch_aces_config(config: ocio.Config):
    """
    Add an sRGB-2.2 Display to the ACES config.

    They assume a piecewise transfer-function by default so we use uniform it to 2.2 for
    all algorithm.
    """
    transforms = ocio.GroupTransform()
    transforms.appendTransform(
        ocio.ColorSpaceTransform(
            src="CIE XYZ-D65 - Display-referred",
            dst="Linear Rec.709 (sRGB)",
        )
    )
    transforms.appendTransform(
        ocio.ColorSpaceTransform(
            src="Linear Rec.709 (sRGB)",
            dst="Gamma 2.2 Encoded Rec.709",
        )
    )
    new_colorspace = ocio.ColorSpace(
        name="sRGB - 2.2",
        referenceSpace=ocio.REFERENCE_SPACE_DISPLAY,
        fromReference=transforms,
    )
    config.addColorSpace(new_colorspace)


class ACES13gmBuilder(BaseRendererBuilder):
    identifier: str = "ACESv1.3-gm"
    source_url: str = (
        "https://github.com/AcademySoftwareFoundation/OpenColorIO-Config-ACES/releases/download/v2.1.0-v2.2.0/studio-config-v2.1.0_aces-v1.3_ocio-v2.1.ocio"
    )

    def get_ocio_config_path(self) -> Path:
        return self.path / self.source_url.split("/")[-1]

    def get_renderer(self):
        return OcioConfigRenderer(
            name=f"ACES v1.3 + Gamut Mapping",
            filename=self.identifier,
            description=(
                'The Academy Color Encoding System on major version 1, with their "Gamut Compression" look.'
                "The config has been edited to add an sRGB-2.2 Display."
            ),
            config_path=self.get_ocio_config_path(),
            srgb_lin="Linear Rec.709 (sRGB)",
            display="sRGB - 2.2",
            view="ACES 1.0 - SDR Video",
            look="ACES 1.3 Reference Gamut Compression",
            source_url=self.source_url,
            references=["https://community.acescentral.com/"],
        )

    def build(self):
        config_path = self.get_ocio_config_path()
        download_file(self.source_url, config_path)
        assert config_path.exists()
        # noinspection PyArgumentList
        config: ocio.Config = ocio.Config.CreateFromFile(str(config_path))
        patch_aces_config(config)
        config.addDisplaySharedView(
            "sRGB - 2.2",
            "ACES 1.0 - SDR Video",
        )
        config.validate()
        LOGGER.debug("writing patched ACES config with sRGB-2.2")
        config.serialize(str(config_path))


class ACES2gmBuilder(BaseRendererBuilder):
    identifier: str = "ACESv2.0-gm"
    source_url: str = (
        "https://github.com/AcademySoftwareFoundation/OpenColorIO-Config-ACES/releases/download/v3.0.0/studio-config-all-views-v3.0.0_aces-v2.0_ocio-v2.4.ocio"
    )

    def get_ocio_config_path(self) -> Path:
        return self.path / self.source_url.split("/")[-1]

    def get_renderer(self):
        return OcioConfigRenderer(
            name=f"ACES v2.0 + Gamut Mapping",
            filename=self.identifier,
            description=(
                'The Academy Color Encoding System on major version 2, with their "Gamut Compression" look.'
                "The config has been edited to add an sRGB-2.2 Display."
            ),
            config_path=self.get_ocio_config_path(),
            srgb_lin="Linear Rec.709 (sRGB)",
            display="sRGB - 2.2",
            view="ACES 2.0 - SDR 100 nits (Rec.709)",
            look="ACES 1.3 Reference Gamut Compression",
            source_url=self.source_url,
            references=["https://community.acescentral.com/"],
        )

    def build(self):
        config_path = self.get_ocio_config_path()
        download_file(self.source_url, config_path)
        assert config_path.exists()
        # noinspection PyArgumentList
        config: ocio.Config = ocio.Config.CreateFromFile(str(config_path))
        patch_aces_config(config)
        config.addDisplaySharedView(
            "sRGB - 2.2",
            "ACES 2.0 - SDR 100 nits (Rec.709)",
        )
        config.addDisplaySharedView(
            "sRGB - 2.2",
            "Un-tone-mapped",
        )
        config.validate()
        LOGGER.debug("writing patched ACES config with sRGB-2.2")
        config.serialize(str(config_path))


class ACES2Builder(ACES2gmBuilder):
    identifier = "ACESv2.0"

    def get_renderer(self):
        renderer = super().get_renderer()
        return dataclasses.replace(
            renderer,
            name=f"ACES v2.0 ",
            filename=self.identifier,
            description=(
                "The Academy Color Encoding System on major version 2."
                "The config has been edited to add an sRGB-2.2 Display."
            ),
            srgb_lin="Linear Rec.709 (sRGB)",
            display="sRGB - 2.2",
            view="ACES 2.0 - SDR 100 nits (Rec.709)",
            look="",
            references=["https://community.acescentral.com/"],
        )


class NativeBuilder(ACES2gmBuilder):
    identifier = "native"

    def get_renderer(self):
        renderer = super().get_renderer()
        return dataclasses.replace(
            renderer,
            name=f"Native (no image formation)",
            filename="native",
            description="No picture formation is applied, anything outside the destination volume is clipped.",
            srgb_lin="Linear Rec.709 (sRGB)",
            display="sRGB - 2.2",
            view="Un-tone-mapped",
            look="",
            references=[],
        )


class OpenDRTBuilder(BaseRendererBuilder):
    identifier: str = "OpenDRT"
    source_url: str = (
        "https://github.com/chrisbrejon/OpenDRT-OCIO-Config/archive/58a630cce6f4167c52928f6ba28ab1de083fe6cc.zip"
    )

    def get_ocio_config_path(self) -> Path:
        return self.path / "ocio" / "config.ocio"

    def get_renderer(self):
        return OcioConfigRenderer(
            name=f"OpenDRT v1.0.0",
            filename=self.identifier,
            description="An open source display rendering transform authored by Jed Smith. Using the version 1.0.0 which has been converted to OCIO by Chris Brejon.",
            config_path=self.get_ocio_config_path(),
            srgb_lin="linear",
            display="sRGB - 2.2 100 nits video dim",
            view="OpenDRT 1.0.0",
            look="",
            source_url=self.source_url,
            references=["https://github.com/jedypod/open-display-transform"],
        )

    def build(self):
        config_path = self.get_ocio_config_path()
        repo_dir = self.path / "tmp"
        repo_dir.mkdir(exist_ok=True)
        repo_path = repo_dir / "OpenDRT-OCIO-Config.zip"
        git_ref = self.source_url.split("/")[-1].split(".zip")[0]
        download_file(self.source_url, repo_path)
        extract_zip(repo_path, remove_zip=True)
        os.rename(repo_dir / f"OpenDRT-OCIO-Config-{git_ref}", self.path / "ocio")
        assert config_path.exists()

        # noinspection PyArgumentList
        config: ocio.Config = ocio.Config.CreateFromFile(str(config_path))
        transforms = ocio.GroupTransform()
        transforms.appendTransform(
            ocio.ColorSpaceTransform(
                src="lin_xyz",
                dst="openDRT 1.0.0 - Rec.709 - 2.4 Gamma",
            )
        )
        transforms.appendTransform(
            ocio.ExponentTransform(
                [2.4, 2.4, 2.4, 1.0],
            )
        )
        transforms.appendTransform(
            ocio.ExponentTransform(
                [2.2, 2.2, 2.2, 1.0],
                direction=ocio.TRANSFORM_DIR_INVERSE,
            )
        )
        new_colorspace = ocio.ColorSpace(
            name="openDRT 1.0.0 - Rec.709 - 2.2 Gamma",
            referenceSpace=ocio.REFERENCE_SPACE_SCENE,
            fromReference=transforms,
        )
        config.addColorSpace(new_colorspace)
        config.addDisplayView(
            "sRGB - 2.2 100 nits video dim",
            "OpenDRT 1.0.0",
            new_colorspace.getName(),
        )
        config.validate()
        LOGGER.debug("writing patched OpenDRT config with sRGB-2.2")
        config.serialize(str(config_path))


class DRT2499Builder(BaseRendererBuilder):
    identifier: str = "2499DRT"
    source_url: str = (
        "https://github.com/Joegenco/PixelManager/archive/c8716a42c7e03c6573915ad24f19eccfc39f687c.zip"
    )

    def get_ocio_config_path(self) -> Path:
        return self.path / "ocio" / "config.ocio"

    def get_renderer(self):
        return OcioConfigRenderer(
            name=f"2499DRT",
            filename=self.identifier,
            description="A .dctl algorithm by Juan Pablo Zambrano; targeting colorists. Converted to OCIO by Joegen.",
            config_path=self.get_ocio_config_path(),
            srgb_lin="Linear Rec.709",
            display="sRGB",
            view="JP2499DRT",
            look="",
            source_url=self.source_url,
            references=["https://github.com/JuanPabloZambrano/DCTL/tree/main/2499_DRT"],
        )

    def build(self):
        repo_dir = self.path / "tmp"
        repo_dir.mkdir(exist_ok=True)
        repo_path = repo_dir / "PixelManager.zip"
        git_ref = self.source_url.split("/")[-1].split(".zip")[0]
        download_file(self.source_url, repo_path)
        extract_zip(repo_path, remove_zip=True)
        os.rename(repo_dir / f"PixelManager-{git_ref}", self.path / "ocio")
        assert self.get_ocio_config_path().exists()


class Kodak2383Builder(BaseRendererBuilder):
    identifier: str = "Kodak2383"
    source_url: str = (
        "https://www.dropbox.com/s/qn62wg07f21jydp/LMT%20Kodak%202383%20Print%20Emulation.xml?dl=0"
    )
    aces_url = "https://github.com/AcademySoftwareFoundation/OpenColorIO-Config-ACES/releases/download/v3.0.0/studio-config-all-views-v3.0.0_aces-v2.0_ocio-v2.4.ocio"

    def get_ocio_config_path(self) -> Path:
        return self.path / self.aces_url.split("/")[-1]

    def get_renderer(self):
        config_name = self.aces_url.split("/")[-1]
        return OcioConfigRenderer(
            name=f"Kodak2383",
            filename=self.identifier,
            description=f"The iconic Kodak2383 print film simulation LUT, authored by Blackmagic as an ACES LMT. Injected in the {config_name} config.",
            config_path=self.get_ocio_config_path(),
            srgb_lin="Linear Rec.709 (sRGB)",
            display="sRGB - 2.2",
            view="Kodak2383",
            source_url=self.source_url,
            references=[
                "https://community.acescentral.com/t/lmts-part-1-what-are-they-and-what-can-they-do-for-me/790/10?u=mrlixm",
                "https://www.kodak.com/en/motion/product/post/print-films/vision-color-2383-3383/",
            ],
        )

    def build(self):
        src_lut_path = THISDIR / "LMT-Kodak-2383-Print-Emulation.clf"
        dst_lut_path = self.path / "LMT-Kodak-2383-Print-Emulation.clf"
        shutil.copy(src_lut_path, dst_lut_path)

        aces_config_path = self.path / self.aces_url.split("/")[-1]
        download_file(self.aces_url, aces_config_path)

        # noinspection PyArgumentList
        config: ocio.Config = ocio.Config.CreateFromFile(str(aces_config_path))
        patch_aces_config(config)
        transforms = ocio.GroupTransform()
        transforms.appendTransform(
            ocio.FileTransform(
                # lut should be stored next to ocio config
                src=dst_lut_path.name,
                direction=ocio.TRANSFORM_DIR_FORWARD,
            )
        )
        # the LUT output BT.1886 so convert to 2.2 to stay uniform with other renderers.
        transforms.appendTransform(
            ocio.ColorSpaceTransform(
                src="ACES2065-1",
                dst="sRGB - 2.2",
            )
        )
        new_colorspace_name = "Kodak2383 AP0"
        arri_colorspace = ocio.ColorSpace(
            referenceSpace=ocio.REFERENCE_SPACE_SCENE,
            name=new_colorspace_name,
            fromReference=transforms,
        )
        config.addColorSpace(arri_colorspace)
        config.addDisplayView("sRGB - 2.2", "Kodak2383", new_colorspace_name)
        config.setSearchPath(".")
        config.validate()
        LOGGER.debug(f"writing patched ACES config with {self.identifier}")
        config.serialize(str(aces_config_path))
        assert self.get_ocio_config_path().exists()


RENDERER_BUILDERS = [
    AgXBuilder,
    AgXBlenderBuilder,
    AgXcBuilder,
    TCAMBuilder,
    ARRIBuilder,
    ACES13gmBuilder,
    ACES2gmBuilder,
    ACES2Builder,
    NativeBuilder,
    OpenDRTBuilder,
    DRT2499Builder,
    Kodak2383Builder,
]

RENDERER_BUILDERS_BY_ID = {b.identifier: b for b in RENDERER_BUILDERS}
