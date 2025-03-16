"""
Generates sets which are combination of multiple assets.
"""

import abc
import dataclasses
import json
import logging
import math
import runpy
import shutil
import subprocess
from pathlib import Path
from typing import Any
from typing import Callable

import lxmpicturelab
from lxmpicturelab.browse import ImageryAsset
from lxmpicturelab.browse import SETS_DIR
from lxmpicturelab.browse import get_imagery_assets
from lxmpicturelab.oiiotoolio import oiiotool_export
from lxmpicturelab.utils import timeit

THISDIR = Path(__file__).parent

LOGGER = logging.getLogger(__name__)

OIIOTOOL_PATH = Path(shutil.which("oiiotool"))
assert OIIOTOOL_PATH.exists()

ASSET_INGEST_PATH = THISDIR / "asset-in-ingest.py"
_ASSET_INGEST = runpy.run_path(str(ASSET_INGEST_PATH), run_name="__passthrough__")
# to upgrade at each code change that affect the data writen to the output image
__version__ = f"3-{_ASSET_INGEST['__version__']}"

OVERWRITE_EXISTING = True


@dataclasses.dataclass
class SetVariant(abc.ABC):

    identifier: str
    bg_color: tuple[float, float, float]
    asset_sorter: Callable[[ImageryAsset], Any] | None = None
    asset_filter: Callable[[ImageryAsset], bool] | None = None

    def get_assets(self, root_dir: Path = None) -> list[ImageryAsset]:
        assets = get_imagery_assets(root_dir)
        if self.asset_filter:
            assets = filter(self.asset_filter, assets)
        if self.asset_sorter:
            assets = sorted(assets, key=self.asset_sorter)
        return assets


def _sort_assets_color(asset: ImageryAsset):
    return asset.metadata.type.value, asset.metadata.primary_color, asset.identifier


SET_VARIANTS = [
    SetVariant(
        identifier="al.sorted-color.bg-black",
        bg_color=(0, 0, 0),
        asset_sorter=_sort_assets_color,
    ),
    SetVariant(
        identifier="al.sorted-color.bg-midgrey",
        bg_color=(0.18, 0.18, 0.18),
        asset_sorter=_sort_assets_color,
    ),
]


def generate_mosaic(
    assets: list[ImageryAsset],
    target_path: Path,
    mosaic_columns: int = 5,
    tile_width: int = 1102,
    tile_height: int = 752,
    mosaic_gap_size: int = 20,
    margins: int = 20,
    background_color: tuple[float, float, float] = (0, 0, 0),
):
    """

    Args:
        background_color:
        assets: list of image asset to build the mosaic with
        target_path: filesystem path to the mosaic file to write to
        mosaic_columns: max number of columns
        tile_height: width each image (tile) must be fitted in
        tile_width: height each image (tile) must be fitted in
        mosaic_gap_size: internal gap in pixels between each tile of the mosaic
        margins: space in pixels between the border of the image and the tiles
    """
    header_height = 150
    header_disclaimer_txt = "all images belongs to their respective owner, credits viewable in the metadata."
    bg_color = ",".join(map(str, background_color))

    if len(assets) <= mosaic_columns:
        tiles_w, tiles_h = (len(assets), 1)
    else:
        tiles_w = mosaic_columns
        tiles_h = math.ceil(len(assets) / mosaic_columns)

    command: list[str] = [str(OIIOTOOL_PATH)]
    for asset in assets:
        command += [
            "-i",
            str(asset.image_path),
            "--fit:filter=cubic",
            f"{tile_width}x{tile_height}",
            "--ch",
            "R,G,B,A=1.0",
            # bottom-left text with 30px margin
            "--text:x={TOP.x+30}:y={TOP.height+TOP.y-15}:shadow=4",
            f"{asset.identifier}",
            # have the data-window cover the display-window
            "--croptofull",
        ]

    # processing
    command += [
        f"--mosaic:pad={mosaic_gap_size}",
        f"{tiles_w}x{tiles_h}",
        f"--cut",
        f"{{TOP.width+{margins * 2}}}x{{TOP.height+{margins * 2 + header_height}}}-{margins}-{margins + header_height}",
        "--ch",
        "R,G,B,A",
    ]
    command += [
        "--create",
        "{TOP.width}x{TOP.height}",
        "4",
        f"--fill:color={bg_color},1.0",
        "{TOP.width}x{TOP.height}",
        "--over",
    ]
    command += [
        f"--text:x={margins}:y=60:size=45",
        f"{target_path.stem}",
        f"--text:x={margins}:y=95:size=25:color=0.4,0.4,0.4",
        header_disclaimer_txt,
    ]
    # metadata
    author_by_file = {asset.identifier: asset.metadata.authors for asset in assets}
    context_by_file = {asset.identifier: asset.metadata.context for asset in assets}
    command += [
        "--evaloff",
        "--wildcardoff",
        "--attrib",
        "sheet/authors",
        str(json.dumps(author_by_file)),
        "--attrib",
        "sheet/context",
        str(json.dumps(context_by_file)),
        "--attrib",
        f"{lxmpicturelab.METADATA_PREFIX}/__version__",
        __version__,
        "--attrib",
        "ColorSpace",
        "ACES2065-1",
        "--attrib",
        "colorspace",
        "ACES2065-1",
        "--attrib:type=float[8]",
        "chromaticities",
        "0.7347,0.2653,0.0,1.0,0.0001,-0.077,0.32168,0.33767",
    ]
    command += oiiotool_export(
        target_path,
        bitdepth="float",
        compression="zips",
    )
    LOGGER.debug(f"subprocess.run({' '.join(command)})")
    subprocess.run(command)


