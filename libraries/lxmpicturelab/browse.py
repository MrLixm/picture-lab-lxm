import logging
from pathlib import Path

from .asset import ImageAsset


LOGGER = logging.getLogger(__name__)

_THISDIR = Path(__file__).parent

REPO_ROOT = _THISDIR.parent.parent
ASSET_DIR = REPO_ROOT / "assets"
ASSET_IN_DIR = REPO_ROOT / ".assets-in"
SCRIPTS_DIR = REPO_ROOT / "scripts"
VENDOR_DIR = REPO_ROOT / ".vendor"
WORKBENCH_DIR = REPO_ROOT / ".workbench"
SETS_DIR = REPO_ROOT / "sets"


def get_all_assets(root_dir: Path) -> list[ImageAsset]:
    """
    Retrieve all the existing ImageryAssets stored in the given directory.
    """
    root_dir = root_dir or ASSET_DIR
    return [ImageAsset(path) for path in root_dir.rglob("*.json")]


def get_asset(identifier: str, root_dir: Path) -> ImageAsset | None:
    """
    Get the asset matching the given identifier from the given directory.
    """
    assets = get_all_assets(root_dir)
    for asset in assets:
        if asset.identifier == identifier:
            return asset
    return None


def find_asset(identifier: str) -> ImageAsset | None:
    """
    Find the given asset based on known assets locations.
    """
    asset = get_asset(identifier, ASSET_DIR)
    if asset:
        return asset
    set_asset = get_asset(identifier, SETS_DIR)
    return set_asset
