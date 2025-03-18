import argparse
import contextlib
import dataclasses
import datetime
import logging
import os
import re
import runpy
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Callable

import jinja2

import lxmpicturelab
from lxmpicturelab.browse import SCRIPTS_DIR
from lxmpicturelab.renderer import OcioConfigRenderer
from lxmpicturelab.comparison import ComparisonSession
from lxmpicturelab.comparison import ComparisonRender
from lxmpicturelab.comparison import GeneratorCombined
from lxmpicturelab.renderer import RENDERER_BUILDERS_BY_ID

LOGGER = logging.getLogger(Path(__file__).stem)

THISDIR = Path(__file__).parent
BUILDIR = THISDIR / ".build"
WORKDIR = THISDIR / ".workbench"

RENDERER_SCRIPT_PATH = SCRIPTS_DIR / "renderer-build.py"
IMAGEGEN_SCRIPT_PATH = SCRIPTS_DIR / "comparisons-generate.py"

ASSETS = {
    "lxmpicturelab.al.sorted-color.bg-black": ["--generator-full", "2048"],
    "CGts-W0L-sweep": ["--generator-full", "864"],
    "CAlc-D8T-dragon": ["--generator-exposures", "0.45", "--generator-full", "864"],
    "CAtm-FGH-specbox": ["--generator-full", "1080"],
    "PAmsk-R65-christmas": ["--generator-exposures", "0.3", "--generator-full", "864"],
    "PAfm-SWE-neongirl": ["--generator-exposures", "0.3", "--generator-full", "864"],
    "PAkp-4DO-bluehand": ["--generator-full", "864"],
    "PAtm-2QQ-space": ["--generator-exposures", "0.3", "--generator-full", "864"],
    "PWarr-VWE-helenjohn": ["--generator-exposures", "0.1", "--generator-full", "864"],
    "PAac-B01-skins": ["--generator-exposures", "0.01", "--generator-full", "864"],
    "PAjg-MZY-nightstreet": ["--generator-exposures", "0.3", "--generator-full", "864"],
}


CSS_PATH = THISDIR / "main.css"

STATIC_RESOURCES = {
    "MartianMono.variable.ttf": "MartianMono.variable.ttf",
    "img/lxmpicturelab-cover.jpg": "img/lxmpicturelab-cover.jpg",
    "img/lxmpicturelab-icon.svg": "img/lxmpicturelab-icon.svg",
    "img/icon-grid.svg": "img/icon-grid.svg",
    "img/icon-swap-box.svg": "img/icon-swap-box.svg",
    ".nojekyll": ".nojekyll",
}

SITENAME = "lxmpicturelab"
REPONAME = "picture-lab-lxm"
SITEURL = f"https://mrlixm.github.io/{REPONAME}"
SITEICON = "img/lxmpicturelab-icon.svg"

META_DESCRIPTION = "Comparison of different picture formation algorithms."
META_IMAGE = "img/lxmpicturelab-cover.jpg"

FOOTER = "Static website created by Liam Collod using Python"

# we mirror the API in lxmpicturelab to prevent break
# in Jinja templates when the API changes. It also mean
# we pass simpler object to the Jinja template and this is the only
# place to read if you want to know what to access in your template.


@dataclasses.dataclass
class CtxRender:
    renderer_name: str
    renderer_id: str
    path: str

    @classmethod
    def from_comparison(cls, comparison: ComparisonRender) -> "CtxRender":
        return cls(
            renderer_name=comparison.renderer.name,
            renderer_id=comparison.renderer.filename,
            path=str(comparison.dst_path),
        )


@dataclasses.dataclass
class CtxGenerator:
    name: str
    renders: list[CtxRender]
    combined: CtxRender | None


@dataclasses.dataclass
class CtxComparison:
    asset_id: str
    generators: list[CtxGenerator]
    meta_context: str
    meta_gamut: str
    meta_authors: str
    meta_references: list[str]

    @property
    def page_slug(self) -> str:
        return self.asset_id

    @classmethod
    def from_session(cls, session: ComparisonSession) -> "CtxComparison":
        asset_id = session.asset.identifier
        meta_context = session.asset.metadata.context
        meta_gamut = session.asset.metadata.capture_gamut
        meta_authors = "; ".join(session.asset.metadata.authors)
        meta_references = session.asset.metadata.references
        render_by_generators: dict[str, list[ComparisonRender]] = {}
        combined_by_generators: dict[str, CtxRender] = {}
        for render in session.renders:
            generator_name = render.generator.shortname
            if generator_name == GeneratorCombined.shortname:
                combined_by_generators[generator_name] = CtxRender.from_comparison(
                    render
                )
            else:
                render_by_generators.setdefault(generator_name, []).append(render)

        cgs = []
        for generator_name, renders in render_by_generators.items():
            cg = CtxGenerator(
                name=generator_name,
                renders=[CtxRender.from_comparison(render) for render in renders],
                combined=combined_by_generators.get(generator_name),
            )
            cgs.append(cg)

        return cls(
            asset_id=asset_id,
            generators=cgs,
            meta_context=meta_context,
            meta_gamut=meta_gamut,
            meta_authors=meta_authors,
            meta_references=meta_references,
        )

    def edit_paths(self, callback: Callable[[str], str]):
        for generator in self.generators:
            for render in generator.renders:
                render.path = callback(render.path)


