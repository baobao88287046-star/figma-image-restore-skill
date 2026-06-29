#!/usr/bin/env python3
"""Conservative SVG text-bound check for screenshot-to-Figma restorations."""

import argparse
import html
import re
import sys
from pathlib import Path


TEXT_RE = re.compile(r"<text\b([^>]*)>(.*?)</text>", re.DOTALL)
ATTR_RE = re.compile(r'([a-zA-Z:-]+)="([^"]*)"')
TAG_RE = re.compile(r"<[^>]+>")


def estimate_width(text: str, font_size: float) -> float:
    width_units = 0.0
    for ch in text:
        if ch.isspace():
            width_units += 0.35
        elif ord(ch) > 127:
            width_units += 1.0
        elif ch in "MW@#%&":
            width_units += 0.85
        elif ch in "il.,:;|!":
            width_units += 0.3
        else:
            width_units += 0.56
    return width_units * font_size


def parse_float(attrs, name, default=0.0):
    try:
        return float(attrs.get(name, default))
    except ValueError:
        return default


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("svg", type=Path)
    parser.add_argument("--screen-width", type=float, default=512)
    parser.add_argument("--safe-margin", type=float, default=20)
    parser.add_argument(
        "--ignore",
        action="append",
        default=["›", "更多 ›", "全部订单 ›"],
        help="Exact text to ignore; can be provided multiple times.",
    )
    args = parser.parse_args()

    svg = args.svg.read_text(encoding="utf-8")
    issues = []

    for match in TEXT_RE.finditer(svg):
        attrs = dict(ATTR_RE.findall(match.group(1)))
        text = html.unescape(TAG_RE.sub("", match.group(2)).strip())
        if not text or text in args.ignore:
            continue

        x = parse_float(attrs, "x")
        y = parse_float(attrs, "y")
        font_size = parse_float(attrs, "font-size", 14.0)
        anchor = attrs.get("text-anchor", "start")
        width = estimate_width(text, font_size)

        if anchor == "middle":
            left, right = x - width / 2, x + width / 2
        elif anchor == "end":
            left, right = x - width, x
        else:
            left, right = x, x + width

        screen = int(x // args.screen_width)
        safe_left = screen * args.screen_width + args.safe_margin
        safe_right = (screen + 1) * args.screen_width - args.safe_margin

        if left < safe_left or right > safe_right:
            issues.append(
                {
                    "text": text,
                    "x": x,
                    "y": y,
                    "font_size": font_size,
                    "anchor": anchor,
                    "left_delta": round(left - safe_left, 1),
                    "right_delta": round(right - safe_right, 1),
                }
            )

    if issues:
        for issue in issues:
            print(issue)
        return 1

    print("No text-bound issues found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
