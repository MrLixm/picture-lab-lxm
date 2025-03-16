import logging
from pathlib import Path

from .imgasset import ImageryAsset


LOGGER = logging.getLogger(__name__)

_THISDIR = Path(__file__).parent

REPO_ROOT = _THISDIR.parent.parent
ASSET_DIR = REPO_ROOT / "assets"
ASSET_IN_DIR = REPO_ROOT / ".assets-in"
SCRIPTS_DIR = REPO_ROOT / "scripts"
VENDOR_DIR = REPO_ROOT / ".vendor"
WORKBENCH_DIR = REPO_ROOT / ".workbench"


def get_imagery_assets(asset_dir: Path = None) -> list[ImageryAsset]:
    """
    Retrieve all the ImageryAssets stored in the given directory.
    """
    asset_dir = asset_dir or ASSET_DIR
    return [
        ImageryAsset(file) for file in asset_dir.glob("*") if file.suffix == ".json"
    ]
