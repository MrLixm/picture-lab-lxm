import argparse
import contextlib
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Generator

import numpy
import rawpy._rawpy as rawpy
import OpenImageIO as oiio

from lxmpicturelab import configure_logging
from lxmpicturelab import METADATA_PREFIX

PROGNAME = Path(__file__).stem
LOGGER = logging.getLogger(PROGNAME)

__VERSION__ = "2"


def errorexit(msg: str, code: int = 1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


@contextlib.contextmanager
def rawpyread(file_path: Path) -> Generator[rawpy.RawPy, None, None]:
    """
    Context to read a raw file with rawpy that handle opening and closing.

    Args:
        file_path: path to an existing raw file supported by rawpy

    Returns:
        RawPy instance of the opened raw file.
    """
    processor = rawpy.RawPy()
    processor.open_file(str(file_path))
    try:
        yield processor
    finally:
        processor.close()


def convert_to_dng(src_path: Path, dst_path: Path, dng_converter: Path):
    # https://helpx.adobe.com/camera-raw/digital-negative.html
    command = [
        str(dng_converter),
        "-u",  # uncompressed
        "-p0",  # JPEG preview size to none
        "-dng1.5",  # arbitrary choice to increase chance of read by libraw
        "-d",
        str(dst_path.parent),
        "-o",
        str(dst_path.name),
        str(src_path),
    ]
    LOGGER.debug(f"subprocess.run({command})")
    subprocess.run(command)
    assert dst_path.exists()


def get_cli(argv: list[str] | None = None) -> argparse.Namespace:
    argv = argv or sys.argv[1:]
    parser = argparse.ArgumentParser(
        description="Debayer a camera raw file to an ACES2065-1 EXR."
    )
    parser.add_argument(
        "src_path",
        type=Path,
        help="Filesystem path to an existing camera raw file.",
    )
    parser.add_argument(
        "--dst-path",
        type=Path,
        default=None,
        help="Filesystem path to a file to write the debayered image to.",
    )
    parser.add_argument(
        "--adobe-dng-converter",
        type=Path,
        default=os.getenv("ADOBE_DNG_CONVERTER"),
        help=(
            "Filesystem path to the Adobe DNG converter executable. "
            "Required if rawpy cannot read the given raw file format."
        ),
    )
    parser.add_argument(
        "--exposure",
        type=float,
        default=2.6,
        help="Amount of exposure in stops, to increase the debayered image by. Vary between camera models.",
    )
    parser.add_argument(
        "--highlights",
        type=int,
        default=0,
        help=(
            "Method to use for highlighting handling: 0=Clip; 1=Ignore; 2=Blend; "
            "3<>9=Reconstruct where low numbers favor whites and higher favor colors."
        ),
    )
    parsed = parser.parse_args(argv)
    return parsed


def main():
    cli = get_cli()
    src_path: Path = cli.src_path
    dng_converter: Path | None = cli.adobe_dng_converter
    u_exposure: float = cli.exposure
    u_dst_path: Path | None = cli.dst_path
    u_highlights: int = cli.highlights

    dst_path: Path = u_dst_path or src_path.with_suffix(".exr")
    dng_path: Path | None = None
    dst_bitdepth = "half"
    dst_compression = "zips"
    debayering_options = rawpy.Params(
        output_bps=16,
        output_color=rawpy.ColorSpace.sRGB,
        no_auto_bright=True,
        gamma=(1.0, 1.0),
        demosaic_algorithm=rawpy.DemosaicAlgorithm.DHT,
        median_filter_passes=0,
        fbdd_noise_reduction=rawpy.FBDDNoiseReductionMode.Off,
        use_camera_wb=True,
        highlight_mode=u_highlights,
    )

    # check if rawpy can read the raw file
    try:
        LOGGER.info(f"💿 reading '{src_path}'")
        with rawpyread(src_path) as raw_file:
            rgb: numpy.ndarray = raw_file.postprocess(params=debayering_options)

        # retrieve original metadata from raw file
        raw_image: oiio.ImageInput = oiio.ImageInput.open(str(src_path))
        raw_metadata: oiio.ParamValueList = raw_image.spec().extra_attribs
        raw_image.close()

    # we need a dng conversion and retry to read
    except rawpy.LibRawDataError:
        LOGGER.info(
            f"Cannot open file' {src_path.name}' with rawpy; DNG conversion required."
        )
        if not dng_converter:
            errorexit("(CLI) No Adobe DNG converter executable specified.")

        with tempfile.TemporaryDirectory(prefix=f"{PROGNAME}-") as tempdir:
            dng_path = Path(tempdir) / src_path.with_suffix(".dng").name
            LOGGER.debug(f"generating dng to '{dng_path}'")
            convert_to_dng(src_path, dng_path, dng_converter)
            src_path = dng_path
            LOGGER.info(f"💿 reading again as dng '{src_path}'")
            with rawpyread(src_path) as raw_file:
                rgb: numpy.ndarray = raw_file.postprocess(params=debayering_options)

            # retrieve original metadata from DNG file
            raw_image: oiio.ImageInput = oiio.ImageInput.open(str(dng_path))
            raw_metadata: oiio.ParamValueList = raw_image.spec().extra_attribs
            raw_image.close()

    LOGGER.info(f"💫 processing raw ...")
    exposure = 2**u_exposure
    buf = oiio.ImageBuf(rgb)
    # convert to float internally else we will have clamped data after mul operation !
    buf = oiio.ImageBufAlgo.copy(buf, convert=oiio.FLOAT)
    buf = oiio.ImageBufAlgo.mul(buf, exposure)

    # https://www.colour-science.org:8010/apps/rgb_colourspace_transformation_matrix?input-colourspace=sRGB&output-colourspace=ACES2065-1&chromatic-adaptation-transform=CAT02&formatter=repr&decimals=6
    # fmt: off
    srgb_to_ap0 = [
        [0.439586, 0.383929, 0.176533],
        [0.089540, 0.814750, 0.095684],
        [0.017387, 0.108739, 0.873821],
        [0.0, 0.0, 0.0, 1.0],
    ]
    # fmt: on
    # OIIO need it transposed
    srgb_to_ap0_t = numpy.transpose(srgb_to_ap0).tolist()
    # flatten as 1D list
    srgb_to_ap0_t = [b for a in srgb_to_ap0_t for b in a]
    buf = oiio.ImageBufAlgo.colormatrixtransform(buf, srgb_to_ap0_t)

    # set metadata
    for extra_attrib in raw_metadata:
        buf.specmod().attribute(
            extra_attrib.name, extra_attrib.type, extra_attrib.value
        )
    buf.specmod().attribute("compression", dst_compression)
    buf.specmod().attribute(f"{METADATA_PREFIX}/debayer-exposure", u_exposure)
    buf.specmod().attribute(f"{METADATA_PREFIX}/debayer-highlights-mode", u_highlights)

    if buf.has_error:
        errorexit(f"(OIIO) current ImageBuf has errors: {buf.geterror()}")

    LOGGER.info(f"💾 writing '{dst_path}'")
    buf.write(str(dst_path), dst_bitdepth)


if __name__ == "__main__":
    configure_logging()
    main()
