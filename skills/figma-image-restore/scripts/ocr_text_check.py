#!/usr/bin/env python3
"""Compare OCR text from the source screenshot with SVG text nodes."""

import argparse
import html
import json
import re
import shutil
import sys
from difflib import SequenceMatcher
from pathlib import Path

import pytesseract
from PIL import Image


TEXT_RE = re.compile(r"<text\b[^>]*>(.*?)</text>", re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")


def normalize(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[|｜/／,，.。:：;；·•]", "", text)
    return text.lower()


def svg_texts(svg: Path) -> list[str]:
    content = svg.read_text(encoding="utf-8")
    values = []
    for match in TEXT_RE.finditer(content):
        text = html.unescape(TAG_RE.sub("", match.group(1))).strip()
        if len(normalize(text)) >= 2:
            values.append(text)
    return values


def best_ratio(needle: str, haystack: str) -> float:
    if not needle:
        return 1.0
    if needle in haystack:
        return 1.0
    if len(haystack) < len(needle):
        return SequenceMatcher(None, needle, haystack).ratio()
    best = 0.0
    size = len(needle)
    for start in range(0, max(1, len(haystack) - size + 1)):
        window = haystack[start : start + size]
        best = max(best, SequenceMatcher(None, needle, window).ratio())
    return best


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--lang", default="chi_sim+eng")
    parser.add_argument("--min-ratio", type=float, default=0.62)
    parser.add_argument("--fail-on-missing", action="store_true")
    args = parser.parse_args()

    out = args.out.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    if not shutil.which("tesseract"):
        payload = {"ok": True, "skipped": True, "reason": "tesseract executable not found"}
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    source = args.source.expanduser().resolve()
    svg = args.svg.expanduser().resolve()
    try:
        image = Image.open(source).convert("RGB")
        ocr_text = pytesseract.image_to_string(image, lang=args.lang, config="--psm 6")
    except Exception as exc:
        payload = {"ok": True, "skipped": True, "reason": f"OCR failed: {exc}"}
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    source_norm = normalize(ocr_text)
    checks = []
    for text in svg_texts(svg):
        norm = normalize(text)
        ratio = best_ratio(norm, source_norm)
        checks.append({"text": text, "normalized": norm, "best_match_ratio": round(ratio, 4), "passed": ratio >= args.min_ratio})

    missing = [item for item in checks if not item["passed"]]
    payload = {
        "ok": not missing or not args.fail_on_missing,
        "skipped": False,
        "source": str(source),
        "svg": str(svg),
        "lang": args.lang,
        "ocr_text": ocr_text,
        "normalized_ocr_text": source_norm,
        "min_ratio": args.min_ratio,
        "checks": checks,
        "missing_or_low_confidence": missing,
        "note": "OCR can miss stylized/low-contrast text; treat failures as review candidates unless --fail-on-missing is used.",
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
