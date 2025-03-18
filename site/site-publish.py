import contextlib
import logging
import re
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

import lxmpicturelab
from lxmpicturelab.browse import WORKBENCH_DIR

LOGGER = logging.getLogger(Path(__file__).stem)


THISDIR = Path(__file__).parent

BUILD_SCRIPT = THISDIR / "site-build.py"

WORK_DIR = WORKBENCH_DIR / "site-publish.work"
# XXX: this need to be a directory trackable by git (non-ignored).
BUILD_DIR = THISDIR / ".publish"


def gitget(command: list[str], cwd: Path) -> str:
    """
    Call git and return its output.
    """
    out = subprocess.check_output(["git"] + command, cwd=cwd, text=True)
    out = out.rstrip("\n").rstrip(" ")
    return out


def check_git_repo_state(repo: Path) -> tuple[str, str]:
    """
    Check the git repository is in the expected state for publishing.

    Returns:
        the commit name for publishing
    """
    git_status = gitget(["status", "--porcelain"], cwd=repo)
    git_last_commit = gitget(["rev-parse", "HEAD"], cwd=repo)
    git_current_branch = gitget(["branch", "--show-current"], cwd=repo)
    git_remote_status = gitget(["status", "--short", "--b", "--porcelain"], cwd=repo)
    try:
        git_ghpages = gitget(["rev-parse", "--verify", "gh-pages"], cwd=repo)
    except subprocess.CalledProcessError:
        git_ghpages = None

    if git_current_branch != "main":
        raise RuntimeError(
            f"current git branch is '{git_current_branch}', expected 'main'."
        )

    if not git_ghpages:
        raise RuntimeError("Branch 'gh-pages' doesn't exists. Create it first.")

    if git_status:
        raise RuntimeError(f"Uncommited changes found: {git_status}.")

    if re.search(rf"## {git_current_branch}.+\[ahead", git_remote_status):
        raise RuntimeError("current git branch is ahead of its remote (needs push).")

    if re.search(rf"## {git_current_branch}.+\[behind", git_remote_status):
        raise RuntimeError("current git branch is behind of its remote (needs pull). ")

    return (
        f"chore(doc): automatic build to gh-pages",
        f"from commit {git_last_commit} on branch {git_current_branch}",
    )


@contextlib.contextmanager
def publish_context(build_dir: Path, commit_msg: tuple[str, str]):
    """
    Perform actions that will be published to the gh-page branch.

    Args:
        build_dir: filesystem path to a directory thatmay not exist yet.
        commit_msg: message for the gh-page branch commit.
    """
    LOGGER.debug(f"git worktree add {build_dir} gh-pages")
    subprocess.check_call(
        ["git", "worktree", "add", str(build_dir), "gh-pages"], cwd=THISDIR
    )
    try:
        # ensure to clean the gh-pages content at each build
        subprocess.check_call(
            ["git", "rm", "--quiet", "--ignore-unmatch", "-r", "*"], cwd=build_dir
        )

        yield

        subprocess.check_call(["git", "add", "--all"], cwd=build_dir)

        changes = gitget(["status", "--porcelain"], cwd=build_dir)
        if not changes:
            LOGGER.warning("nothing to commit, skipping publishing ...")
            return

        LOGGER.info(f"git changes found:\n{changes}")

        LOGGER.info(f"git commit -m '{commit_msg[0]}' -m '{commit_msg[1]}'")
        subprocess.check_call(
            ["git", "commit", "-m", commit_msg[0], "-m", commit_msg[1]], cwd=build_dir
        )
        LOGGER.info("git push origin gh-pages")
        subprocess.check_call(["git", "push", "origin", "gh-pages"], cwd=build_dir)

    finally:
        # `git worktree remove` is supposed to delete it but fail, so we do it in python
        LOGGER.debug(f"shutil.rmtree({build_dir})")
        shutil.rmtree(build_dir, ignore_errors=True)
        LOGGER.debug(f"git worktree prune")
        subprocess.check_call(["git", "worktree", "prune"], cwd=THISDIR)


def main():
    LOGGER.warning("📤 about to publish website; make sure this is intentional")
    try:
        commit_msgs = check_git_repo_state(THISDIR)
    except Exception as error:
        print(f"GIT ERROR: {error}", file=sys.stderr)
        sys.exit(1)

    # make sure to regenerates all the comparisons/renderers from scratch
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)

    sys.argv = [
        sys.argv[0],
        "--publish",
        "--target-dir",
        str(BUILD_DIR),
        "--work-dir",
        str(WORK_DIR),
    ]
    with publish_context(BUILD_DIR, commit_msgs):
        runpy.run_path(str(BUILD_SCRIPT), run_name="__main__")

    LOGGER.info("✅ site publish finished")


if __name__ == "__main__":
    lxmpicturelab.configure_logging()
    main()
