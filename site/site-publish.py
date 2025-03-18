import argparse
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
BUILD_DIR = THISDIR.parent / ".site.publish"


def gitget(command: list[str], cwd: Path) -> str:
    """
    Call git and return its output.
    """
    out = subprocess.check_output(["git"] + command, cwd=cwd, text=True)
    out = out.rstrip("\n").rstrip(" ")
    return out


def gitc(command: list[str], cwd: Path):
    """
    Call git.
    """
    subprocess.check_call(["git"] + command, cwd=cwd)


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
def publish_context(
    build_dir: Path,
    commit_msg: tuple[str, str],
    dry_run: bool = False,
):
    """
    Perform actions that will be published to the gh-page branch.

    Args:
        build_dir: filesystem path to a directory thatmay not exist yet.
        commit_msg: message for the gh-page branch commit.
        dry_run: If True do not affect the repository permanently.
    """
    LOGGER.debug(f"git worktree add {build_dir} gh-pages")
    gitc(["worktree", "add", str(build_dir), "gh-pages"], cwd=THISDIR)
    try:
        # ensure to clean the gh-pages content at each build
        gitc(["rm", "--quiet", "--ignore-unmatch", "-r", "*"], cwd=build_dir)

        yield

        gitc(["add", "--all"], cwd=build_dir)

        changes = gitget(["status", "--porcelain"], cwd=build_dir)
        if not changes:
            LOGGER.warning("nothing to commit, skipping publishing ...")
            return

        LOGGER.info(f"git changes found:\n{changes}")

        if dry_run:
            LOGGER.warning("dry run specified; returning ...")
            return
        else:
            LOGGER.info(f"git commit -m '{commit_msg[0]}' -m '{commit_msg[1]}'")
            gitc(["commit", "-m", commit_msg[0], "-m", commit_msg[1]], cwd=build_dir)
            LOGGER.info("git push origin gh-pages")
            gitc(["push", "origin", "gh-pages"], cwd=build_dir)

    finally:
        # `git worktree remove` is supposed to delete it but fail, so we do it in python
        LOGGER.debug(f"shutil.rmtree({build_dir})")
        shutil.rmtree(build_dir, ignore_errors=True)
        LOGGER.debug(f"git worktree prune")
        gitc(["worktree", "prune"], cwd=THISDIR)


def get_cli(argv: list[str] | None = None) -> argparse.Namespace:
    argv = argv or sys.argv[1:]
    parser = argparse.ArgumentParser(
        description="Generates the repository static website and publish it to GitHub pages.",
    )
    parser.add_argument(
        "--preserve-work-dir",
        action="store_true",
        help="If specified, do not delete the work directory which may avoid the long generation of comparisons/renders.",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=WORK_DIR,
        help="filesystem path to a directory that may exist. use to write intermediates resource data to.",
    )
    parser.add_argument(
        "--dev-mode",
        action="store_true",
        help="If specified, do not push the branch, and git check do not raises. Useful for debugging.",
    )
    parsed = parser.parse_args(argv)
    return parsed


def main():

    cli = get_cli()

    u_preserve_work_dir: bool = cli.preserve_work_dir
    u_work_dir: Path = cli.work_dir
    u_dev_mode: bool = cli.dev_mode

    LOGGER.debug(f"{u_preserve_work_dir=}")
    LOGGER.debug(f"{u_work_dir=}")
    LOGGER.debug(f"{u_dev_mode=}")

    LOGGER.warning("📤 about to publish website; make sure this is intentional")
    try:
        commit_msgs = check_git_repo_state(THISDIR)
    except Exception as error:
        print(f"GIT ERROR: {error}", file=sys.stderr)
        if u_dev_mode:
            commit_msgs = ("! delete me (dev mode enabled)", "")
        else:
            sys.exit(1)

    # make sure to regenerates all the comparisons/renderers from scratch
    if u_work_dir.exists() and not u_preserve_work_dir:
        shutil.rmtree(u_work_dir)

    sys.argv = [
        sys.argv[0],
        "--publish",
        "--target-dir",
        str(BUILD_DIR),
        "--work-dir",
        str(u_work_dir),
    ]
    with publish_context(BUILD_DIR, commit_msgs, dry_run=u_dev_mode):
        runpy.run_path(str(BUILD_SCRIPT), run_name="__main__")

    LOGGER.info("✅ site publish finished")


if __name__ == "__main__":
    lxmpicturelab.configure_logging()
    main()
