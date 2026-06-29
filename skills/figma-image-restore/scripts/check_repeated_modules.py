#!/usr/bin/env python3
"""Check repeated SVG UI modules for sibling alignment drift."""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def parse_float(value: Optional[str], default: float = 0.0) -> float:
    if not value:
        return default
    match = NUMBER_RE.search(value)
    return float(match.group(0)) if match else default


def parse_style(style: Optional[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    if not style:
        return result
    for part in style.split(";"):
        if ":" in part:
            key, value = part.split(":", 1)
            result[key.strip()] = value.strip()
    return result


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


@dataclass
class Box:
    name: str
    x: float
    y: float
    w: float
    h: float
    partial: bool = False

    def contains(self, x: float, y: float, slack: float = 1.0) -> bool:
        return self.x - slack <= x <= self.x + self.w + slack and self.y - slack <= y <= self.y + self.h + slack


@dataclass
class TextNode:
    text: str
    x: float
    y: float
    font_size: float
    font_weight: str


@dataclass
class ImageNode:
    x: float
    y: float
    w: float
    h: float


def parse_box(spec: str, partial: bool = False) -> Box:
    if ":" not in spec:
        raise argparse.ArgumentTypeError(f"Expected name:x,y,w,h, got {spec}")
    name, coords = spec.split(":", 1)
    parts = coords.split(",")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(f"Expected name:x,y,w,h, got {spec}")
    x, y, w, h = (float(part) for part in parts)
    return Box(name=name, x=x, y=y, w=w, h=h, partial=partial)


def collect_svg_nodes(svg_path: Path) -> tuple[list[TextNode], list[ImageNode]]:
    root = ET.parse(svg_path).getroot()
    texts: list[TextNode] = []
    images: list[ImageNode] = []

    for elem in root.iter():
        tag = local_name(elem.tag)
        style = parse_style(elem.attrib.get("style"))
        if tag == "text":
            text = " ".join("".join(elem.itertext()).split())
            if not text:
                continue
            x = parse_float(elem.attrib.get("x") or style.get("x"))
            y = parse_float(elem.attrib.get("y") or style.get("y"))
            font_size = parse_float(elem.attrib.get("font-size") or style.get("font-size"), 0.0)
            font_weight = elem.attrib.get("font-weight") or style.get("font-weight") or ""
            texts.append(TextNode(text=text, x=x, y=y, font_size=font_size, font_weight=font_weight))
        elif tag == "image":
            x = parse_float(elem.attrib.get("x") or style.get("x"))
            y = parse_float(elem.attrib.get("y") or style.get("y"))
            w = parse_float(elem.attrib.get("width") or style.get("width"))
            h = parse_float(elem.attrib.get("height") or style.get("height"))
            images.append(ImageNode(x=x, y=y, w=w, h=h))

    return texts, images


def classify_text(node: TextNode) -> str:
    text = node.text.strip()
    if "押金" in text:
        return "helper"
    if "¥" in text or text.startswith("￥"):
        return "price"
    if "/天" in text or text == "/天":
        return "unit"
    if re.search(r"\d", text) and any(sep in text for sep in ["|", "万", "K", "F", "mm"]):
        return "subtitle"
    return "title"


def module_metrics(box: Box, texts: list[TextNode], images: list[ImageNode]) -> dict[str, object]:
    inside_texts = [node for node in texts if box.contains(node.x, node.y)]
    inside_images = [node for node in images if box.contains(node.x, node.y) or box.contains(node.x + node.w, node.y + node.h)]

    metrics: dict[str, object] = {
        "name": box.name,
        "partial": box.partial,
        "box": {"x": box.x, "y": box.y, "w": box.w, "h": box.h},
        "text_count": len(inside_texts),
        "image_count": len(inside_images),
    }

    by_kind: dict[str, TextNode] = {}
    for node in sorted(inside_texts, key=lambda item: (item.y, item.x)):
        kind = classify_text(node)
        by_kind.setdefault(kind, node)

    for kind, node in by_kind.items():
        metrics[f"{kind}_text"] = node.text
        metrics[f"{kind}_x_offset"] = round(node.x - box.x, 3)
        metrics[f"{kind}_y_offset"] = round(node.y - box.y, 3)
        metrics[f"{kind}_font_size"] = round(node.font_size, 3)
        metrics[f"{kind}_font_weight"] = node.font_weight

    if inside_images:
        image = max(inside_images, key=lambda item: item.w * item.h)
        metrics["image_x_offset"] = round(image.x - box.x, 3)
        metrics["image_y_offset"] = round(image.y - box.y, 3)
        metrics["image_w"] = round(image.w, 3)
        metrics["image_h"] = round(image.h, 3)
        metrics["image_aspect"] = round(image.w / image.h, 5) if image.h else None

    return metrics


def compare_metrics(rows: list[dict[str, object]], tolerance: float, font_tolerance: float) -> list[str]:
    issues: list[str] = []
    anchors = [row for row in rows if not row.get("partial")]
    if not anchors:
        anchors = rows
    baseline = anchors[0] if anchors else {}

    layout_keys = [
        "title_x_offset",
        "subtitle_x_offset",
        "price_x_offset",
        "unit_x_offset",
        "helper_x_offset",
        "image_x_offset",
        "image_y_offset",
    ]
    font_keys = [
        "title_font_size",
        "subtitle_font_size",
        "price_font_size",
        "unit_font_size",
        "helper_font_size",
    ]

    for row in rows[1:]:
        for key in layout_keys:
            if key in baseline and key in row:
                delta = abs(float(row[key]) - float(baseline[key]))
                if delta > tolerance:
                    issues.append(f"{row['name']} {key} drift {delta:.2f}px from {baseline['name']}")
        for key in font_keys:
            if key in baseline and key in row:
                delta = abs(float(row[key]) - float(baseline[key]))
                if delta > font_tolerance:
                    issues.append(f"{row['name']} {key} drift {delta:.2f}px from {baseline['name']}")

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("svg", type=Path)
    parser.add_argument("--card", action="append", default=[], help="Repeated module box as name:x,y,w,h")
    parser.add_argument("--partial-card", action="append", default=[], help="Clipped preview card as full logical name:x,y,w,h")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--tolerance", type=float, default=3.0)
    parser.add_argument("--font-tolerance", type=float, default=0.1)
    args = parser.parse_args()

    boxes = [parse_box(spec) for spec in args.card]
    boxes.extend(parse_box(spec, partial=True) for spec in args.partial_card)
    if len(boxes) < 2:
        raise SystemExit("Provide at least two --card/--partial-card boxes")

    texts, images = collect_svg_nodes(args.svg)
    rows = [module_metrics(box, texts, images) for box in boxes]
    issues = compare_metrics(rows, args.tolerance, args.font_tolerance)
    report = {
        "svg": str(args.svg),
        "ok": not issues,
        "tolerance": args.tolerance,
        "font_tolerance": args.font_tolerance,
        "modules": rows,
        "issues": issues,
    }

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
