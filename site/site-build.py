import argparse
import dataclasses
import datetime
import json
import logging
import os
import re
import runpy
import shutil
import sys
from pathlib import Path
from typing import Callable

import jinja2
import unicodedata

import lxmpicturelab
from lxmpicturelab.renderer import OcioConfigRenderer
from lxmpicturelab.imgasset import ImageryAssetMetadata

LOGGER = logging.getLogger(Path(__file__).stem)

THISDIR = Path(__file__).parent
BUILDIR = THISDIR / ".build"
WORKDIR = THISDIR / ".workbench"

IMAGEGEN_SCRIPT_PATH = THISDIR.parent / "scripts" / "comparisons-generate.py"

CSS_PATH = THISDIR / "main.css"

STATIC_RESOURCES = [
    THISDIR / "MartianMono.variable.ttf",
    THISDIR / "lxmpicturelab-cover.jpg",
    THISDIR / "lxmpicturelab-icon.svg",
]

SITENAME = "lxmpicturelab"
SITEURL = f"https://mrlixm.github.io/{SITENAME}"
SITEICON = "lxmpicturelab-icon.svg"

META_DESCRIPTION = "Comparison of different picture formation algorithms."
META_IMAGE = "lxmpicturelab-cover.jpg"

FOOTER = "Static website created by Liam Collod using Python"


@dataclasses.dataclass
class ComparisonGenerator:
    name: str
    renders: dict[OcioConfigRenderer, str]
    combined: str


@dataclasses.dataclass
class Comparison:
    source: str
    generators: list[ComparisonGenerator]
    metadata: ImageryAssetMetadata

    @classmethod
    def from_json(cls, json_str: str, renderers: list[OcioConfigRenderer]):
        as_dict = json.loads(json_str)
        renderers_by_name = {renderer.name: renderer for renderer in renderers}

        generators = []
        for generator_name, generator_config in as_dict["generators"].items():
            generator = ComparisonGenerator(
                name=generator_name,
                renders={
                    renderers_by_name[renderer_name]: path
                    for renderer_name, path in generator_config["renders"].items()
                },
                combined=generator_config["combined"],
            )
            generators.append(generator)

        return cls(
            source=as_dict["name"],
            generators=generators,
            metadata=ImageryAssetMetadata.from_dict(as_dict["metadata"]),
        )

    def edit_paths(self, callback: Callable[[str], str]):
        for generator in self.generators:
            generator.renders = {
                name: callback(path) for name, path in generator.renders.items()
            }
            generator.combined = callback(generator.combined)


def build_comparisons(
    work_dir: Path,
    dst_dir: Path,
) -> tuple[list[Comparison], list[OcioConfigRenderer]]:
    comparisons_dir = work_dir / "comparisons"
    renderer_dir = work_dir / "renderers"
    if not comparisons_dir.exists() or not renderer_dir.exists():
        sys.argv = [
            sys.argv[0],
            "--results-dir",
            str(comparisons_dir),
            "--renderer-dir",
            str(renderer_dir),
        ]
        runpy.run_path(str(IMAGEGEN_SCRIPT_PATH), run_name="__main__")

    renderers = []
    for renderer_metadadata_path in renderer_dir.glob("*.json"):
        renderer = OcioConfigRenderer.from_json(renderer_metadadata_path.read_text())
        renderers.append(renderer)

    comparisons = []
    for comparison_metadadata_path in comparisons_dir.glob("*.json"):
        comparison = Comparison.from_json(
            json_str=comparison_metadadata_path.read_text(),
            renderers=renderers,
        )
        if comparison_metadadata_path.name.startswith("lxm"):
            comparisons.insert(0, comparison)
        else:
            comparisons.append(comparison)

    LOGGER.debug(f"copytree('{comparisons_dir}', '{dst_dir}')")
    shutil.copytree(comparisons_dir, dst_dir, ignore=shutil.ignore_patterns("*.json"))

    return comparisons, renderers


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


def main(argv: list[str] | None = None):

    cli = get_cli(argv)
    work_dir: Path = cli.work_dir
    build_dir: Path = cli.target_dir
    publish: bool = cli.publish

    def expand_siteurl(path: str) -> str:
        if publish:
            return f"{SITEURL}/{path}"
        return path

    work_dir.mkdir(exist_ok=True)

    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(exist_ok=True)

    comparisons_dir = build_dir / "img"
    LOGGER.info(f"building comparisons to '{comparisons_dir}'")
    comparisons, renderers = build_comparisons(
        work_dir=work_dir,
        dst_dir=comparisons_dir,
    )
    comparisons = {comparison.source: comparison for comparison in comparisons}

    jinja_env = get_jinja_env(build_dir)
    comparison_template = jinja_env.get_template("comparison.html")

    def conformize_paths(p: str) -> str:
        p = Path("img", p)
        return p.as_posix()

    global_ctx = {
        "SITENAME": SITENAME,
        "SITEICON": expand_siteurl(SITEICON),
        "STYLESHEETS": [CSS_PATH.name],
        "COMPARISONS": list(comparisons.keys()),
        "FOOTER": FOOTER,
        "BUILD_DATE": datetime.datetime.today().isoformat(timespec="minutes"),
        "META_DESCRIPTION": META_DESCRIPTION,
        "META_IMAGE": expand_siteurl(META_IMAGE),
    }

    for filename, comparison in comparisons.items():
        comparison.edit_paths(callback=conformize_paths)
        page_ctx = {
            "Comparison": comparison,
            "NAV_ACTIVE": filename,
        }
        page_ctx.update(global_ctx)
        html = comparison_template.render(**page_ctx)
        html_path = build_dir / f"{filename}.html"
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
    for resource_path in STATIC_RESOURCES:
        shutil.copy(resource_path, build_dir / resource_path.name)

    LOGGER.info("site build finished")


if __name__ == "__main__":
    lxmpicturelab.configure_logging()
    main()
