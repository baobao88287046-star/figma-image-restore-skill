# Figma Image Restore Skill

Codex skill for restoring PNG/JPG UI screenshots or AI-generated app mockups into editable Figma Web content.

This skill is designed for high-fidelity, iterative image-to-Figma reconstruction:

- Generate editable SVG layers for layout, text, controls, and icons.
- Keep photos/products as cropped raster assets when bitmap detail matters.
- Paste SVG into Figma Web when no Figma desktop plugin or MCP write tool is available.
- Use screenshot comparison, text-bound checks, icon fidelity checks, and versioned Figma frames.

## Install With Codex Skill Installer

In Codex, ask:

```text
Install the skill from https://github.com/baobao88287046-star/figma-image-restore-skill/tree/main/skills/figma-image-restore
```

Or run the installer script directly if available:

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo baobao88287046-star/figma-image-restore-skill \
  --path skills/figma-image-restore
```

Restart Codex after installation so the new skill is discovered.

## Manual Install

```bash
mkdir -p ~/.codex/skills
git clone git@github.com:baobao88287046-star/figma-image-restore-skill.git /tmp/figma-image-restore-skill
cp -R /tmp/figma-image-restore-skill/skills/figma-image-restore ~/.codex/skills/
```

Restart Codex after installation.

## Usage

Ask Codex to use the skill with a screenshot and a Figma link:

```text
Use $figma-image-restore to restore /path/to/mockup.png into this Figma file: https://www.figma.com/design/...
```

For iterative fixes, provide target crops and feedback:

```text
Use $figma-image-restore to compare these problem regions and paste a new version beside the last one.
```

## Contents

```text
skills/figma-image-restore/
├── SKILL.md
├── agents/openai.yaml
└── scripts/check_svg_text_bounds.py
```

`check_svg_text_bounds.py` exits with code 1 when it finds possible overflow candidates. Some edge-preview carousel text may be intentionally clipped; the skill instructs Codex to treat those as explicit exceptions only after visual comparison.

## Notes

This workflow does not promise perfect one-click restoration from a flattened bitmap. It aims for high-fidelity iterative reconstruction, with explicit checks for icon fidelity, crop contamination, text overflow, and Figma-rendered layout drift.
