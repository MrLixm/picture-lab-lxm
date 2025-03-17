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


def get_all_assets(root_dir: Path = None) -> list[ImageAsset]:
    """
    Retrieve all the existing ImageryAssets stored in the given directory.
    """
    root_dir = root_dir or ASSET_DIR
    return [ImageAsset(path) for path in root_dir.rglob("*.json")]


def get_asset(identifier: str, root_dir: Path = None) -> ImageAsset | None:
    """
    Get the asset matching the given identifier.
    """
    assets = get_all_assets(root_dir)
    for asset in assets:
        if asset.identifier == identifier:
            return asset
    return None


def get_all_sets(root_dir: Path = None) -> dict[str, Path]:
    """
    Retrieve all the existing sets images file stored in the given directory.

    Returns:
        mapping of "set name": "set absolute path"
    """
    root_dir = root_dir or SETS_DIR
    return {path.parent.name: path for path in root_dir.rglob("*.exr")}


def get_set(identifier: str, root_dir: Path = None) -> Path | None:
    """
    Get the set image matching the given identifier.
    """
    imgsets = get_all_sets(root_dir)
    for imgset_id, imgset_path in imgsets.items():
        if imgset_id == identifier:
            return imgset_path
    return None
