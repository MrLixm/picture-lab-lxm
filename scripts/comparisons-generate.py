import argparse
import logging
import runpy
import shutil
import sys
import time
from pathlib import Path

import lxmpicturelab
from lxmpicturelab import patch_sysargv
from lxmpicturelab.browse import WORKBENCH_DIR
from lxmpicturelab.browse import find_asset
from lxmpicturelab.comparison import BaseGenerator
from lxmpicturelab.comparison import ComparisonRender
from lxmpicturelab.comparison import ComparisonSession
from lxmpicturelab.comparison import GeneratorExposureBands
from lxmpicturelab.comparison import GeneratorFull
from lxmpicturelab.renderer import OcioConfigRenderer
from lxmpicturelab.renderer import RENDERER_BUILDERS_BY_ID

LOGGER = logging.getLogger(Path(__file__).stem)

THISDIR = Path(__file__).parent

RENDERER_SCRIPT = THISDIR / "renderer-build.py"

WORKBENCH_DIR.mkdir(exist_ok=True)
WORK_DIR = WORKBENCH_DIR / "comparisons"
WORK_DIR.mkdir(exist_ok=True)


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
        command = [renderer_id, str(renderer_dir)]
        with patch_sysargv([str(RENDERER_SCRIPT)] + command):
            runpy.run_path(str(RENDERER_SCRIPT), run_name="__main__")

        renderer_file = next(renderer_dir.glob("*.json"))
        renderer_txt = renderer_file.read_text("utf-8")
        renderer = OcioConfigRenderer.from_json(renderer_txt)
        renderers.append(renderer)

    return renderers


def get_cli(argv: list[str] | None = None) -> argparse.Namespace:
    argv = argv or sys.argv[1:]
    parser = argparse.ArgumentParser(
        description="Generates image to compare image formation algorithm.",
    )
    parser.add_argument(
        "asset_id",
        type=str,
        help="Identifier of the asset to generate comparison for.",
    )
    parser.add_argument(
        "--generator-exposures",
        type=float,
        default=None,
        help=(
            "If specified, generate bands of gradually increasing exposure. "
            "Value is the percentage of image to offset on the x axis in 0-1 range."
        ),
    )
    parser.add_argument(
        "--generator-full",
        type=int,
        default=None,
        help=(
            "If specified, render the whole area of the image and resize "
            "its height to the given size (in pixels)."
        ),
    )
    parser.add_argument(
        "--combined-renderers",
        action="store_true",
        help=(
            "If specified, create an additional image which combine all the image "
            "generated for each renderer."
        ),
    )
    parser.add_argument(
        "--target-dir",
        type=Path,
        default=None,
        help="filesystem path to a directory that may not exist.",
    )
    parser.add_argument(
        "--renderer-dir",
        type=Path,
        default=WORKBENCH_DIR / "renderers",
        help="filesystem path to a directory that may not exist.",
    )
    parsed = parser.parse_args(argv)
    return parsed


def main(argv: list[str] | None = None):
    cli = get_cli(argv)
    stime = time.time()

    asset_id: str = cli.asset_id
    renderer_work_dir: Path = cli.renderer_dir
    target_dir: Path | None = cli.target_dir
    generator_exposure: float | None = cli.generator_exposures
    generator_full: int | None = cli.generator_full
    combined_renderers: bool = cli.combined_renderers

    LOGGER.debug(f"{asset_id=}")
    LOGGER.debug(f"{target_dir=}")
    LOGGER.debug(f"{renderer_work_dir=}")
    LOGGER.debug(f"{combined_renderers=}")

    renderer_ids = list(RENDERER_BUILDERS_BY_ID.keys())
    renderer_work_dir.mkdir(exist_ok=True)
    LOGGER.info(f"🛠️ building {len(renderer_ids)} renderers to '{renderer_work_dir}'")
    renderers = build_renderers(renderer_work_dir, renderer_ids)

    asset = find_asset(asset_id)
    if not asset:
        LOGGER.error(f"No asset with identifier '{asset_id}' found.")
        sys.exit(1)

    target_dir = target_dir or WORKBENCH_DIR / "comparisons" / asset.identifier
    if target_dir.exists():
        LOGGER.debug(f"shutil.rmtree({target_dir})")
        shutil.rmtree(target_dir)
    target_dir.mkdir(exist_ok=True, parents=True)

    generators: list[BaseGenerator] = []
    if generator_exposure is not None:
        generators.append(GeneratorExposureBands(generator_exposure))
    if generator_full is not None:
        generators.append(GeneratorFull(generator_full))

    if not generators:
        LOGGER.warning("no generator created; did you forget --generator-XXX options ?")

    session = ComparisonSession(asset=asset)

    for generator in generators:
        generator_results: dict[str, Path] = {}
        generator_name = generator.shortname
        comparison_src_path = asset.image_path

        for renderer in renderers:
            generation_dst_name = (
                f"{asset.identifier}.{generator_name}.{renderer.filename}.jpg"
            )
            comparison_dst_path = target_dir / generation_dst_name
            comparison = ComparisonRender(
                generator=generator,
                renderer=renderer,
                src_paths=[comparison_src_path],
                dst_path=comparison_dst_path,
            )
            LOGGER.info(f"💫 generating '{comparison_dst_path}'")
            comparison.run()
            session.add_render(comparison)

        # this is an extra comparison but without renderer
        if combined_renderers:
            combined_name = f"{asset.identifier}.{generator_name}.__combined__.jpg"
            combined_path = target_dir / combined_name
            comparison = ComparisonRender(
                generator=generator,
                renderer=None,
                src_paths=list(generator_results.values()),
                dst_path=combined_path,
            )
            LOGGER.info(f"💫 generating combined image to '{combined_path}'")
            comparison.run()
            session.add_render(comparison)

    metadata: str = session.to_json(indent=4)
    metadata_path = target_dir / f"{asset.identifier}.metadata.json"
    LOGGER.info(f"writing metadata to '{metadata_path}'")
    metadata_path.write_text(metadata, encoding="utf-8")

    LOGGER.info(f"✅ finished in {time.time() - stime:.1f}s")


if __name__ == "__main__":
    lxmpicturelab.configure_logging()
    main()