def build_renderers(
    dst_dir: Path,
    renderer_ids: list[str],
) -> list[OcioConfigRenderer]:
    """
    Args:
        dst_dir: filesystem path to a directory that may exist
        renderer_ids: list of renderer identifier to build and return
    """
    renderers: list[OcioConfigRenderer] = []
    for renderer_id in renderer_ids:
        renderer_dir = dst_dir / renderer_id
        sys.argv = [
            sys.argv[0],
            renderer_id,
            str(renderer_dir),
        ]
        runpy.run_path(str(RENDERER_SCRIPT_PATH), run_name="__main__")

        renderer_file = next(renderer_dir.glob("*.json"))
        renderer_txt = renderer_file.read_text("utf-8")
        renderer = OcioConfigRenderer.from_json(renderer_txt)
        renderers.append(renderer)

    return renderers


def build_comparisons(
    assets: dict[str, list[str]],
    comparisons_dir: Path,
    renderers_dir: Path,
    dst_dir: Path,
    overwrite_existing: bool = False,
) -> list[CtxComparison]:
    """
    Generate the comparison images and their metadata.
    """
    sessions: list[ComparisonSession] = []

    for asset_id, asset_args in assets.items():
        asset_dst_dir = comparisons_dir / asset_id

        if asset_dst_dir.exists() and not overwrite_existing:
            LOGGER.info(f"💨 skipping building for '{asset_id}': found existing")
        else:
            LOGGER.info(f"🔨 building comparisons for '{asset_id}'")
            sys.argv = [
                sys.argv[0],
                asset_id,
                "--target-dir",
                str(asset_dst_dir),
                "--renderer-dir",
                str(renderers_dir),
            ] + asset_args
            runpy.run_path(str(IMAGEGEN_SCRIPT_PATH), run_name="__main__")

        session_metadadata_path = next(asset_dst_dir.glob("*.json"))
        session_metadadata = session_metadadata_path.read_text(encoding="utf-8")
        session = ComparisonSession.from_json(json_str=session_metadadata)
        if session.asset.identifier.startswith("lxm"):
            sessions.insert(0, session)
        else:
            sessions.append(session)

    LOGGER.debug(f"copytree('{comparisons_dir}', '{dst_dir}')")
    shutil.copytree(comparisons_dir, dst_dir, ignore=shutil.ignore_patterns("*.json"))

    def swap_path(p: str) -> str:
        p = Path(p).relative_to(comparisons_dir)
        return str(dst_dir / p)

    comparisons = [CtxComparison.from_session(session) for session in sessions]
    [comparison.edit_paths(swap_path) for comparison in comparisons]

    return comparisons


def gitget(command: list[str], cwd: Path) -> str:
    """
    Call git and return its output.
    """
    out = subprocess.check_output(["git"] + command, cwd=cwd, text=True)
    out = out.rstrip("\n").rstrip(" ")
    return out


def slugify(value, allow_unicode=False):
    """
    Convert to ASCII if 'allow_unicode' is False. Convert spaces or repeated
    dashes to single dashes. Remove characters that aren't alphanumerics,
    underscores, or hyphens. Convert to lowercase. Also strip leading and
    trailing whitespace, dashes, and underscores.

    References:
        - [1] https://github.com/django/django/blob/30e0a43937e685083fa1210c3594678a3b813806/django/utils/text.py#L444
    """
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize("NFKC", value)
    else:
        value = (
            unicodedata.normalize("NFKD", value)
            .encode("ascii", "ignore")
            .decode("ascii")
        )
    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[-\s]+", "-", value).strip("-_")


def get_jinja_env(doc_build_dir: Path) -> jinja2.Environment:
    jinja_env = jinja2.Environment(
        undefined=jinja2.StrictUndefined,
        loader=jinja2.FileSystemLoader(THISDIR),
    )
    jinja_env.filters["slugify"] = slugify
    return jinja_env


def get_cli(argv: list[str] | None = None) -> argparse.Namespace:
    argv = argv or sys.argv[1:]
    parser = argparse.ArgumentParser(
        description="Generates the repository static website.",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="True to create the website published to the gh-page branch.",
    )
    parser.add_argument(
        "--target-dir",
        type=Path,
        default=BUILDIR,
        help="filesystem path to write the final html site to.",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=WORKDIR,
        help="filesystem path to write intermediates resource data to.",
    )
    parsed = parser.parse_args(argv)
    return parsed


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
        shutil.rmtree(build_dir, ignore_errors=True)
        subprocess.check_call(["git", "worktree", "prune"], cwd=THISDIR)


