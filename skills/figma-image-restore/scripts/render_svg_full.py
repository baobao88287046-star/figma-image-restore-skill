#!/usr/bin/env python3
"""Render a generated SVG to a full-size PNG for restoration QA.

The preferred renderer is the bundled Codex Node runtime plus sharp because it
preserves tall mobile screenshots. QuickLook is kept as a last-resort macOS
fallback and is rejected when it crops the output to the wrong dimensions.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image


DEFAULT_NODE = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
DEFAULT_NODE_MODULES = (
    Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules"
)


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def run_sharp(svg: Path, output: Path, node: Path, node_modules: Path, density: int) -> dict:
    script = """
const sharp = require("sharp");
const input = process.argv[1];
const output = process.argv[2];
const density = Number(process.argv[3] || 72);
sharp(input, { density, unlimited: true })
  .png()
  .toFile(output)
  .then(info => console.log(JSON.stringify(info)))
  .catch(error => { console.error(error && error.stack ? error.stack : String(error)); process.exit(1); });
"""
    env = os.environ.copy()
    env["NODE_PATH"] = str(node_modules)
    result = subprocess.run(
        [str(node), "-e", script, str(svg), str(output), str(density)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "sharp render failed")
    try:
        return json.loads(result.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise RuntimeError(f"sharp returned unexpected output: {result.stdout!r}") from exc


def run_quicklook(svg: Path, output: Path, size: int) -> dict:
    if not shutil.which("qlmanage"):
        raise RuntimeError("qlmanage is not available")
    with tempfile.TemporaryDirectory(prefix="figma-restore-ql-") as tmp:
        tmp_path = Path(tmp)
        result = subprocess.run(
            ["qlmanage", "-t", "-s", str(size), "-o", str(tmp_path), str(svg)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "qlmanage failed")
        generated = tmp_path / f"{svg.name}.png"
        if not generated.exists():
            raise RuntimeError(f"QuickLook did not create expected file: {generated}")
        shutil.copyfile(generated, output)
    width, height = image_size(output)
    return {"format": "png", "width": width, "height": height, "renderer": "quicklook"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("svg", type=Path)
    parser.add_argument("--out", type=Path, help="Output PNG path. Defaults beside SVG.")
    parser.add_argument("--expected-width", type=int)
    parser.add_argument("--expected-height", type=int)
    parser.add_argument("--density", type=int, default=72)
    parser.add_argument("--node", type=Path, default=DEFAULT_NODE)
    parser.add_argument("--node-modules", type=Path, default=DEFAULT_NODE_MODULES)
    parser.add_argument("--allow-quicklook", action="store_true")
    args = parser.parse_args()

    svg = args.svg.expanduser().resolve()
    if not svg.exists():
        print(f"SVG not found: {svg}", file=sys.stderr)
        return 2

    output = (
        args.out.expanduser().resolve()
        if args.out
        else svg.with_name(f"{svg.stem}_render_full.png")
    )
    output.parent.mkdir(parents=True, exist_ok=True)

    attempts = []
    renderer = None
    info = None
    try:
        if not args.node.exists():
            raise RuntimeError(f"Node runtime not found: {args.node}")
        if not args.node_modules.exists():
            raise RuntimeError(f"node_modules not found: {args.node_modules}")
        info = run_sharp(svg, output, args.node, args.node_modules, args.density)
        renderer = "sharp"
    except Exception as exc:
        attempts.append({"renderer": "sharp", "error": str(exc)})
        if not args.allow_quicklook:
            print(json.dumps({"ok": False, "attempts": attempts}, ensure_ascii=False, indent=2))
            return 1
        try:
            size = args.expected_width or 1008
            info = run_quicklook(svg, output, size)
            renderer = "quicklook"
        except Exception as quicklook_exc:
            attempts.append({"renderer": "quicklook", "error": str(quicklook_exc)})
            print(json.dumps({"ok": False, "attempts": attempts}, ensure_ascii=False, indent=2))
            return 1

    width, height = image_size(output)
    dimension_ok = True
    if args.expected_width is not None and width != args.expected_width:
        dimension_ok = False
    if args.expected_height is not None and height != args.expected_height:
        dimension_ok = False

    payload = {
        "ok": dimension_ok,
        "renderer": renderer,
        "svg": str(svg),
        "output": str(output),
        "width": width,
        "height": height,
        "expected_width": args.expected_width,
        "expected_height": args.expected_height,
        "renderer_info": info,
        "attempts": attempts,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if dimension_ok else 1


if __name__ == "__main__":
    sys.exit(main())
