import logging
import runpy
from pathlib import Path

from lxmpicturelab import patch_sysargv
from lxmpicturelab.browse import ASSET_IN_DIR
from lxmpicturelab.browse import SCRIPTS_DIR

LOGGER = logging.getLogger(__name__)

ASSET_SCRIPT = SCRIPTS_DIR / "asset-generate.py"

OVERWRITE: bool = False

# - file without colorspace are assumed to be already ACES2065-1
# - colorspace value must be a name found in the ACES studio-config v2.0.0
ASSETS_IN: dict[Path, list[str]] = {
    ASSET_IN_DIR / "CAaf-Z37-legomovie.json": [],
    ASSET_IN_DIR / "CAlc-D8T-dragon.json": [],
    ASSET_IN_DIR / "CAtm-FGH-specbox.json": [],
    ASSET_IN_DIR / "CGts-W0L-sweep.json": ["--colorspace", "Linear Rec.709 (sRGB)"],
    ASSET_IN_DIR / "PAds-4HS-testbench.json": [],
    ASSET_IN_DIR / "PAfl-H6O-night.json": [],
    ASSET_IN_DIR / "PAfl-IP1-candle.json": [],
    ASSET_IN_DIR / "PAfl-UY7-garden.json": [],
    ASSET_IN_DIR / "PAfm-SWE-neongirl.json": [],
    ASSET_IN_DIR / "PAmsk-8BB-bluebar.json": [],
    ASSET_IN_DIR / "PAmsk-R65-christmas.json": [],
    ASSET_IN_DIR / "PAtm-2QQ-space.json": [],
    ASSET_IN_DIR / "PWarr-VWE-helenjohn.json": ["--colorspace", "ARRI LogC4"],
    ASSET_IN_DIR / "PWsjw-7QC-watchmaker.json": [],
    ASSET_IN_DIR / "PWsjw-90G-icecave.json": [],
    ASSET_IN_DIR / "PWsjw-FCC-closeman.json": [],
    ASSET_IN_DIR / "PWsjw-LE4-alpinist.json": [],
    ASSET_IN_DIR / "PAac-B01-skins.json": [],
    ASSET_IN_DIR / "PAkp-4DO-bluehand.json": [],
    ASSET_IN_DIR / "PAjg-MZY-nightstreet.json": [],
    ASSET_IN_DIR / "Cblr-GFD-spring.json": ["--colorspace", "Linear Rec.709 (sRGB)"],
    ASSET_IN_DIR / "PWdc-85R-braidmaker.json": [],
    ASSET_IN_DIR / "PPry-00M-mountain.json": [],
    ASSET_IN_DIR / "PWdac-11H-ngohaiha.json": [],
    ASSET_IN_DIR
    / "Pgra-O1K-snowfire.json": [
        # asset is Filmlight E-Gamut encoded which is not in the ACES config
        # convert first to CIE-XYZ with matrix (which is in the config).
        "--colorspace",
        "CIE XYZ-D65 - Display-referredf",
        "--color-matrix",
        "0.7053968501,0.1640413283,0.08101774865,0.2801307241,0.8202066415,-0.1003373656,-0.1037815116,-0.07290725703,1.265746519",
    ],
}

for asset_path, extra_args in ASSETS_IN.items():
    command = [str(asset_path)] + extra_args
    if OVERWRITE:
        command += ["--overwrite-existing"]
    with patch_sysargv([str(ASSET_SCRIPT)] + command):
        runpy.run_path(str(ASSET_SCRIPT), run_name="__main__")
