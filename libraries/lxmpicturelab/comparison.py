import abc
import dataclasses
import json
import logging
import subprocess
from pathlib import Path
from typing import ClassVar

from lxmpicturelab.asset import ImageAsset
from lxmpicturelab.oiiotoolio import oiiotool_export
from lxmpicturelab.oiiotoolio import oiiotool_export_auto_mosaic
from lxmpicturelab.oiiotoolio import oiiotool_generate_expo_bands
from lxmpicturelab.oiiotoolio import OIIOTOOL
from lxmpicturelab.renderer import OcioConfigRenderer

LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass
class BaseGenerator(abc.ABC):
    """
    A method of generating an image with oiiotool.
    """

    shortname: ClassVar[str] = NotImplemented
    description: ClassVar[str] = NotImplemented

    @abc.abstractmethod
    def run(
        self,
        src_paths: list[Path],
        dst_path: Path,
        renderer: OcioConfigRenderer,
    ):
        pass

    def to_dict(self) -> dict:
        asdict = dataclasses.asdict(self)
        return asdict

    @classmethod
    def from_dict(cls, as_dict: dict) -> "BaseGenerator":
        return cls(**as_dict)


@dataclasses.dataclass
class GeneratorExposureBands(BaseGenerator):
    # 0-1 range, percentage of image width
    band_offset: float = 0.0

    shortname: ClassVar[str] = "exposures"
    description: ClassVar[str] = "generate bands of gradually increasing exposure"

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
        src_paths: list[Path],
        dst_path: Path,
        renderer: OcioConfigRenderer,
    ):
        src_path = src_paths[0]
        look_str = f", look='{renderer.look}'" if renderer.look else ""
        ocio_command = renderer.to_oiiotool_command()
        text_left = f"{src_path.stem} - {renderer.name}"
        text_right = f"(display='{renderer.display}', view='{renderer.view}'{look_str})"
        self._run(
            src_path=src_path,
            dst_path=dst_path,
            ocio_command=ocio_command,
            text_left=text_left,
            text_right=text_right,
        )


@dataclasses.dataclass
class GeneratorFull(BaseGenerator):
    """
    Render the full size of the image with a legend in a bottom footer.
    """

    max_height: int

    shortname: ClassVar[str] = "full"
    description: ClassVar[str] = "render the whole area of the image and resize it"

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
        src_paths: list[Path],
        dst_path: Path,
        renderer: OcioConfigRenderer,
    ):
        src_path = src_paths[0]
        look_str = f", look='{renderer.look}'" if renderer.look else ""
        ocio_command = renderer.to_oiiotool_command()
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


@dataclasses.dataclass
class GeneratorCombined(BaseGenerator):
    """
    A method of generating an image with oiiotool.
    """

    shortname: ClassVar[str] = "__combined__"
    description: ClassVar[str] = ""

    def run(
        self,
        src_paths: list[Path],
        dst_path: Path,
        renderer: OcioConfigRenderer | None = None,
    ):
        command = oiiotool_export_auto_mosaic(
            image_paths=src_paths,
            dst_path=dst_path,
        )
        LOGGER.debug(f"subprocess.run({command})")
        subprocess.run(command)


for subclass in BaseGenerator.__subclasses__():
    assert subclass.shortname != BaseGenerator.shortname
    assert subclass.description != BaseGenerator.description


GENERATORS = [
    GeneratorExposureBands,
    GeneratorFull,
    GeneratorCombined,
]
_GENERATORS_BY_SHORTNAME = {gen.shortname: gen for gen in GENERATORS}


@dataclasses.dataclass(frozen=True)
class ComparisonRender:
    generator: BaseGenerator
    renderer: OcioConfigRenderer | None
    src_paths: list[Path]
    dst_path: Path

    def run(self):
        self.generator.run(self.src_paths, self.dst_path, self.renderer)

    def to_dict(self) -> dict:
        asdict = {
            "dst_path": str(self.dst_path),
            "src_paths": [str(path) for path in self.src_paths],
            "renderer": self.renderer.to_dict(),
            "generator": (
                self.generator.shortname,
                self.generator.to_dict(),
            ),
        }
        return asdict

    @classmethod
    def from_dict(cls, as_dict: dict) -> "ComparisonRender":
        generator = _GENERATORS_BY_SHORTNAME[as_dict["generator"][0]]
        generator = generator.from_dict(as_dict["generator"][1])
        renderer = OcioConfigRenderer.from_dict(as_dict["renderer"])
        src_paths = [Path(path) for path in as_dict["src_paths"]]
        dst_path = Path(as_dict["dst_path"])
        return cls(
            generator=generator,
            renderer=renderer,
            src_paths=src_paths,
            dst_path=dst_path,
        )


@dataclasses.dataclass
class ComparisonSession:

    asset: ImageAsset
    renders: list[ComparisonRender] = dataclasses.field(default_factory=list)

    def add_render(self, render: ComparisonRender):
        self.renders.append(render)

    def to_dict(self) -> dict:
        asdict = {
            "asset": str(self.asset.json_path),
            "renders": [render.to_dict() for render in self.renders],
        }
        return asdict

    @classmethod
    def from_dict(cls, as_dict: dict) -> "ComparisonSession":
        asset = ImageAsset(Path(as_dict["asset"]))
        renders = [ComparisonRender.from_dict(render) for render in as_dict["renders"]]
        return cls(
            asset=asset,
            renders=renders,
        )

    @classmethod
    def from_json(cls, json_str: str) -> "ComparisonSession":
        as_dict = json.loads(json_str)
        return cls.from_dict(as_dict)

    def to_json(self, **json_kwargs) -> str:
        asdict = self.to_dict()
        return json.dumps(asdict, **json_kwargs)
