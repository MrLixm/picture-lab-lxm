import logging
import math
import shutil
from pathlib import Path

LOGGER = logging.getLogger(__name__)


OIIOTOOL = Path(shutil.which("oiiotool"))
# if raises, means problem with dependencies python venv
assert OIIOTOOL.exists()


def oiiotool_export(
    target_path: Path,
    bitdepth: str,
    compression: str = None,
    srgb_encoded: bool = False,
) -> list[str]:
    """
    Create the arguments required to export an image.

    Those are usually concatenated last with the other arguments.

    Args:
        target_path:
        bitdepth: depends on the image format
        compression: depends on the image format
        srgb_encoded: True to apply the sRGB transfer-function.

    Returns:
        partial oiiotool command
    """
    command = ["-d", bitdepth]
    if srgb_encoded:
        command += ["--colorconvert", "linear", "sRGB"]
    if compression:
        command += ["--compression", compression]
    command += ["-o", str(target_path)]
    return command


def oiiotool_ocio_display_convert(
    config: Path,
    src_colorspace: str,
    display: str,
    view: str,
    look: str | None = None,
) -> list[str]:
    """
    Apply an OCIO display conversion.

    Args:
        config: filesystem path to an existing OCIO config file.
        src_colorspace: name of the colorspace the image stack is encoded in.
        display: name of the display to use.
        view: name of the OCIO view to use with the given display
        look: optional name of the OCIO look to use

    Returns:
         a partial oiiotool command.
    """
    command = [
        "--colorconfig",
        str(config),
    ]
    if look:
        command += [
            f'--ociolook:from="{src_colorspace}":to="{src_colorspace}"',
            look,
        ]
    command += [
        f'--ociodisplay:from="{src_colorspace}"',
        display,
        view,
    ]
    return command


def oiiotool_generate_expo_bands(
    src_path: Path,
    band_number: int = 7,
    band_exposure_offset: int = 2,
    band_width: float = 0.3,
    band_x_offset: float = 0.0,
    band_extra_args: list[str] = None,
) -> list[str]:
    """
    Render a width section of the given image with different exposure offsets.

    Args:
        src_path: filesytem path to the source image.
        band_number: number of band to generate.
        band_exposure_offset: amount of exposure to change between each band.
        band_width: width in pixels of the band.
        band_x_offset:
            percentage of the image width to offset horizontally the band by, 0-1 range.
        band_extra_args:
            optional oiiotool extra arguments to apply on each individual band
            (before text is rendered).

    Returns:
        a partial oiiotool command that create the mosaic bands
    """
    band_extra_args = band_extra_args or []

    if band_number % 2 == 0:
        raise ValueError(f"band_number can only be an odd number; got {band_number}")

    command = []

    middle_index = math.ceil(band_number / 2)
    limits = band_exposure_offset * (middle_index - 1)
    bands: list[int] = list(range(limits * -1, limits + 1, band_exposure_offset))
    for band_exposure in bands:
        command += [
            "-i",
            str(src_path),
            "--cut",
            f"{{TOP.width//{1 / band_width:.2f}}}x{{TOP.height}}+{{TOP.width//{1 / band_x_offset:.2f}}}+0",
            "--mulc",
            str(round(2**band_exposure, 2)),
        ]
        command += band_extra_args
        command += [
            "--text:x={TOP.width/2}:y={TOP.height-25}:shadow=4:size=44:color=1,1,1,1",
            f"{band_exposure:+}",
        ]
    command += [
        "--mosaic",
        f"{len(bands)}x1",
    ]
    return command


def oiiotool_auto_mosaic(image_number: int) -> list[str]:
    """
    Create a mosaic of the curret image stack, automatically guessing rows/columns.

    Returns:
        a partial oiiotool command
    """
    columns = math.ceil(math.sqrt(image_number))
    rows = math.ceil(image_number / columns)
    command = [
        "--mosaic",
        f"{columns}x{rows}",
    ]
    return command
