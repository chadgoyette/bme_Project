from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Optional

from .profiles import Profile, profile_from_default, list_default_profiles
from .runtime import CollectorRunner, Metadata, RunConfig, build_backend
from .ui import CollectorApp

LOGGER = logging.getLogger("collector")

CONFIG_DIR = Path.home() / ".bme690_collect"
CONFIG_PATH = CONFIG_DIR / "config.json"


def load_last_profile_path() -> Optional[Path]:
    if not CONFIG_PATH.exists():
        return None
    try:
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        last = payload.get("last_profile")
        if last:
            path = Path(last)
            if path.exists():
                return path
    except Exception:
        LOGGER.warning("Unable to parse collector config at %s", CONFIG_PATH)
    return None


def save_last_profile_path(path: Path) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"last_profile": str(path)}
    CONFIG_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BME690 Collect Application")
    parser.add_argument("--headless", action="store_true", help="Run without opening the UI.")
    parser.add_argument("--profile", type=Path, help="Path to .bmeprofile file.")
    parser.add_argument("--cycles", type=int, default=10, help="Number of profile cycles to record.")
    parser.add_argument("--skip-cycles", type=int, default=3, help="Number of initial cycles to discard.")
    parser.add_argument("--meta", type=str, help="Metadata JSON string or path to JSON file.")
    parser.add_argument("--log-level", type=str, default="INFO")
    return parser.parse_args(argv)


def load_profile(path: Optional[Path]) -> Profile:
    if path is None:
        return profile_from_default("Broad Sweep (meat)")
    profile = Profile.load(path)
    save_last_profile_path(path)
    return profile


def resolve_metadata(metadata_arg: Optional[str]) -> Metadata:
    if metadata_arg is None:
        raise ValueError("--meta is required in headless mode.")
    if metadata_arg.strip().startswith("{"):
        payload = json.loads(metadata_arg)
    else:
        payload = json.loads(Path(metadata_arg).read_text(encoding="utf-8"))
    return Metadata.from_mapping(payload)


def run_headless(args: argparse.Namespace) -> Path:
    profile = load_profile(args.profile)
    metadata = resolve_metadata(args.meta)
    cycles_target = max(1, int(args.cycles))
    skip_cycles = max(0, int(args.skip_cycles))
    backend = build_backend(profile)
    runner = CollectorRunner(
        RunConfig(
            profile=profile,
            metadata=metadata,
            cycles_target=cycles_target,
            backend=backend,
            profile_hash=profile.hash(),
            skip_cycles=skip_cycles,
        )
    )
    return runner.run()


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(message)s")

    if args.headless:
        try:
            path = run_headless(args)
            LOGGER.info("Headless run complete: %s", path)
            return 0
        except KeyboardInterrupt:
            LOGGER.warning("Headless run interrupted by user.")
            return 1

    last_profile_path = load_last_profile_path()
    if last_profile_path and last_profile_path.exists():
        initial_profile = Profile.load(last_profile_path)
    else:
        initial_profile = profile_from_default("Broad Sweep (meat)")

    def on_profile_selected(profile: Profile) -> None:
        if profile.path:
            save_last_profile_path(profile.path)

    app = CollectorApp(initial_profile=initial_profile, defaults=list_default_profiles(), on_profile_selected=on_profile_selected)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
