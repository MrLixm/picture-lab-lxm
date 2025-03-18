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

for asset_path, colorspace in ASSETS_IN.items():
    command = [str(asset_path), "--colorspace", colorspace]
    if OVERWRITE:
        command += ["--overwrite-existing"]
    with patch_sysargv([str(ASSET_SCRIPT)] + command):
        runpy.run_path(str(ASSET_SCRIPT), run_name="__main__")
