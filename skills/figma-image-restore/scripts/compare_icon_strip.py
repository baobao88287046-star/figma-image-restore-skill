#!/usr/bin/env python3
"""Targeted comparison for small icon/control strips."""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat


def parse_region(value: str) -> tuple[str, tuple[int, int, int, int]]:
    try:
        name, coords = value.split(":", 1)
        x, y, w, h = [int(part) for part in coords.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Region must be formatted as name:x,y,w,h") from exc
    return name, (x, y, x + w, y + h)


def foreground_mask(image: Image.Image) -> np.ndarray:
    gray = np.array(image.convert("L"))
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blur, 40, 130)
    adaptive = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, -3
    )
    mask = cv2.bitwise_or(edges, adaptive)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8), iterations=1)
    return mask


def contour_stats(mask: np.ndarray) -> dict:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    areas = [cv2.contourArea(contour) for contour in contours if cv2.contourArea(contour) >= 2]
    total_area = float(sum(areas))
    return {
        "contour_count": len(areas),
        "foreground_ratio": round(total_area / float(mask.shape[0] * mask.shape[1]), 5),
        "median_contour_area": round(float(np.median(areas)) if areas else 0.0, 3),
    }


def edge_metrics(source: Image.Image, render: Image.Image) -> dict:
    if source.size != render.size:
        render = render.resize(source.size, Image.Resampling.LANCZOS)
    src_edges = source.convert("L").filter(ImageFilter.FIND_EDGES)
    ren_edges = render.convert("L").filter(ImageFilter.FIND_EDGES)
    diff = ImageChops.difference(src_edges, ren_edges)
    edge_mae = ImageStat.Stat(diff).mean[0] / 255.0

    src_mask = foreground_mask(source)
    ren_mask = foreground_mask(render)
    mask_diff = cv2.absdiff(src_mask, ren_mask)
    mask_delta = float(np.mean(mask_diff)) / 255.0
    src_stats = contour_stats(src_mask)
    ren_stats = contour_stats(ren_mask)
    return {
        "normalized_edge_mae": round(edge_mae, 5),
        "normalized_mask_delta": round(mask_delta, 5),
        "source": src_stats,
        "render": ren_stats,
        "contour_count_delta": ren_stats["contour_count"] - src_stats["contour_count"],
        "foreground_ratio_delta": round(ren_stats["foreground_ratio"] - src_stats["foreground_ratio"], 5),
    }


def contact_sheet(source: Image.Image, render: Image.Image, output: Path, label: str) -> None:
    scale = max(1, min(4, 360 // max(1, source.width)))
    src = source.resize((source.width * scale, source.height * scale), Image.Resampling.NEAREST).convert("RGB")
    ren = render.resize((render.width * scale, render.height * scale), Image.Resampling.NEAREST).convert("RGB")
    pad = 16
    label_h = 28
    canvas = Image.new("RGB", (src.width + ren.width + pad * 3, max(src.height, ren.height) + label_h + pad * 2), (8, 10, 12))
    draw = ImageDraw.Draw(canvas)
    draw.text((pad, pad), f"source {label}", fill=(235, 240, 245))
    draw.text((pad * 2 + src.width, pad), f"render {label}", fill=(235, 240, 245))
    canvas.paste(src, (pad, pad + label_h))
    canvas.paste(ren, (pad * 2 + src.width, pad + label_h))
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("render", type=Path)
    parser.add_argument("--region", action="append", type=parse_region, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--label", default="icon_compare")
    parser.add_argument("--max-edge-mae", type=float, default=0.22)
    parser.add_argument("--max-mask-delta", type=float, default=0.28)
    parser.add_argument("--max-contour-count-delta-ratio", type=float, default=0.8)
    args = parser.parse_args()

    source_path = args.source.expanduser().resolve()
    render_path = args.render.expanduser().resolve()
    if not source_path.exists() or not render_path.exists():
        print("Source or render image missing", file=sys.stderr)
        return 2
    source = Image.open(source_path).convert("RGB")
    render = Image.open(render_path).convert("RGB")
    if source.size != render.size:
        render = render.resize(source.size, Image.Resampling.LANCZOS)

    outdir = args.outdir.expanduser().resolve()
    results = []
    for name, box in args.region:
        src_crop = source.crop(box)
        ren_crop = render.crop(box)
        metrics = edge_metrics(src_crop, ren_crop)
        source_count = max(1, metrics["source"]["contour_count"])
        contour_delta_ratio = abs(metrics["contour_count_delta"]) / source_count
        metrics["contour_count_delta_ratio"] = round(contour_delta_ratio, 5)
        passed = (
            metrics["normalized_edge_mae"] <= args.max_edge_mae
            and metrics["normalized_mask_delta"] <= args.max_mask_delta
            and contour_delta_ratio <= args.max_contour_count_delta_ratio
        )
        contact = outdir / f"{args.label}_{name}.png"
        contact_sheet(src_crop, ren_crop, contact, name)
        results.append({"name": name, "box": box, "metrics": metrics, "passed": passed, "contact_sheet": str(contact)})

    payload = {
        "ok": all(item["passed"] for item in results),
        "source": str(source_path),
        "render": str(render_path),
        "thresholds": {
            "max_edge_mae": args.max_edge_mae,
            "max_mask_delta": args.max_mask_delta,
            "max_contour_count_delta_ratio": args.max_contour_count_delta_ratio,
        },
        "regions": results,
    }
    report = outdir / f"{args.label}_icon_report.json"
    outdir.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    payload["report"] = str(report)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
