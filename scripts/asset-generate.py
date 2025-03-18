import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

import lxmpicturelab
from lxmpicturelab.browse import ASSET_DIR
from lxmpicturelab.browse import WORKBENCH_DIR
from lxmpicturelab.download import download_file
from lxmpicturelab.browse import ImageAsset

# to upgrade at each code change that affect the data writen to the output image
__version__ = f"2-{lxmpicturelab.__version__}"

LOGGER = logging.getLogger(Path(__file__).stem)

OIIOTOOL_PATH = Path(shutil.which("oiiotool"))
assert OIIOTOOL_PATH.exists()

WORKBENCH_DIR.mkdir(exist_ok=True)
WORK_DIR = WORKBENCH_DIR / "asset-in-ingest"


def optimize_asset(
    source_asset: ImageAsset,
    target_path: Path,
    ocio_config_path: Path,
    source_ocio_colorspace: str | None,
    dst_ocio_colorspace: str = "ACES2065-1",
    color_matrix: list[float] = None,
    max_width: int = 2204,
    max_height: int = 1504,
):
    """
    Create an optimized OpenEXR out of the given source ImageryAsset.

    Optimized imply:

    - 3 R,G,B channels only
    - converted to ACES2065-1 primaries/whitepoint
    - proper colorspace metadata
    - copy asset .json metadata to exr metadata
    - not wider than a given maximum width
    - plates are 16bit half float and CGI is 32bit float

    Args:
        source_asset:
        target_path:
        ocio_config_path: filesystem path to an existing .ocio config
        source_ocio_colorspace: colorspace name in given ocio config
        dst_ocio_colorspace: colorspace name in given ocio config
        color_matrix: optional 3x3 matrix to perform color-conversion
        max_width: in pixels
        max_height: in pixels
    """
    asset_metadata: dict = source_asset.metadata.to_dict()

    command = [
        str(OIIOTOOL_PATH),
        str(source_asset.image_path),
    ]

    # call oiiotool a first time to retrieve the image width/height
    # (we could have used --if condition with OIIO>2.4)
    size_command = command + ["--echo", "{TOP.width}", "--echo", "{TOP.height}"]
    LOGGER.debug(f"subprocess.run({size_command!r})")
    asset_size = subprocess.check_output(size_command, text=True)
    asset_size = asset_size.split("\n")
    asset_width = int(asset_size[0])
    asset_height = int(asset_size[1])

    # strip alpha and other extra channels
    command += [
        "--ch",
        "R,G,B",
    ]

    if color_matrix:
        _color_matrix = ",".join(map(str, color_matrix))
        LOGGER.debug(f"[optimize] using color-matrix '{_color_matrix}'")
        command += [
            "--ccmatrix:transpose=1",
            _color_matrix,
        ]

    # color conversion with OCIO
    if source_ocio_colorspace:
        LOGGER.debug(
            f"[optimize] using color-conversion "
            f"'{source_ocio_colorspace}'>'{dst_ocio_colorspace}'"
        )
        command += [
            "--colorconfig",
            str(ocio_config_path),
            "--colorconvert",
            source_ocio_colorspace,
            dst_ocio_colorspace,
        ]

    # rescale if larger than max_width/max_height
    command += [
        "--fit:filter=cubic",
        f"{min(asset_width, max_width)}x{min(asset_height, max_height)}",
        # reset display windows to data window
        "--fullpixels",
        "--origin",
        "+0+0",
        "--fullsize",
        "+0+0",
    ]

    # OpenEXR configuration
    # XXX: plates being generated from integer-based data we allow a lower bitdepth
    bitdepth = "half" if source_asset.is_plate else "float"
    command += [
        "-d",
        bitdepth,
        "--compression",
        "zip",
    ]
    # metadata
    command += [
        "--evaloff",
        "--wildcardoff",
        "--attrib",
        "ColorSpace",
        dst_ocio_colorspace,
        "--attrib",
        "colorspace",
        dst_ocio_colorspace,
        "--attrib:type=float[8]",
        "chromaticities",
        "0.7347,0.2653,0.0,1.0,0.0001,-0.077,0.32168,0.33767",
        "--attrib",
        f"{lxmpicturelab.METADATA_PREFIX}/__version__",
        __version__,
    ]
    for metadata_name, metadata_value in asset_metadata.items():
        command += [
            "--attrib",
            f"{lxmpicturelab.METADATA_PREFIX}/{metadata_name}",
            json.dumps(metadata_value),
        ]
    # output
    command += [
        "-o",
        str(target_path),
    ]
    environ = os.environ.copy()
    environ["OCIO"] = str(ocio_config_path)
    LOGGER.debug(f"subprocess.run({command!r})")
    subprocess.run(command, check=True, env=environ)


