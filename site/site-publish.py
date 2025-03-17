import runpy
import sys
from pathlib import Path

THISDIR = Path(__file__).parent
BUILD_SCRIPT = THISDIR / "site-build.py"
BUILD_DIR = THISDIR.parent / ".site.build"

sys.argv = sys.argv + ["--publish", "--target-dir", str(BUILD_DIR)]
runpy.run_path(str(BUILD_SCRIPT), run_name="__main__")
