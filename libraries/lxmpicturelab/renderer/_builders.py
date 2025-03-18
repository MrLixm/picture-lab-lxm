import abc
import dataclasses
import logging
import shutil
from pathlib import Path

import PyOpenColorIO as ocio

from lxmpicturelab.download import download_file
from lxmpicturelab.download import download_file_advanced
from lxmpicturelab.download import extract_zip
from ._config import OcioConfigRenderer

LOGGER = logging.getLogger(__name__)


class BaseRendererBuilder:
    """
    Abstract template to define how to build a renderer.

    Args:
        path: filesystem path to an existing empty directory.
    """

    identifier: str = NotImplemented
    reference_url: str = NotImplemented

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
    reference_url: str = "https://github.com/sobotka/AgX/archive/refs/heads/main.zip"

    def get_ocio_config_path(self) -> Path:
        return self.path / "AgX-main" / "config.ocio"

    def get_renderer(self):
        return OcioConfigRenderer(
            name=f"AgX",
            filename=self.identifier,
            description="The original AgX algorithm by Troy Sobotka.",
            config_path=self.get_ocio_config_path(),
            srgb_lin="Linear BT.709",
            display="sRGB",
            view="Appearance Punchy",
            reference_url=self.reference_url,
        )

    def build(self):
        repo_path = self.path / "AgX.zip"
        download_file(self.reference_url, repo_path)
        extract_zip(repo_path, remove_zip=True)
        assert self.get_ocio_config_path().exists()


class AgXBlenderBuilder(BaseRendererBuilder):
    identifier: str = "AgX.blender"
    reference_url: str = (
        "https://projects.blender.org/blender/blender/archive/v4.2.7.zip"
    )

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
            reference_url=self.reference_url,
        )

    def build(self):
        src_dir = self.path / "blender" / "release" / "datafiles" / "colormanagement"
        repo_path = self.path / "blender.zip"
        download_file(self.reference_url, repo_path)
        extract_zip(repo_path, remove_zip=True)
        config_path = self.get_ocio_config_path()
        shutil.copytree(src_dir, config_path.parent)
        shutil.rmtree(self.path / "blender")
        assert config_path.exists()


class AgXcBuilder(BaseRendererBuilder):
    identifier: str = "AgXc"
    reference_url: str = (
        "https://github.com/MrLixm/AgXc/archive/refs/heads/refacto/ocio-overhaul.zip"
    )

    def get_ocio_config_path(self) -> Path:
        return (
            self.path
            / "AgXc-refacto-ocio-overhaul"
            / "ocio"
            / "AgXc_default_OCIO-v2"
            / "config.ocio"
        )

    def get_renderer(self):
        return OcioConfigRenderer(
            name=f"AgXc v1.0",
            filename=self.identifier,
            description="Another custom variant of AgX, closer to Blender variant. Not yet released.",
            config_path=self.get_ocio_config_path(),
            srgb_lin="sRGB-linear",
            display="sRGB-2.2",
            view="AgXc.base Punchy",
            reference_url=self.reference_url,
        )

    def build(self):
        repo_path = self.path / "AgXc.zip"
        download_file(self.reference_url, repo_path)
        extract_zip(repo_path, remove_zip=True)
        assert self.get_ocio_config_path().exists()


