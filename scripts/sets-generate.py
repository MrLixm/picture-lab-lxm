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
from lxmpicturelab.browse import ASSET_DIR
from lxmpicturelab.browse import SETS_DIR
from lxmpicturelab.browse import get_asset
from lxmpicturelab.asset import AssetMetadata
from lxmpicturelab.asset import ImageAsset
from lxmpicturelab.asset import AssetPrimaryColor
from lxmpicturelab.asset import AssetType
from lxmpicturelab.oiiotoolio import oiiotool_export
from lxmpicturelab.utils import timeit

THISDIR = Path(__file__).parent

LOGGER = logging.getLogger(Path(__file__).stem)

OIIOTOOL_PATH = Path(shutil.which("oiiotool"))
assert OIIOTOOL_PATH.exists()

ASSET_INGEST_PATH = THISDIR / "asset-generate.py"
_ASSET_INGEST = runpy.run_path(str(ASSET_INGEST_PATH), run_name="__passthrough__")
# to upgrade at each code change that affect the data writen to the output image
__version__ = f"8-{_ASSET_INGEST['__version__']}"

OVERWRITE_EXISTING = True


@dataclasses.dataclass
class SetVariant(abc.ABC):

    identifier: str
    description: str
    bg_color: tuple[float, float, float]
    asset_ids: list[str]
    asset_sorter: Callable[[ImageAsset], Any] | None = None

    def get_assets(self, root_dir: Path) -> list[ImageAsset]:
        assets = [get_asset(assetid, root_dir) for assetid in self.asset_ids]
        if self.asset_sorter:
            assets = sorted(assets, key=self.asset_sorter)
        return assets


def _sort_assets_color(asset: ImageAsset):
    return asset.metadata.type.value, asset.metadata.primary_color, asset.identifier


ALL_ASSETS = [
    "CAaf-Z37-legomovie",
    "CAlc-D8T-dragon",
    "CAtm-FGH-specbox",
    "Cblr-GFD-spring",
    "CGts-W0L-sweep",
    "PAac-B01-skins",
    "PAds-4HS-testbench",
    "PAfl-H6O-night",
    # "PAfl-IP1-candle",
    "Pbri-H34-sunflower",
    "PAfl-UY7-garden",
    "PAfm-SWE-neongirl",
    "PAjg-MZY-nightstreet",
    "PAkp-4DO-bluehand",
    "PAmsk-8BB-bluebar",
    "PAmsk-R65-christmas",
    "PAtm-2QQ-space",
    "Pgra-O1K-snowfire",
    "PPry-00M-mountain",
    "PWarr-VWE-helenjohn",
    "PWdac-11H-ngohaiha",
    "PWdc-85R-braidmaker",
    "PWsjw-7QC-watchmaker",
    "PWsjw-90G-icecave",
    "PWsjw-FCC-closeman",
    "PWsjw-LE4-alpinist",
]

SET_VARIANTS = [
    SetVariant(
        identifier="lxmpicturelab.al.sorted-color.bg-black",
        description="A collection of heterogeneous images from various physical or virtual capture devices.",
        bg_color=(0, 0, 0),
        asset_ids=ALL_ASSETS,
        asset_sorter=_sort_assets_color,
    ),
    SetVariant(
        identifier="lxmpicturelab.al.sorted-color.bg-midgrey",
        description=(
            "A collection of heterogeneous images from various physical or virtual "
            "capture devices; with a mid-grey background to affect picture perception."
        ),
        bg_color=(0.18, 0.18, 0.18),
        asset_ids=ALL_ASSETS,
        asset_sorter=_sort_assets_color,
    ),
]