def build_ocio_config(dst_dir: Path) -> Path:
    """
    Download the OCIO config for colrospace conversion with oiiotool.
    """
    config_url = "https://github.com/AcademySoftwareFoundation/OpenColorIO-Config-ACES/releases/download/v2.1.0-v2.2.0/studio-config-v2.1.0_aces-v1.3_ocio-v2.1.ocio"
    config_name = config_url.split("/")[-1]
    config_path = dst_dir / config_name

    if config_path.exists():
        LOGGER.debug(f"found existing config at '{config_path}'; skipping")
        return config_path

    LOGGER.debug(f"downloading config to '{config_path}'")
    download_file(config_url, config_path)
    return config_path


def get_cli(argv: list[str] | None = None) -> argparse.Namespace:
    argv = argv or sys.argv[1:]
    parser = argparse.ArgumentParser(
        description="Run the ingest process on the given asset."
    )
    parser.add_argument(
        "src_path",
        type=Path,
        help="Filesystem path to an existing asset .json file.",
    )
    parser.add_argument(
        "--colorspace",
        type=str,
        default=None,
        help=(
            "Colorspace encoding of the exr if not already ACES2065-1."
            "Colorspace name must be found in the ACES studio-config v2.0.0."
        ),
    )
    parser.add_argument(
        "--color-matrix",
        type=str,
        default=None,
        help=(
            "Peform manual color-conversion to ACES2065-1 by using a 3x3 color matrix."
        ),
    )
    parser.add_argument(
        "--overwrite-existing",
        action="store_true",
        help="If specified, existing assets will be overwritten.",
    )
    parsed = parser.parse_args(argv)
    return parsed


def main(argv: list[str] | None = None):

    cli = get_cli(argv)
    u_src_path: Path = cli.src_path
    u_colorspace: str | None = cli.colorspace
    u_overwrite_existing: bool = cli.overwrite_existing
    u_color_matrix: str | None = cli.color_matrix

    color_matrix = None
    if u_color_matrix:
        color_matrix = [float(i) for i in u_color_matrix.split(",")]
        if not len(color_matrix) == 3 * 3:
            print(
                f"Invalid color matrix: expected 3x3, got {color_matrix}",
                file=sys.stderr,
            )
            sys.exit(1)

    src_asset = ImageAsset(u_src_path)
    dst_dir = ASSET_DIR / src_asset.identifier
    dst_asset = src_asset.with_root_path(dst_dir)

    prefix = f"({src_asset.identifier})"

    if dst_asset.json_path.exists() and not u_overwrite_existing:
        LOGGER.info(f"⏩ {prefix} found existing asset; skipping")
        return

    LOGGER.info(f"🔨 {prefix} building ocio config to '{WORK_DIR}'")
    ocio_config_path = build_ocio_config(dst_dir=WORK_DIR)

    if dst_dir.exists():
        LOGGER.debug(f"rmtree({dst_dir})")
        shutil.rmtree(dst_dir)
    dst_dir.mkdir(exist_ok=True)

    dst_path = dst_asset.json_path.with_suffix(".exr")
    LOGGER.info(f"💫 {prefix} optimizing to '{dst_path}'")
    optimize_asset(
        source_asset=src_asset,
        target_path=dst_path,
        ocio_config_path=ocio_config_path,
        source_ocio_colorspace=u_colorspace,
        color_matrix=color_matrix,
    )
    LOGGER.debug(f"copy({src_asset.json_path}, {dst_asset.json_path})")
    shutil.copy(src_asset.json_path, dst_asset.json_path)
    LOGGER.info(f"✅ {prefix} finished")


if __name__ == "__main__":
    lxmpicturelab.configure_logging()
    main()
