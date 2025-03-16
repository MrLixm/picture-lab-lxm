import dataclasses
import json
import logging
from pathlib import Path

from lxmpicturelab.oiiotoolio import oiiotool_ocio_display_convert

LOGGER = logging.getLogger(__name__)


ACES20651_COLORSPACE = "@ACES2065-1@"


def oiiotool_AP0_to_sRGB():
    # https://www.colour-science.org:8010/apps/rgb_colourspace_transformation_matrix?input-colourspace=ACES2065-1&output-colourspace=sRGB&chromatic-adaptation-transform=CAT02&formatter=str&decimals=6
    AP0_TO_SRGB = [
        2.521649,
        -1.136889,
        -0.384918,
        -0.275214,
        1.369705,
        -0.094392,
        -0.015925,
        -0.147806,
        1.163806,
    ]
    return [
        "--ccmatrix:transpose=1",
        ",".join(map(str, AP0_TO_SRGB)),
    ]


@dataclasses.dataclass
class OcioConfigRenderer:
    """
    Indicate how to evaluate an image formation sourced from an OCIO config file.
    """

    name: str
    filename: str
    description: str

    config_path: Path
    # this is a trick because there is more chance an OCIO config includes
    #   a Linear sRGB colorspace than any other.
    srgb_lin: str
    display: str
    view: str
    look: str = ""

    src_colorspace: str = ACES20651_COLORSPACE

    reference_url: str = ""

    def to_oiiotool_command(self) -> list[str]:
        if self.src_colorspace == ACES20651_COLORSPACE:
            command = oiiotool_AP0_to_sRGB()
        else:
            raise NotImplementedError(
                "Only ACES2065-1 encoded data is supported at this time."
            )

        return command + oiiotool_ocio_display_convert(
            config=self.config_path,
            src_colorspace=self.srgb_lin,
            display=self.display,
            view=self.view,
            look=self.look,
        )

    @classmethod
    def from_json(cls, json_str: str) -> "OcioConfigRenderer":
        structure = json.loads(json_str)
        return cls(
            name=structure["name"],
            filename=structure["filename"],
            description=structure["description"],
            config_path=Path(structure["config_path"]),
            srgb_lin=structure["srgb_lin"],
            display=structure["display"],
            view=structure["view"],
            look=structure["look"],
            src_colorspace=structure["src_colorspace"],
            reference_url=structure["reference_url"],
        )

    def to_json(self, **json_kwargs) -> str:
        asdict = dataclasses.asdict(self)
        asdict["config_path"] = str(self.config_path)
        return json.dumps(asdict, **json_kwargs)
