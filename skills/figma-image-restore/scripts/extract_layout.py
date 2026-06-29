#!/usr/bin/env python3
"""Extract coarse layout boxes from a flattened UI screenshot.

This heuristic pass is meant to prevent purely loose absolute positioning. It
detects likely cards, media blocks, text clusters, and icon-sized components,
then writes a JSON report and annotated PNG for review.
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw


def clamp_box(x: int, y: int, w: int, h: int, width: int, height: int) -> dict:
    x = max(0, min(x, width - 1))
    y = max(0, min(y, height - 1))
    w = max(1, min(w, width - x))
    h = max(1, min(h, height - y))
    return {"x": int(x), "y": int(y), "width": int(w), "height": int(h)}


def iou(a: dict, b: dict) -> float:
    ax2, ay2 = a["x"] + a["width"], a["y"] + a["height"]
    bx2, by2 = b["x"] + b["width"], b["y"] + b["height"]
    ix1, iy1 = max(a["x"], b["x"]), max(a["y"], b["y"])
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    union = a["width"] * a["height"] + b["width"] * b["height"] - inter
    return inter / union if union else 0.0


def dedupe(items: list[dict], threshold: float = 0.65) -> list[dict]:
    kept = []
    for item in sorted(items, key=lambda value: value["box"]["width"] * value["box"]["height"], reverse=True):
        if all(iou(item["box"], other["box"]) < threshold for other in kept):
            kept.append(item)
    return kept


def classify_box(box: dict, image_area: int) -> str:
    w, h = box["width"], box["height"]
    area = w * h
    ratio = w / h
    if area > image_area * 0.08 and ratio > 1.15:
        return "hero_or_section"
    if area > image_area * 0.012 and w > 120 and h > 60:
        return "card_or_media"
    if 12 <= w <= 96 and 12 <= h <= 96:
        return "icon_or_control"
    if h <= 44 and w >= 28:
        return "text_cluster"
    return "component"


def find_boxes(image_bgr: np.ndarray) -> list[dict]:
    height, width = image_bgr.shape[:2]
    image_area = width * height
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    # Edges catch rounded cards and icon outlines in dark UI.
    edges = cv2.Canny(gray, 36, 112)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)

    # Bright/dark contrast catches text and high-contrast media blocks.
    blur = cv2.GaussianBlur(gray, (0, 0), 5)
    local = cv2.absdiff(gray, blur)
    _, contrast = cv2.threshold(local, 12, 255, cv2.THRESH_BINARY)
    mask = cv2.bitwise_or(edges, contrast)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8), iterations=1)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    items = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        if area < 90 or area > image_area * 0.72:
            continue
        if w < 6 or h < 6:
            continue
        box = clamp_box(x, y, w, h, width, height)
        label = classify_box(box, image_area)
        items.append({"type": label, "box": box, "area": int(area)})

    # Add larger card-like rectangles from contours on a softened threshold.
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    for candidate in [thresh, cv2.bitwise_not(thresh)]:
        candidate = cv2.morphologyEx(candidate, cv2.MORPH_CLOSE, np.ones((19, 19), np.uint8), iterations=1)
        contours, _ = cv2.findContours(candidate, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            area = w * h
            if image_area * 0.006 <= area <= image_area * 0.62 and w > 40 and h > 28:
                box = clamp_box(x, y, w, h, width, height)
                items.append({"type": classify_box(box, image_area), "box": box, "area": int(area)})

    return dedupe(items)


def draw_overlay(source: Path, items: list[dict], output: Path) -> None:
    image = Image.open(source).convert("RGB")
    draw = ImageDraw.Draw(image)
    colors = {
        "hero_or_section": (0, 220, 255),
        "card_or_media": (255, 210, 80),
        "icon_or_control": (180, 120, 255),
        "text_cluster": (80, 255, 160),
        "component": (255, 120, 120),
    }
    for item in items:
        box = item["box"]
        color = colors.get(item["type"], (255, 120, 120))
        rect = (box["x"], box["y"], box["x"] + box["width"], box["y"] + box["height"])
        draw.rectangle(rect, outline=color, width=2)
        draw.text((box["x"], max(0, box["y"] - 12)), item["type"], fill=color)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--overlay", type=Path)
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    if not source.exists():
        print(f"Source not found: {source}", file=sys.stderr)
        return 2

    image = cv2.imread(str(source))
    if image is None:
        print(f"Could not read image: {source}", file=sys.stderr)
        return 2
    items = find_boxes(image)
    payload = {
        "source": str(source),
        "width": int(image.shape[1]),
        "height": int(image.shape[0]),
        "items": items,
        "counts": {},
    }
    for item in items:
        payload["counts"][item["type"]] = payload["counts"].get(item["type"], 0) + 1

    out = args.out.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    overlay = args.overlay.expanduser().resolve() if args.overlay else out.with_suffix(".overlay.png")
    draw_overlay(source, items, overlay)
    payload["overlay"] = str(overlay)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
