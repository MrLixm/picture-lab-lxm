import argparse
import contextlib
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Generator

import numpy
import rawpy._rawpy as rawpy
import OpenImageIO as oiio

from lxmpicturelab import configure_logging
from lxmpicturelab import METADATA_PREFIX

LOGGER = logging.getLogger(__name__)


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
        "-o",
        str(dst_path),
        str(src_path),
    ]
    LOGGER.debug(f"subprocess.run({command})")
    subprocess.run(command)


def get_cli(argv: list[str] | None = None) -> argparse.Namespace:
    argv = argv or sys.argv[1:]
    parser = argparse.ArgumentParser(description="Debayer a camera raw file to EXR.")
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
        help="Amount of exposure in stops, to increase the debayered image by.",
    )
    parsed = parser.parse_args(argv)
    return parsed


def main():
    cli = get_cli()
    src_path: Path = cli.src_path
    dng_converter: Path | None = cli.adobe_dng_converter
    u_exposure: float = cli.exposure
    u_dst_path: Path | None = cli.dst_path

    dst_path: Path = u_dst_path or src_path.with_suffix(".exr")
    dng_path: Path | None = None
    dst_bitdepth = "half"
    dst_compression = "zips"
    debayering_options = rawpy.Params(
        output_bps=16,
        output_color=rawpy.ColorSpace.XYZ,
        no_auto_bright=True,
        gamma=(1.0, 1.0),
        demosaic_algorithm=rawpy.DemosaicAlgorithm.DHT,
        median_filter_passes=0,
        fbdd_noise_reduction=rawpy.FBDDNoiseReductionMode.Off,
        use_camera_wb=True,
    )

    # check if rawpy can read the raw file
    try:
        rawpyread(src_path)
    except rawpy.LibRawDataError:
        LOGGER.info(
            f"Cannot open file {src_path.name} with rawpy; DNG conversion required."
        )
        if not dng_converter:
            print(
                "ERROR: No Adobe DNG converter executable specified.",
                file=sys.stderr,
            )
            sys.exit(1)

        dng_path = src_path.with_suffix(".dng")
        LOGGER.debug(f"generating dng to '{dng_path}'")
        convert_to_dng(src_path, dng_path, dng_converter)
        src_path = dng_path

    LOGGER.info(f"💿 reading '{src_path}'")
    with rawpyread(src_path) as raw_file:
        rgb: numpy.ndarray = raw_file.postprocess(params=debayering_options)

    if dng_path and dng_path.exists():
        LOGGER.debug(f"unlink({dng_path})")
        dng_path.unlink()

    LOGGER.info(f"💫 processing raw ...")
    exposure = 2**u_exposure
    buf = oiio.ImageBuf(rgb)
    buf = oiio.ImageBufAlgo.mul(buf, exposure)

    # https://www.colour-science.org:8010/apps/rgb_colourspace_transformation_matrix?input-colourspace=CIE+XYZ-D65+-+Scene-referred&output-colourspace=ACES2065-1&chromatic-adaptation-transform=CAT02&formatter=opencolorio&decimals=6
    # fmt: off
    xyz_to_ap0 = [
        [+1.009732, +0.008407, -0.018139, 0.0],
        [-0.469470, +1.371110, +0.098360, 0.0],
        [-0.000318, -0.001037, +1.001356, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    # fmt: on
    # OIIO need it transposed
    xyz_to_ap0_t = numpy.transpose(xyz_to_ap0).tolist()
    # flatten as 1D list
    xyz_to_ap0_t = [b for a in xyz_to_ap0_t for b in a]
    buf = oiio.ImageBufAlgo.colormatrixtransform(buf, xyz_to_ap0_t)

    # set metadata
    raw_spec: oiio.ImageSpec = oiio.ImageInput.open(str(src_path)).spec()
    for extra_attrib in raw_spec.extra_attribs:
        buf.specmod().attribute(
            extra_attrib.name, extra_attrib.type, extra_attrib.value
        )
    buf.specmod().attribute("compression", dst_compression)
    buf.specmod().attribute(f"{METADATA_PREFIX}/debayer-exposure", u_exposure)

    if buf.has_error:
        print(
            f"OIIO ERROR: current ImageBuf has errors: {buf.geterror()}",
            file=sys.stderr,
        )
        sys.exit(1)

    LOGGER.info(f"💾 writing '{dst_path}'")
    buf.write(str(dst_path), dst_bitdepth)


if __name__ == "__main__":
    configure_logging()
    main()
