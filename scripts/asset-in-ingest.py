"""
Generates the images stored in '{root}/assets' by processing the untracked images in '{root}/.assets-in'.

The processing implies optimization and uniformization.
"""

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

import lxmpicturelab
from lxmpicturelab.browse import ASSET_DIR
from lxmpicturelab.browse import ASSET_IN_DIR
from lxmpicturelab.browse import WORKBENCH_DIR
from lxmpicturelab.utils import timeit
from lxmpicturelab.download import download_file
from lxmpicturelab.browse import ImageryAsset

# to upgrade at each code change that affect the data writen to the output image
__version__ = f"2-{lxmpicturelab.__version__}"

LOGGER = logging.getLogger(__name__)

OIIOTOOL_PATH = Path(shutil.which("oiiotool"))
assert OIIOTOOL_PATH.exists()

WORKBENCH_DIR.mkdir(exist_ok=True)
WORK_DIR = WORKBENCH_DIR / "asset-in-ingest"

# // editables globals:

OVERWRITE_EXISTING: bool = True

# - file without colorspace are assumed to be already ACES2065-1
# - colorspace value must be a name found in the ACES studio-config v2.0.0
ASSETS_IN: dict[Path, str | None] = {
    ASSET_IN_DIR / "CAaf-Z37-legomovie.json": None,
    ASSET_IN_DIR / "CAlc-D8T-dragon.json": None,
    ASSET_IN_DIR / "CAtm-FGH-specbox.json": None,
    ASSET_IN_DIR / "CGts-W0L-sweep.json": "Linear Rec.709 (sRGB)",
    ASSET_IN_DIR / "PAds-4HS-testbench.json": None,
    ASSET_IN_DIR / "PAfl-H6O-night.json": None,
    ASSET_IN_DIR / "PAfl-IP1-candle.json": None,
    ASSET_IN_DIR / "PAfl-UY7-garden.json": None,
    ASSET_IN_DIR / "PAfm-SWE-neongirl.json": None,
    ASSET_IN_DIR / "PAmsk-8BB-bluebar.json": None,
    ASSET_IN_DIR / "PAmsk-R65-christmas.json": None,
    ASSET_IN_DIR / "PAtm-2QQ-space.json": None,
    ASSET_IN_DIR / "PAtm-B2W-fire.json": None,
    ASSET_IN_DIR / "PWarr-VWE-helenjohn.json": "ARRI LogC4",
    ASSET_IN_DIR / "PWsjw-7QC-watchmaker.json": None,
    ASSET_IN_DIR / "PWsjw-90G-icecave.json": None,
    ASSET_IN_DIR / "PWsjw-FCC-closeman.json": None,
    ASSET_IN_DIR / "PWsjw-LE4-alpinist.json": None,
    ASSET_IN_DIR / "PAac-B01-skins.json": None,
    ASSET_IN_DIR / "PAkp-4DO-bluehand.json": None,
    ASSET_IN_DIR / "PAjg-MZY-nightstreet.json": None,
    ASSET_IN_DIR / "Cblr-GFD-spring.json": "Linear Rec.709 (sRGB)",
    ASSET_IN_DIR / "PWdc-85R-braidmaker.json": None,
    ASSET_IN_DIR / "PPry-00M-mountain.json": None,
    ASSET_IN_DIR / "PWdac-11H-ngohaiha.json": None,
}


def optimize_asset(
    source_asset: ImageryAsset,
    target_path: Path,
    ocio_config_path: Path,
    source_ocio_colorspace: str | None,
    dst_ocio_colorspace: str = "ACES2065-1",
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


def ingest_assets(
    assets_config: dict[Path, str | None],
    work_dir: Path,
    dst_dir: Path,
    overwrite_existing: bool = False,
):
    """
    Run the ingest process for all the given assets.

    Args:
        assets_config: assets to ingest as {"asset path": "ocio colorspace name"}
        work_dir: filesystem path to a directory that may exist. Used to write intermediate resources to.
        dst_dir: fileystem path to a directory that may exist. Used to write the ingested assets to.
        overwrite_existing: True to force ingest assets which already exists in target_dir
    """
    ocio_config_url = "https://github.com/AcademySoftwareFoundation/OpenColorIO-Config-ACES/releases/download/v2.1.0-v2.2.0/studio-config-v2.1.0_aces-v1.3_ocio-v2.1.ocio"
    ocio_config_name = ocio_config_url.split("/")[-1]
    ocio_config_path = work_dir / ocio_config_name

    if not ocio_config_path.exists():
        work_dir.mkdir(exist_ok=True)
        LOGGER.info(f"downloading ACES OCIO config to '{ocio_config_path}'")
        download_file(ocio_config_url, ocio_config_path)
    else:
        LOGGER.info(f"found existing ACES OCIO config at '{ocio_config_path}'")

    if overwrite_existing and dst_dir.exists():
        LOGGER.debug(f"rmtree({dst_dir})")
        shutil.rmtree(dst_dir)
    dst_dir.mkdir(exist_ok=True)

    LOGGER.info(f"optimizing {len(assets_config)} assets ...")
    for index, (src_asset_path, colorspace) in enumerate(assets_config.items()):
        prefix = f"[{index+1:0>2}/{len(assets_config):0>2}]"

        src_asset = ImageryAsset(src_asset_path)
        dst_asset_dir = dst_dir / src_asset.identifier
        dst_asset = src_asset.with_root_path(dst_asset_dir)

        if dst_asset_dir.exists() and not overwrite_existing:
            LOGGER.info(f"{prefix} ❎ skipping existing asset '{dst_asset.identifier}'")
            continue

        dst_asset_dir.mkdir(exist_ok=True)
        dst_path = dst_asset.json_path.with_suffix(".exr")

        LOGGER.info(f"{prefix} 💫 optimizing '{dst_path.name}'")
        with timeit(f"{prefix} ✅ finished '{dst_path}' in ", LOGGER.info):
            optimize_asset(
                source_asset=src_asset,
                target_path=dst_path,
                ocio_config_path=ocio_config_path,
                source_ocio_colorspace=colorspace,
            )
            shutil.copy(src_asset.json_path, dst_asset.json_path)


if __name__ == "__main__":
    lxmpicturelab.configure_logging()
    with timeit("main() finished in ", LOGGER.info):
        ingest_assets(
            assets_config=ASSETS_IN,
            work_dir=WORK_DIR,
            dst_dir=ASSET_DIR,
            overwrite_existing=OVERWRITE_EXISTING,
        )
