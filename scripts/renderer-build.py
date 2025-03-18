import argparse
import logging
import shutil
import sys
import time
from pathlib import Path

from lxmpicturelab import configure_logging
from lxmpicturelab.renderer import RENDERER_BUILDERS
from lxmpicturelab.renderer import RENDERER_BUILDERS_BY_ID

LOGGER = logging.getLogger(Path(__file__).stem)


def get_cli(argv: list[str] | None = None) -> argparse.Namespace:
    argv = argv or sys.argv[1:]
    parser = argparse.ArgumentParser(
        description="Generates the renderers resources and their configuration file.",
    )
    parser.add_argument(
        "identifier",
        type=str,
        choices=[b.identifier for b in RENDERER_BUILDERS],
        help="renderer identifier to build",
    )
    parser.add_argument(
        "target_dir",
        type=Path,
        help="filesystem path to a directory that may not exist.",
    )
    parser.add_argument(
        "--force-overwrite",
        action="store_true",
        help="If specified, force the build of the renderer even its already exists.",
    )
    parsed = parser.parse_args(argv)
    return parsed


def main(argv: list[str] | None = None):
    cli = get_cli(argv)
    stime = time.time()

    u_identifier: str = cli.identifier
    u_target_dir: Path = cli.target_dir
    u_force_overwrite: bool = cli.force_overwrite

    LOGGER.debug(f"{u_identifier=}")
    LOGGER.debug(f"{u_target_dir=}")
    LOGGER.debug(f"{u_force_overwrite=}")

    BuilderT = RENDERER_BUILDERS_BY_ID.get(u_identifier)
    if not BuilderT:
        print(
            f"ERROR: Unknown renderer identifier '{u_identifier}'\n"
            f"Must be on of {RENDERER_BUILDERS_BY_ID.keys()}",
            file=sys.stderr,
        )
        sys.exit(1)

    if u_target_dir.exists() and not u_force_overwrite:
        LOGGER.debug(f"⏩ skiping existing renderer '{u_identifier}'")
        return

    if u_target_dir.exists():
        shutil.rmtree(u_target_dir)
    u_target_dir.mkdir()

    builder = BuilderT(path=u_target_dir)

    LOGGER.info(f"🛠️ building renderer '{u_identifier};")
    builder.build()

    renderer = builder.get_renderer()
    as_json = renderer.to_json(indent=4, sort_keys=True)
    renderer_path = u_target_dir / f"{renderer.filename}.json"
    LOGGER.info(f"💾 writing '{renderer_path}'")
    renderer_path.write_text(as_json)

    LOGGER.info(f"✅ finished in {time.time() - stime:.1f}s")


if __name__ == "__main__":
    configure_logging()
    main()