def generate_mosaic(
    dst_asset: ImageAsset,
    src_assets: list[ImageAsset],
    description: str,
    mosaic_columns: int = 5,
    tile_width: int = 1102,
    tile_height: int = 752,
    mosaic_gap_size: int = 20,
    margins: int = 20,
    background_color: tuple[float, float, float] = (0, 0, 0),
):
    """

    Args:
        dst_asset: the asset configuration of the mosaic to create
        src_assets: list of image asset to build the mosaic with
        description:
        mosaic_columns: max number of columns
        tile_height: width each image (tile) must be fitted in
        tile_width: height each image (tile) must be fitted in
        mosaic_gap_size: internal gap in pixels between each tile of the mosaic
        margins: space in pixels between the border of the image and the tiles
        background_color:
    """
    header_height = 150
    header_title = f"{dst_asset.image_path.stem} v{__version__}"
    header_disclaimer_txt = "all images belongs to their respective owner, credits viewable in the metadata."
    bg_color = ",".join(map(str, background_color))

    if len(src_assets) <= mosaic_columns:
        tiles_w, tiles_h = (len(src_assets), 1)
    else:
        tiles_w = mosaic_columns
        tiles_h = math.ceil(len(src_assets) / mosaic_columns)

    command: list[str] = [str(OIIOTOOL_PATH)]
    for src_asset in src_assets:
        command += [
            "-i",
            str(src_asset.image_path),
            "--fit:filter=cubic",
            f"{tile_width}x{tile_height}",
            "--ch",
            "R,G,B,A=1.0",
            # bottom-left text with 30px margin
            "--text:x={TOP.x+30}:y={TOP.height+TOP.y-15}:shadow=4:size=20",
            f"{src_asset.identifier}",
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
    # text header
    command += [
        f"--text:x={margins}:y=60:size=45",
        header_title,
        f"--text:x={margins}:y=95:size=25:color=0.4,0.4,0.4",
        header_disclaimer_txt,
    ]

    # metadata
    authors: dict[str, list[str]] = {}
    for asset in src_assets:
        for author in asset.metadata.authors:
            authors.setdefault(author, []).append(asset.identifier)
    authors: list[str] = [
        f"{author} ({','.join(assets)})" for author, assets in authors.items()
    ]
    metadata = AssetMetadata(
        source="https://github.com/MrLixm/picture-lab-lxm",
        authors=authors,
        references=["https://github.com/MrLixm/picture-lab-lxm"],
        capture_gamut="various",
        primary_color=AssetPrimaryColor.rainbow,
        type=AssetType.cgi,
        context=description,
    )
    LOGGER.debug(f"writing metadata to '{dst_asset.json_path}'")
    metadata.to_json_file(dst_asset.json_path, indent=4)

    command += [
        "--evaloff",
        "--wildcardoff",
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
    for metadata_name, metadata_value in metadata.to_dict().items():
        command += [
            "--attrib",
            f"{lxmpicturelab.METADATA_PREFIX}/{metadata_name}",
            json.dumps(metadata_value),
        ]

    # export
    command += oiiotool_export(
        dst_asset.image_path,
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

        assets = variant.get_assets(ASSET_DIR)
        bg_color = variant.bg_color
        variant_name = variant.identifier
        variant_dir = dst_dir / variant_name

        if variant_dir.exists() and not overwrite_existing:
            LOGGER.info(f"{prefix} ❎ skipping existing set '{variant_name}'")
            continue

        variant_dir.mkdir(exist_ok=True)

        mosaic_path = variant_dir / f"{variant_name}.json"
        mosaic_asset = ImageAsset(mosaic_path)

        LOGGER.info(
            f"💫 generating mosaic from {len(assets)} assets to '{mosaic_asset.image_path}'"
        )
        with timeit(f"{prefix} ✅ generation took ", LOGGER.info):
            generate_mosaic(
                dst_asset=mosaic_asset,
                src_assets=assets,
                background_color=bg_color,
                description=variant.description,
            )
            preview_path = mosaic_path.with_suffix(".preview.jpg")
            generate_preview(
                mosaic_path=mosaic_asset.image_path,
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
