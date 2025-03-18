import argparse
import dataclasses
import datetime
import logging
import os
import re
import runpy
import shutil
import sys
from typing import Any

import unicodedata
from pathlib import Path
from typing import Callable

import jinja2

import lxmpicturelab.renderer
from lxmpicturelab import patch_sysargv
from lxmpicturelab.browse import SCRIPTS_DIR
from lxmpicturelab.comparison import ComparisonRender
from lxmpicturelab.comparison import ComparisonSession
from lxmpicturelab.comparison import GeneratorCombined
from lxmpicturelab.renderer import OcioConfigRenderer

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

# orders define visual order in which comparison are presented on the site
RENDERERS = [
    lxmpicturelab.renderer.NativeBuilder,
    lxmpicturelab.renderer.TCAMBuilder,
    lxmpicturelab.renderer.ARRIBuilder,
    lxmpicturelab.renderer.AgXBuilder,
    lxmpicturelab.renderer.AgXBlenderBuilder,
    lxmpicturelab.renderer.AgXcBuilder,
    lxmpicturelab.renderer.ACES13gmBuilder,
    lxmpicturelab.renderer.ACES2gmBuilder,
    lxmpicturelab.renderer.ACES2Builder,
]

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
class CtxRenderer:
    name: str
    identifier: str
    description: str
    reference_url: str
    config_display: str
    config_view: str
    config_look: str

    @classmethod
    def from_renderer(cls, renderer: OcioConfigRenderer) -> "CtxRenderer":
        name = renderer.name
        identifier = renderer.filename
        description = renderer.description
        reference_url = renderer.reference_url
        config_display = renderer.display
        config_view = renderer.view
        config_look = renderer.look
        return cls(
            name=name,
            identifier=identifier,
            description=description,
            reference_url=reference_url,
            config_display=config_display,
            config_view=config_view,
            config_look=config_look,
        )


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

    def sort_renders(self, callback: Callable[[CtxRender], Any]):
        for generator in self.generators:
            generator.renders = sorted(generator.renders, key=callback)


def build_renderers(
    dst_dir: Path,
    renderer_ids: list[str],
) -> list[CtxRenderer]:
    """
    Args:
        dst_dir: filesystem path to a directory that may exist
        renderer_ids: list of renderer identifier to build and return
    """
    renderers: list[CtxRenderer] = []
    for renderer_id in renderer_ids:
        renderer_dir = dst_dir / renderer_id
        command = [renderer_id, str(renderer_dir)]
        with patch_sysargv([str(RENDERER_SCRIPT_PATH)] + command):
            runpy.run_path(str(RENDERER_SCRIPT_PATH), run_name="__main__")

        renderer_file = next(renderer_dir.glob("*.json"))
        renderer_txt = renderer_file.read_text("utf-8")
        renderer = OcioConfigRenderer.from_json(renderer_txt)
        ctxrenderer = CtxRenderer.from_renderer(renderer)
        renderers.append(ctxrenderer)

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
            LOGGER.info(f"⏩ skipping building for '{asset_id}': found existing")
        else:
            LOGGER.info(f"🔨 building comparisons for '{asset_id}'")
            command = [
                asset_id,
                "--target-dir",
                str(asset_dst_dir),
                "--renderer-dir",
                str(renderers_dir),
            ] + asset_args
            with patch_sysargv([str(IMAGEGEN_SCRIPT_PATH)] + command):
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

    def sort_renders(render: CtxRender):
        try:
            return renderer_ids.index(render.renderer_id)
        except ValueError:
            LOGGER.warning(
                f"could not sort CtxRender {render.renderer_id}; not in {renderer_ids}"
            )
            return 0

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
        comparison.sort_renders(callback=sort_renders)
        page_ctx = {
            "Comparison": comparison,
            "NAV_ACTIVE": comparison.page_slug,
        }
        page_ctx.update(global_ctx)
        html = comparison_template.render(**page_ctx)
        html_path = build_dir / f"{comparison.page_slug}.html"
        LOGGER.info(f"💾 writing html to '{html_path}'")
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
    LOGGER.info(f"💾 writing html to '{html_path}'")
    html_path.write_text(html, encoding="utf-8")

    # build index.html

    page_ctx = {
        "NAV_ACTIVE": "index",
    }
    page_ctx.update(global_ctx)
    index_template = jinja_env.get_template("index.html")
    html = index_template.render(**page_ctx)
    html_path = build_dir / f"index.html"
    LOGGER.info(f"💾 writing html to '{html_path}'")
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


def get_cli(argv: list[str] | None = None) -> argparse.Namespace:
    argv = argv or sys.argv[1:]
    LOGGER.debug(f"argv={argv}")
    parser = argparse.ArgumentParser(
        description="Generates the repository static website.",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="If specified configure the site build for web publishing instead of local.",
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


def main(argv: list[str] | None = None):
    cli = get_cli(argv)
    work_dir: Path = cli.work_dir
    build_dir: Path = cli.target_dir
    publish: bool = cli.publish

    LOGGER.debug(f"{build_dir=}")
    LOGGER.debug(f"{work_dir=}")
    LOGGER.debug(f"{publish=}")

    if build_dir.exists() and not publish:
        LOGGER.debug(f"shutil.rmtree({build_dir})")
        shutil.rmtree(build_dir)

    work_dir.mkdir(exist_ok=True)
    build_dir.mkdir(exist_ok=True)

    LOGGER.info(f"🔨 building site to '{build_dir}'")
    build(
        assets=ASSETS,
        renderer_ids=[r.identifier for r in RENDERERS],
        build_dir=build_dir,
        work_dir=work_dir,
        publish=publish,
    )
    LOGGER.info("✅ site build finished")
    if publish:
        LOGGER.info(f"🌐 check '{SITEURL}' in few minutes")
    else:
        LOGGER.info(f"🌐 check 'file:///{build_dir.as_posix()}/index.html'")


if __name__ == "__main__":
    lxmpicturelab.configure_logging()
    main()