def generate_preview(
    mosaic_path: Path,
    target_path: Path,
    jpeg_compression: int = 70,
    jpeg_subsampling: str = "4:4:4",
):
    command: list[str] = [
        str(OIIOTOOL_PATH),
        str(mosaic_path),
    ]
    command += [
        # we assume OpenImageIO has been compiled with OCIO support
        "--colorconvert",
        "aces2065_1",
        "g22_encoded_rec709",
    ]
    command += [
        "--ch",
        "R,G,B",
        "--attrib",
        "jpeg:subsampling",
        jpeg_subsampling,
    ]
    command += oiiotool_export(
        target_path,
        bitdepth="uint8",
        compression=f"jpeg:{jpeg_compression}",
    )
    LOGGER.debug(f"subprocess.run({' '.join(command)})")
    subprocess.run(command, check=True)


def main(
    dst_dir: Path,
    variants: list[SetVariant],
    overwrite_existing: bool = False,
):

    if overwrite_existing and dst_dir.exists():
        LOGGER.debug(f"rmtree({dst_dir})")
        shutil.rmtree(dst_dir)
    dst_dir.mkdir(exist_ok=True)

    for index, variant in enumerate(variants):

        prefix = f"[{index + 1:0>2}/{len(variants):0>2}]"

        assets = variant.get_assets()
        bg_color = variant.bg_color
        variant_name = variant.identifier
        variant_dir = dst_dir / variant_name

        if variant_dir.exists() and not overwrite_existing:
            LOGGER.info(f"{prefix} ❎ skipping existing set '{variant_name}'")
            continue

        variant_dir.mkdir(exist_ok=True)

        mosaic_name = f"lxmpicturelab-set.{variant_name}.{__version__}.exr"
        mosaic_path = variant_dir / mosaic_name

        LOGGER.info(
            f"💫 generating mosaic from {len(assets)} assets to '{mosaic_path}'"
        )
        with timeit(f"{prefix} ✅ generation took ", LOGGER.info):
            generate_mosaic(
                assets=assets,
                target_path=mosaic_path,
                background_color=bg_color,
            )
            preview_path = mosaic_path.with_suffix(".jpg")
            generate_preview(
                mosaic_path=mosaic_path,
                target_path=preview_path,
            )


if __name__ == "__main__":
    lxmpicturelab.configure_logging()
    with timeit("main() finished in ", LOGGER.info):
        main(
            dst_dir=SETS_DIR,
            variants=SET_VARIANTS,
            overwrite_existing=OVERWRITE_EXISTING,
        )
