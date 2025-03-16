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
SETS_DIR = REPO_ROOT / "sets"


def get_imagery_assets(root_dir: Path = None) -> list[ImageryAsset]:
    """
    Retrieve all the existing ImageryAssets stored in the given directory.
    """
    root_dir = root_dir or ASSET_DIR
    return [ImageryAsset(path) for path in root_dir.rglob("*.json")]


def get_imagery_sets(root_dir: Path = None) -> dict[str, Path]:
    """
    Retrieve all the existing sets images file stored in the given directory.

    Returns:
        mapping of "set name": "set absolute path"
    """
    root_dir = root_dir or SETS_DIR
    return {path.parent.name: path for path in root_dir.rglob("*.exr")}