def build(
    assets: dict[str, list[str]],
    renderer_ids: list[str],
    build_dir: Path,
    work_dir: Path,
    publish: bool,
):
    """
    Generate the final static html site.

    Args:
        assets: collection of asset to build the website against
        renderer_ids: list of renderer identifier to build and use for the comparison
        build_dir: filesystem path to a non-existing directory. Used to store the final site.
        work_dir: filesystem path to an existing directory.
        publish: true to build for web publishing else implies local testing.
    """

    def expand_siteurl(path: str) -> str:
        if publish:
            return f"{SITEURL}/{path}"
        return path

    def conformize_paths(p: str) -> str:
        p = Path(p)
        p = p.relative_to(build_dir)
        return p.as_posix()

    # // comparison images generation

    img_dir = build_dir / "img"

    renderers_dir = work_dir / "renderers"
    renderers_dir.mkdir(exist_ok=True)
    LOGGER.info(f"🔨 building renderers to '{renderers_dir}'")
    renderers = build_renderers(dst_dir=renderers_dir, renderer_ids=renderer_ids)

    comparisons_dir = work_dir / "comparisons"
    comparisons_dir.mkdir(exist_ok=True)
    LOGGER.info(f"🔨 building comparisons images to '{comparisons_dir}'")
    comparisons = build_comparisons(
        assets=assets,
        comparisons_dir=comparisons_dir,
        renderers_dir=renderers_dir,
        dst_dir=img_dir,
    )

    # // HTML generation

    jinja_env = get_jinja_env(build_dir)
    comparison_template = jinja_env.get_template("comparison.html")

    # build comparison.html

    global_ctx = {
        "SITENAME": SITENAME,
        "SITEICON": expand_siteurl(SITEICON),
        "STYLESHEETS": [CSS_PATH.name],
        "COMPARISONS": comparisons,
        "FOOTER": FOOTER,
        "BUILD_DATE": datetime.datetime.today().isoformat(timespec="minutes"),
        "META_DESCRIPTION": META_DESCRIPTION,
        "META_IMAGE": expand_siteurl(META_IMAGE),
    }

    for comparison in comparisons:
        comparison.edit_paths(callback=conformize_paths)
        page_ctx = {
            "Comparison": comparison,
            "NAV_ACTIVE": comparison.page_slug,
        }
        page_ctx.update(global_ctx)
        html = comparison_template.render(**page_ctx)
        html_path = build_dir / f"{comparison.page_slug}.html"
        LOGGER.info(f"writing html to '{html_path}'")
        html_path.write_text(html, encoding="utf-8")

    # build about.html

    page_ctx = {
        "Renderers": renderers,
        "NAV_ACTIVE": "about",
    }
    page_ctx.update(global_ctx)
    about_template = jinja_env.get_template("about.html")
    html = about_template.render(**page_ctx)
    html_path = build_dir / f"about.html"
    LOGGER.info(f"writing html to '{html_path}'")
    html_path.write_text(html, encoding="utf-8")

    # build index.html

    page_ctx = {
        "NAV_ACTIVE": "index",
    }
    page_ctx.update(global_ctx)
    index_template = jinja_env.get_template("index.html")
    html = index_template.render(**page_ctx)
    html_path = build_dir / f"index.html"
    LOGGER.info(f"writing html to '{html_path}'")
    html_path.write_text(html, encoding="utf-8")

    # copy static resources

    if publish:
        shutil.copy(CSS_PATH, build_dir / CSS_PATH.name)
    else:
        os.symlink(CSS_PATH, build_dir / CSS_PATH.name)
    for src_path, dst_path in STATIC_RESOURCES.items():
        src_path = Path(THISDIR, src_path)
        dst_path = Path(build_dir, dst_path)
        LOGGER.debug(f"shutil.copy({src_path}, {dst_path})")
        shutil.copy(src_path, dst_path)


def main(argv: list[str] | None = None):
    cli = get_cli(argv)
    work_dir: Path = cli.work_dir
    build_dir: Path = cli.target_dir
    publish: bool = cli.publish

    LOGGER.debug(f"build_dir={build_dir}")
    LOGGER.debug(f"work_dir={work_dir}")

    if build_dir.exists():
        shutil.rmtree(build_dir)
    if publish and work_dir.exists():
        shutil.rmtree(work_dir)

    work_dir.mkdir(exist_ok=True)

    renderer_ids = list(RENDERER_BUILDERS_BY_ID.keys())

    if publish:
        LOGGER.warning("about to publish website; make sure this is intentional")
        try:
            commit_msgs = check_git_repo_state(THISDIR)
        except Exception as error:
            print(f"GIT ERROR: {error}", file=sys.stderr)
            sys.exit(1)

        with publish_context(build_dir, commit_msgs):
            build(
                assets=ASSETS,
                renderer_ids=renderer_ids,
                build_dir=build_dir,
                work_dir=work_dir,
                publish=True,
            )
        LOGGER.info("✅ site publish finished")
        LOGGER.info(f"🌐 check '{SITEURL}' in few minutes")

    else:
        build_dir.mkdir(exist_ok=True)
        build(
            assets=ASSETS,
            renderer_ids=renderer_ids,
            build_dir=build_dir,
            work_dir=work_dir,
            publish=False,
        )
        LOGGER.info("✅ site build finished")
        LOGGER.info(f"🌐 check 'file:///{build_dir.as_posix()}/index.html'")


if __name__ == "__main__":
    lxmpicturelab.configure_logging()
    main()
