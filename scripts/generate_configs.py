from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.common import GENERATED_DIR, all_devices, load_vars, render_device_config
from scripts.validate_vars import validate_all


def generate_configs(output_dir: Path = GENERATED_DIR) -> list[Path]:
    config = load_vars()
    errors = validate_all(config)
    if errors:
        raise SystemExit("Validation failed before render:\n" + "\n".join(f"- {e}" for e in errors))

    output_dir.mkdir(parents=True, exist_ok=True)
    rendered_files: list[Path] = []
    for device in all_devices(config):
        rendered = render_device_config(config, device).rstrip() + "\n"
        suffix = ".policy.txt" if device["role"] == "firewall" else ".cfg"
        output_path = output_dir / f"{device['name']}{suffix}"
        output_path.write_text(rendered, encoding="utf-8")
        rendered_files.append(output_path)
    return rendered_files


def main() -> int:
    parser = argparse.ArgumentParser(description="Render network configs to generated_configs/")
    parser.add_argument("--output-dir", type=Path, default=GENERATED_DIR)
    args = parser.parse_args()
    rendered_files = generate_configs(args.output_dir)
    print(f"Rendered {len(rendered_files)} files:")
    for path in rendered_files:
        print(f"- {path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