class TCAMBuilder(BaseRendererBuilder):
    identifier: str = "TCAMv3"
    reference_url: str = "https://www.filmlight.ltd.uk/resources/download.php"

    def get_ocio_config_path(self) -> Path:
        return self.path / "TCS_TCAMv3" / "TCS_TCAMv3.ocio"

    def get_renderer(self):
        return OcioConfigRenderer(
            name=f"TCAMv3",
            filename=f"TCAMv3",
            description="Filmlight's algorithm which is best working in the context of their grading tools.",
            config_path=self.get_ocio_config_path(),
            srgb_lin="CGI: Linear : Rec.709",
            display="sRGB Display: 2.2 Gamma : Rec.709 Truelight CAM v3",
            view="sRGB Display: 2.2 Gamma : Rec.709",
            reference_url=self.reference_url,
        )

    def build(self):
        repo_path = self.path / "TCAM.zip"
        download_file_advanced(
            self.reference_url,
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
    reference_url: str = (
        "https://www.arri.com/resource/blob/280728/7933fd1ce4de9165b906936661ab54eb/arri-logc4-lut-package-data.zip"
    )
    aces_url = "https://github.com/AcademySoftwareFoundation/OpenColorIO-Config-ACES/releases/download/v3.0.0/studio-config-all-views-v3.0.0_aces-v2.0_ocio-v2.4.ocio"

    def get_ocio_config_path(self) -> Path:
        return self.path / self.aces_url.split("/")[-1]

    def get_renderer(self):
        return OcioConfigRenderer(
            name=f"ARRI Reveal",
            filename=self.identifier,
            description='The ARRI "color-science" pipeline, based on their provided display LUTs.',
            config_path=self.get_ocio_config_path(),
            srgb_lin="Linear Rec.709 (sRGB)",
            display="sRGB - 2.2",
            view="ARRI Reveal",
            reference_url=self.reference_url,
        )

    def build(self):
        """
        ARRI Reveal is only provided as a display-ready LUT from ARRI.

        We use the ACESv3.0.0 config as a base on which we add a new view with the ARRI Lut.
        """
        aces_config_path = self.path / self.aces_url.split("/")[-1]
        repo_path = self.path / "arri.zip"
        download_file(self.reference_url, repo_path)
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


class ACES13gmBuilder(BaseRendererBuilder):
    identifier: str = "ACESv1.3-gm"
    reference_url: str = (
        "https://github.com/AcademySoftwareFoundation/OpenColorIO-Config-ACES/releases/download/v2.1.0-v2.2.0/studio-config-v2.1.0_aces-v1.3_ocio-v2.1.ocio"
    )

    def get_ocio_config_path(self) -> Path:
        return self.path / self.reference_url.split("/")[-1]

    def get_renderer(self):
        return OcioConfigRenderer(
            name=f"ACES v1.3 + Gamut Mapping",
            filename=self.identifier,
            description='The Academy Color Encoding System on major version 1, with their "Gamut Compression" look.',
            config_path=self.get_ocio_config_path(),
            srgb_lin="Linear Rec.709 (sRGB)",
            display="sRGB - Display",
            view="ACES 1.0 - SDR Video",
            look="ACES 1.3 Reference Gamut Compression",
            reference_url=self.reference_url,
        )

    def build(self):
        config_path = self.get_ocio_config_path()
        download_file(self.reference_url, config_path)
        assert config_path.exists()


class ACES2gmBuilder(BaseRendererBuilder):
    identifier: str = "ACESv2.0-gm"
    reference_url: str = (
        "https://github.com/AcademySoftwareFoundation/OpenColorIO-Config-ACES/releases/download/v3.0.0/studio-config-all-views-v3.0.0_aces-v2.0_ocio-v2.4.ocio"
    )

    def get_ocio_config_path(self) -> Path:
        return self.path / self.reference_url.split("/")[-1]

    def get_renderer(self):
        return OcioConfigRenderer(
            name=f"ACES v2.0 + Gamut Mapping",
            filename=self.identifier,
            description='The Academy Color Encoding System on major version 2, with their "Gamut Compression" look.',
            config_path=self.get_ocio_config_path(),
            srgb_lin="Linear Rec.709 (sRGB)",
            display="sRGB - Display",
            view="ACES 2.0 - SDR 100 nits (Rec.709)",
            look="ACES 1.3 Reference Gamut Compression",
            reference_url=self.reference_url,
        )

    def build(self):
        config_path = self.get_ocio_config_path()
        download_file(self.reference_url, config_path)
        assert config_path.exists()


class ACES2Builder(ACES2gmBuilder):
    identifier = "ACESv2.0"

    def get_renderer(self):
        renderer = super().get_renderer()
        return dataclasses.replace(
            renderer,
            name=f"ACES v2.0 ",
            filename=self.identifier,
            description="The Academy Color Encoding System on major version 2.",
            srgb_lin="Linear Rec.709 (sRGB)",
            display="sRGB - Display",
            view="ACES 2.0 - SDR 100 nits (Rec.709)",
            look="",
        )


class NativeBuilder(ACES2gmBuilder):
    identifier = "native"

    def get_renderer(self):
        renderer = super().get_renderer()
        return dataclasses.replace(
            renderer,
            name=f"Native (no image formation)",
            filename="native",
            description="No picture formation is applied, anything outside the target volume is clipped.",
            srgb_lin="Linear Rec.709 (sRGB)",
            display="sRGB - Display",
            view="Un-tone-mapped",
            look="",
        )


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
]

RENDERER_BUILDERS_BY_ID = {b.identifier: b for b in RENDERER_BUILDERS}
