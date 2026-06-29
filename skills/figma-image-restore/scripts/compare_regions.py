#!/usr/bin/env python3
"""Compare a source screenshot and rendered reconstruction by regions.

This is not a magic aesthetic judge. It gives the restoration loop a repeatable
gate: full-screen and region-level visual differences, edge differences, and
side-by-side evidence images that can be inspected by the user.
"""

import argparse
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat


def parse_region(value: str) -> tuple[str, tuple[int, int, int, int]]:
    try:
        name, coords = value.split(":", 1)
        x, y, w, h = [int(part) for part in coords.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Region must be formatted as name:x,y,w,h"
        ) from exc
    if w <= 0 or h <= 0:
        raise argparse.ArgumentTypeError("Region width/height must be positive")
    return name, (x, y, x + w, y + h)


def normalized_metrics(source: Image.Image, render: Image.Image) -> dict:
    if source.size != render.size:
        render = render.resize(source.size, Image.Resampling.LANCZOS)
    src = source.convert("RGB")
    ren = render.convert("RGB")
    diff = ImageChops.difference(src, ren)
    stat = ImageStat.Stat(diff)
    mae = sum(stat.mean) / 3.0
    rms = math.sqrt(sum(value * value for value in stat.rms) / 3.0)
    extrema = diff.getextrema()
    max_delta = max(channel[1] for channel in extrema)

    src_edges = src.convert("L").filter(ImageFilter.FIND_EDGES)
    ren_edges = ren.convert("L").filter(ImageFilter.FIND_EDGES)
    edge_diff = ImageChops.difference(src_edges, ren_edges)
    edge_mae = ImageStat.Stat(edge_diff).mean[0]

    return {
        "mae": round(mae, 3),
        "normalized_mae": round(mae / 255.0, 5),
        "rms": round(rms, 3),
        "normalized_rms": round(rms / 255.0, 5),
        "max_delta": int(max_delta),
        "edge_mae": round(edge_mae, 3),
        "normalized_edge_mae": round(edge_mae / 255.0, 5),
    }


def make_contact_sheet(
    source: Image.Image,
    render: Image.Image,
    output: Path,
    title_left: str,
    title_right: str,
    width: int,
) -> None:
    height = round(source.height * width / source.width)
    src = source.resize((width, height), Image.Resampling.LANCZOS).convert("RGB")
    ren = render.resize((width, height), Image.Resampling.LANCZOS).convert("RGB")
    pad = 20
    label = 32
    canvas = Image.new("RGB", (width * 2 + pad * 3, height + label + pad * 2), (6, 10, 13))
    draw = ImageDraw.Draw(canvas)
    draw.text((pad, pad), title_left, fill=(235, 240, 245))
    draw.text((pad * 2 + width, pad), title_right, fill=(235, 240, 245))
    canvas.paste(src, (pad, pad + label))
    canvas.paste(ren, (pad * 2 + width, pad + label))
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("render", type=Path)
    parser.add_argument("--region", action="append", type=parse_region, default=[])
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--label", default="comparison")
    parser.add_argument("--max-normalized-mae", type=float, default=0.16)
    parser.add_argument("--max-region-normalized-mae", type=float, default=0.18)
    parser.add_argument("--contact-width", type=int, default=420)
    args = parser.parse_args()

    source_path = args.source.expanduser().resolve()
    render_path = args.render.expanduser().resolve()
    if not source_path.exists():
        print(f"Source not found: {source_path}", file=sys.stderr)
        return 2
    if not render_path.exists():
        print(f"Render not found: {render_path}", file=sys.stderr)
        return 2

    source = Image.open(source_path).convert("RGB")
    render = Image.open(render_path).convert("RGB")
    if source.size != render.size:
        render = render.resize(source.size, Image.Resampling.LANCZOS)

    outdir = args.outdir.expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    global_metrics = normalized_metrics(source, render)
    global_contact = outdir / f"{args.label}_global.png"
    make_contact_sheet(source, render, global_contact, "source global", args.label, args.contact_width)

    regions = []
    for name, box in args.region:
        src_crop = source.crop(box)
        ren_crop = render.crop(box)
        metrics = normalized_metrics(src_crop, ren_crop)
        contact = outdir / f"{args.label}_{name}.png"
        make_contact_sheet(src_crop, ren_crop, contact, f"source {name}", f"{args.label} {name}", min(500, args.contact_width + 80))
        regions.append(
            {
                "name": name,
                "box": {"x": box[0], "y": box[1], "width": box[2] - box[0], "height": box[3] - box[1]},
                "metrics": metrics,
                "passed": metrics["normalized_mae"] <= args.max_region_normalized_mae,
                "contact_sheet": str(contact),
            }
        )

    passed = global_metrics["normalized_mae"] <= args.max_normalized_mae and all(
        region["passed"] for region in regions
    )
    payload = {
        "ok": passed,
        "source": str(source_path),
        "render": str(render_path),
        "source_size": {"width": source.width, "height": source.height},
        "render_size": {"width": render.width, "height": render.height},
        "thresholds": {
            "max_normalized_mae": args.max_normalized_mae,
            "max_region_normalized_mae": args.max_region_normalized_mae,
        },
        "global": {
            "metrics": global_metrics,
            "passed": global_metrics["normalized_mae"] <= args.max_normalized_mae,
            "contact_sheet": str(global_contact),
        },
        "regions": regions,
    }
    report = outdir / f"{args.label}_report.json"
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
