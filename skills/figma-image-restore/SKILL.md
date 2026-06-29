---
name: figma-image-restore
description: Restore PNG/JPG screenshots or AI-generated app/website mockups into editable Figma Web content. Use this skill whenever the user asks to put an image into Figma, recreate a generated UI image, compare a PNG to a Figma reconstruction, improve missing icons, fix over-compressed image assets, or asks for a repeatable image-to-Figma restoration workflow. Prefer this even when the user does not explicitly say "skill" if the task involves high-fidelity UI image reconstruction for Figma.
---

# Figma Image Restore

Use this skill to turn a static UI image into a Figma Web file with as many editable layers as possible, without assuming Figma desktop or paid APIs are available.

The workflow is iterative. A perfect one-click restore is not realistic from a flattened bitmap, but a high-quality reconstruction is achievable by combining:

- Vector/SVG layers for UI containers, text, controls, and icons.
- Cropped raster layers for photos, avatars, products, and other detailed bitmap regions.
- Figma Web paste/import for delivery when no Figma MCP write tool or desktop plugin is available.
- Comparison passes driven by the user's screenshots and notes.
- Screenshot-based calibration after paste, because Figma's actual text and SVG rendering can differ from local estimates.

## Operating Contract

When Bao provides feedback on a Figma reconstruction, own the iteration loop:

- Treat each user screenshot/comment as an acceptance criterion, not as optional polish.
- Do not mark the work complete until the latest pasted Figma version is checked against the reported issues.
- After every failed or partially fixed pass, update this skill if the failure came from the workflow rather than a one-off coordinate mistake.
- Prefer improving the repeatable loop over repeatedly hand-tuning the same class of issue.

## Capability Boundary

Be explicit about which path is being used:

1. **Figma MCP write path**: Use only if a callable write/import tool such as `mcp__figma__generate_figma_design` is actually available in the current tool list. Do not imply it exists if it is not callable.
2. **Figma Desktop plugin path**: Only useful if the user has Figma desktop and can import a local plugin manifest.
3. **Figma Web SVG path**: Default fallback. Generate an SVG with embedded image assets, copy it to the clipboard, open the user's Figma Web file, and paste it. This is free except for normal Figma account limits and uses no external paid AI/API by default.
4. **Manual browser drawing path**: Last resort. It is slow and usually less accurate than SVG import.

For Bao's current environment, the proven path is **Figma Web SVG paste**:

- Generate local SVG from the source PNG.
- Embed cropped image assets as base64.
- Use Chrome/Computer Use to open Figma Web and paste the SVG.
- Iterate with new versions placed beside earlier versions.

## Input Checklist

Start by inspecting:

- Source image path and dimensions.
- Existing Figma link, if provided.
- Whether the user needs a new draft or an existing file.
- Whether the goal is visual reference, editable UI layers, or production-quality component reconstruction.

If the user provides feedback screenshots, treat them as targeted diff examples. Extract the exact issue:

- Icon shape mismatch.
- Missing icon.
- Wrong control geometry or spacing.
- Blurry or over-compressed image layer.
- Text size, weight, or placement drift.
- Card/background/rounding mismatch.
- Actual Figma-rendered overflow that was not visible in the generated SVG.

## Run Directory and Evidence Pack

For any non-trivial restore or batch test, create a run directory before drawing:

```bash
python3 ~/.codex/skills/figma-image-restore/scripts/init_restore_run.py path/to/source.png --outdir figma_restore_runs
```

Use the generated `restore_manifest.json` as the work ledger:

- Put source reference crops in `crops/`.
- Put extracted/upscaled bitmap assets in `assets/`.
- Put local SVG/PNG renders in `renders/`.
- Put Figma-rendered screenshots in `figma-screenshots/`.
- Put side-by-side source/render/user-feedback comparisons in `comparisons/`.
- Append each pasted Figma version to the manifest with version name, local SVG
  path, Figma node URL, X/Y position, what changed, and remaining issues.

Do not scatter one-off crops in unrelated folders during a repeatable test. If
the user wants to compare several images, create one run directory per source
image and summarize pass/fail using those manifests.

## Required QA Gates

For any high-fidelity restore, treat the scripts in `scripts/` as gates, not
optional helpers. The model can still make design judgments, but the workflow
should fail loudly when evidence is missing.

After generating each SVG version:

1. Run the standard local gates with one command:

   ```bash
   python3 ~/.codex/skills/figma-image-restore/scripts/run_restore_gates.py \
     --source path/to/source.png \
     --svg path/to/restore.svg \
     --manifest path/to/restore_manifest.json \
     --version v1 \
     --screen-width 1008 \
     --screen-height 1792 \
     --region hero:0,40,1008,485 \
     --region dense_cards:0,520,1008,605 \
     --region nav:0,1120,1008,672 \
     --extract-layout \
     --ocr \
     --icon-region bottom_nav:0,1600,1008,192 \
     --module-card hot1:56,120,238,506 \
     --module-card hot2:318,120,238,506 \
     --partial-module-card hot_edge:842,120,238,506
   ```

   This renders the SVG, checks text bounds, compares source/render regions,
   optionally extracts layout, optionally checks OCR text, optionally compares
   icon strips, optionally checks repeated module alignment, writes contact
   sheets and JSON reports, and updates the manifest.

2. If a gate fails, inspect the generated comparison report and contact sheets,
   then fix the SVG and create a new version.

3. After pasting to Figma, add the selected node URL and position to the
   manifest, then verify the pasted version:

   ```bash
   python3 ~/.codex/skills/figma-image-restore/scripts/verify_manifest.py \
     path/to/restore_manifest.json \
     --version v1 \
     --require-figma
   ```

Use the individual scripts directly only when debugging one gate:

- `render_svg_full.py`: full-size SVG rendering.
- `check_svg_text_bounds.py`: conservative text overflow check.
- `compare_regions.py`: source/render visual scoring and contact sheets.
- `extract_layout.py`: source screenshot layout boxes and annotated overlay.
- `ocr_text_check.py`: source OCR vs SVG text consistency check.
- `compare_icon_strip.py`: targeted icon/control silhouette comparison.
- `check_repeated_modules.py`: sibling card/list alignment and typography drift check.
- `verify_manifest.py`: final evidence and metadata gate.

If any gate fails, fix the SVG and create a new version. Do not paste or report
the failed version as accepted unless the user explicitly asks to inspect a
known-failing draft.

## Restoration Strategy

### 1. Analyze and Crop

Use local tools first:

- `file`, `sips`, or Pillow to inspect image size.
- Crop high-value raster regions:
  - Product photos.
  - Portraits and scenic photos.
  - Avatars.
  - Complex camera/lens objects.
- Crop reference regions for comparison:
  - Toggles and controls.
  - Tab bars.
  - Icon strips.
  - Problematic product rows.
- For image cards with editable captions below the photo, crop only the photo
  region. Do a quick visual or OCR-like check that no caption pixels are
  embedded in the bitmap asset before pasting to Figma.

Preserve originals. Put working assets in a clearly named folder such as:

```text
figma_restore_assets/
figma_restore_assets_v2/
figma_debug_crops/
```

### 2. Build Editable SVG

Generate an SVG, not HTML, when targeting Figma Web. Use:

- `<rect>`, `<circle>`, `<path>`, `<text>` for editable-like vector/text import.
- Embedded `data:image/png;base64,...` for bitmap assets.
- One top-level canvas frame matching the source image size.
- Four or more logical subframes when the source contains multiple screens.

For Figma Web paste:

```bash
pbcopy < path/to/restore.svg
```

Then open the Figma Web file and paste with `Cmd+V`.

Before pasting, run deterministic local checks:

```bash
python3 ~/.codex/skills/figma-image-restore/scripts/check_svg_text_bounds.py path/to/restore.svg --screen-width 512 --safe-margin 20
```

Fix reported text-bound issues before pasting, unless the text is intentionally clipped by an edge preview card.

### 3. Icon Fidelity

Do not leave generic square placeholders after the first proof-of-concept pass. Replace them with path-based line icons approximating the source:

- Bottom tabs:
  - Home: filled house when active, outline when inactive.
  - Category: 2x2 rounded grid.
  - Gallery/video: play card or active badge/star if source uses that.
  - Profile: person outline or filled active user.
- Home quick entries:
  - Camera: camera body + lens.
  - Lens: cylindrical bucket/lens shape if source shows one.
  - Accessories: rounded case/box.
  - Drone: four rotors + center body.
  - Light: bulb.
  - More: circular button with horizontal bidirectional mark if source shows it.
- Profile order/function icons:
  - Wallet, truck, bag/use, return, check, ticket, star, clock, pin, headset, help.

Use original reference crops to compare icon geometry, line weight, and active/inactive color.
For small UI icons, do not substitute a generic icon merely because it has the
same meaning. First crop the exact source icon strip, then compare silhouette,
stroke weight, filled dots/badges, tail direction, handles, and small internal
marks. A settings gear must not become a sun, a message bubble must keep its
dot count and tail shape, and order-state icons must match the source object
type rather than a nearby icon-library metaphor.

### 4. Controls and Layout

For controls, match the source geometry before aesthetics:

- Toggle pill must contain the knob inside the track.
- Match exact pill width/height, knob radius, and knob center.
- Verify text does not collide with controls.
- Match card heights and product image aspect ratios.
- For product rows, compare the rendered row against the source row crop, not
  only against text-bound estimates. Check title/subtitle/price/deposit
  baselines, product photo vertical position, CTA x-position, and bottom
  padding inside the card.

Example correction pattern:

```text
If source toggle is 48 x 26 and knob radius is 10, knob center must be inside the pill near x + 35, not outside at x + 58.
```

### 4.5 Container-First Alignment

Treat AI-generated UI screenshots as if they were produced from layout modules,
not as loose absolute-position drawings. Before tuning individual pixels:

- Identify the parent viewport for each app screen, card, carousel, list row,
  tab, or media tile.
- Add viewport clips for every phone/app screen and for scrollable regions
  where content is intentionally cut by the edge. Partial previews should be
  clipped by the container, not allowed to leak into adjacent screens.
- For repeated rows/cards, derive one internal rhythm and reuse it: image
  region, title baseline, subtitle baseline, price baseline, deposit/helper
  baseline, and CTA center should move as a group.
- If an item looks globally too high or low, move the whole content group
  within the card first. Only tune individual elements after the group-level
  alignment matches the source.
- For edge-preview cards, compare the source and render crop at the actual
  viewport boundary. Check for asset contamination such as title pixels embedded
  inside a product photo crop.
- Leave explicit inner padding for long titles and right-side CTAs. Do not let
  a long title borrow space that belongs to the button column.

Before accepting repeated UI modules, run a sibling-invariant gate:

- Extract a metric table from the generated SVG/DOM for every repeated card or
  row: `card_x`, `card_w`, `image_x`, `title_x`, `price_x`, `helper_x`,
  `cta_x`, and the corresponding y baselines.
- Compare derived values such as `title_x - card_x`, `price_x - card_x`, image
  inset, CTA right padding, and baseline gaps across siblings. Differences
  outside 2-3 px need a deliberate reason, such as a centered image or an
  intentionally clipped preview.
- For partially visible carousel cards, do not judge only the visible crop.
  Validate against the full logical card box first, then validate the viewport
  crop. A clipped card still needs the same internal padding as its siblings.
- For partially visible carousel cards, reuse the same internal grid as full
  sibling cards. Title, price, unit, and helper text insets must match the
  sibling cards before viewport clipping is applied; do not move text inward to
  make the visible fragment look self-contained.
- For edge-preview cards, keep text baselines inside the logical card box.
  Do not push price/helper text downward to make room for an extra title line
  if that moves helper text below the card bottom. Prefer tighter vertical
  rhythm, clipping the second title line, or matching the source-visible crop.
- Do not shrink typography just to make partially visible or edge-clipped
  content fit. Repeated modules must keep the same title, price, unit, and
  helper font tokens as their siblings unless the source clearly uses a smaller
  variant. If the app viewport cuts content off, keep the normal size and clip
  or truncate at the viewport/card boundary.
- When a generated UI appears "AI aligned", infer the hidden grid: repeated
  modules usually share the same left padding, vertical rhythm, and control
  alignment even when the bitmap is fuzzy.
- Record the metric table or a short pass/fail summary before pasting. A visual
  screenshot check is the final check, not the only check.
- Use `check_repeated_modules.py`, or the `run_restore_gates.py --module-card`
  wrapper, whenever repeated card/list alignment is part of the acceptance
  criteria. For partially visible carousel cards, pass the full logical card box
  with `--partial-module-card`; do not pass only the visible fragment.

### 5. Image Quality

Be honest about source limits: a small product crop cannot become true high-resolution detail. Improve perceived quality by:

- Avoiding aspect-ratio distortion.
- Displaying product crops close to their source dimensions.
- Upscaling cropped product images 2x-4x locally with Lanczos and light unsharp masking before embedding.
- Using larger original crop boxes when possible.
- Replacing with real high-resolution product assets if the user provides or approves them.

Do not over-enlarge tiny product images in SVG. If the source row shows a 137 x 78 lens, render it at approximately that ratio rather than forcing it into a tall 118 x 94 box.

### 5.5 Photo-Backed Hero Sections

When a banner/hero uses a photo behind text, do not automatically split it into
separate "text block left, image block right" regions. First inspect whether the
source relies on image overlap, dark scrims, or directional gradients for its
visual quality.

For these regions:

- Crop a wider photo background than the visible subject, including the area
  under or near the text when the source uses overlap.
- Recreate the text readability layer with one or more translucent scrims or
  linear gradients rather than a hard vertical edge.
- Keep text and CTA editable above the bitmap, but allow the bitmap to extend
  behind them if the source does.
- Compare the restored hero against the exact source crop before paste. Look
  specifically for hard seams, ghost text from contaminated crops, and loss of
  depth caused by over-darkening or over-masking the image.
- If a hero crop includes source text that will be replaced by editable text,
  cover only the contaminated area with a local scrim/patch; avoid flattening
  the whole region into a plain block.

### 6. Figma Web Delivery

If operating Figma Web through browser/computer use:

1. Open the user's Figma link.
2. If the team file quota blocks new files, create a draft when Figma offers that option.
3. Paste the SVG.
4. If Chrome asks for clipboard permission, explain exactly what will be read from the clipboard and ask for confirmation before clicking Allow.
5. Rename the file or place versioned frames side-by-side.
6. Return the Figma URL and local SVG path.
7. Do not stop here for high-fidelity work. Run the screenshot calibration loop below before reporting done.

Prevent version overlap:

- Do not paste while an older version frame or any of its child layers is
  selected. In Figma Web this often inserts the SVG into the selected frame
  instead of creating a new top-level version.
- Before paste, click an area of the canvas that is clearly outside all
  existing frames, or otherwise confirm the next paste will create a new
  top-level object.
- After paste, compare the selected node id, layer type, and X/Y values with
  the previously selected version. If the node id did not change, or the right
  sidebar says a child type such as `Vector path`, undo immediately and retry
  from a clean canvas selection.
- Never paste a new version while intending it to remain at the same coordinates as the selected existing frame.
- After paste, immediately select the new top-level frame and set an explicit non-overlapping position in the right sidebar.
- Use a simple version grid unless the user asks otherwise: keep `Y` aligned to the baseline version row, and set each new frame at least `frame_width + 240` px to the right of the previous version.
- After typing a new `X` or `Y` value in Figma, press `Return` and re-read the sidebar to confirm the value committed.
- If the new frame accidentally overlaps an older frame, move it before doing visual review or reporting the link.
- Include the selected new node URL in the final response so the user lands on the correct version.

Use versioned names:

```text
Image_25_restore_for_figma_web.svg
Image_25_restore_for_figma_web_v2.svg
Image_25_restore_for_figma_web_v3.svg
```

Also version the top-level Figma object name:

- Before paste, embed the version in SVG metadata: root `id`, `<title>`, and a
  top-level group/frame `id` such as `Image_25_restore_v17_hot_card_font_clip`.
- After paste, verify the selected top-level layer name in Figma. If Figma
  imported it as a generic `Frame`, rename the selected top-level object to the
  versioned name before moving on.
- Do not leave several pasted versions all named `Frame`; the final response
  should include the version name and selected node URL.

### 7. Screenshot Calibration Loop

For pixel-sensitive restoration, add a screenshot check after every Figma paste:

1. Select the newly pasted top-level frame and record its Figma node URL, position, and dimensions from the right sidebar.
2. Capture the Figma viewport, or export/screenshot the selected frame if an export path is available.
   - Prefer an app-scoped/browser screenshot when available.
   - If using a system screenshot command, immediately inspect or OCR the output enough to confirm it captured Figma, not another foreground window.
3. Crop the same problem regions from:
   - the source PNG,
   - the newly pasted Figma screenshot,
   - any user feedback screenshots.
4. Compare local geometry before judging visually:
   - Use color-threshold bounding boxes for buttons, toggles, card backgrounds, and highlighted text.
   - Use conservative text-width estimation with `text-anchor` handling for SVG text.
   - For bitmap cards, crop the rendered image layer and verify it does not
     contain caption/title text that should be editable below the image.
   - For product rows, crop both source and rendered rows and compare baselines
     and card padding visually before paste.
   - Treat right-edge CTA buttons and long titles as high-risk regions; leave extra visual padding because Figma font rendering can be wider than local estimates.
   - For user-reported regions, compare against the exact feedback crop first, then the full original screen.
5. If a region fails, generate a new versioned SVG and paste it beside the previous version.
6. Repeat until:
   - no text-overflow candidates remain,
   - CTA pills sit inside their cards with clear right padding,
   - toggles match the source track/knob bounding boxes,
   - product images preserve source aspect ratio,
   - the user-provided feedback crops no longer reproduce the reported issue.

Prefer objective checks where possible, then use visual review as the final pass. Do not claim a version is final if it has only been generated locally and not pasted/rendered in Figma.

If screenshot comparison is not available in the current environment, explicitly say the version passed local checks only, and ask for or wait for the user's next crop before treating it as accepted.

### 7.2 Local SVG Render Fallback

Before or after pasting to Figma, render the generated SVG locally so the first
comparison can catch obvious scale, typography, crop, and clipping problems.
Prefer Playwright or Chrome when it is already working, because browser
rendering is closer to what Figma Web will import. If that path times out or
returns a blank image, do not skip the evidence step. Use the bundled render
script, which first tries the Codex Node runtime with `sharp` because it
preserves tall mobile screenshots:

```bash
python3 ~/.codex/skills/figma-image-restore/scripts/render_svg_full.py \
  path/to/restore.svg \
  --out path/to/renders/restore_full.png \
  --expected-width 1008 \
  --expected-height 1792
```

On macOS, QuickLook can still be used as a last-resort thumbnail fallback, but
verify the output dimensions because it may crop tall SVGs to a square:

```bash
qlmanage -t -s 1008 -o path/to/renders path/to/restore.svg >/tmp/ql.out 2>/tmp/ql.err
mv path/to/renders/restore.svg.png path/to/renders/restore_render_light.png
```

When using the fallback:

- Save the fallback render in `renders/` with a versioned name.
- Verify `file render.png` or image metadata reports the expected source
  dimensions, such as `1008 x 1792` for a full mobile screenshot.
- Add the render path to `restore_manifest.json`.
- Mark the failure mode as `tooling-gap` only if no script/check currently
  handles the fallback automatically.
- Continue the comparison loop using the fallback PNG; do not report "no local
  render comparison" merely because Playwright failed.

### 7.3 Region Comparison Gate

Use `compare_regions.py` to make the comparison loop repeatable. Start with
three regions for mobile app screens:

- `hero`: first major banner or header.
- `dense_cards`: the densest repeated card/list module.
- `nav`: bottom tabs, timeline, or small icon-heavy strip.

Tune the region boxes to the source image; do not reuse stale boxes from a
different screenshot. Save the generated report JSON and contact sheets in
`comparisons/`, then add their paths to the manifest.

The score is intentionally a coarse gate, not a promise of pixel perfection.
When the score passes but the visual still looks wrong, record the issue type
as `tooling-gap` and add a targeted region for the next pass. This is how the
skill improves instead of silently relying on taste.

### 7.4 Layout, OCR, Icon, and Module Gates

Use these gates when the source contains dense repeated modules, text that must
not be misread, or small icons whose exact silhouette matters:

- `--extract-layout` creates a coarse layout JSON and overlay from the source
  screenshot. Use it before hand-placing modules so card/media/text/icon boxes
  are based on detected evidence rather than memory.
- `--ocr` runs `ocr_text_check.py` when Tesseract is available. Treat OCR
  failures as review candidates by default because stylized low-contrast text
  can be missed. Use `--require-ocr-pass` only when the OCR output is known to
  be reliable for the screenshot.
- `--icon-region name:x,y,w,h` runs a targeted edge/mask comparison for icon
  strips. Use it for bottom navigation, order-state icons, toolbar icons, and
  any user-reported icon mismatch. The icon gate checks edge/mask difference
  and contour-count drift so a visually plausible but structurally different
  icon can still fail.
- `--module-card name:x,y,w,h` and
  `--partial-module-card name:x,y,w,h` run repeated-module invariant checks.
  Use them for rental cards, list rows, carousel cards, and any area where
  titles/prices/helpers/images should share a grid. The partial-card box should
  be the full logical card, even if only part of it is visible in the app
  screenshot.

For OCR-heavy Chinese screenshots, prefer `--ocr-lang chi_sim+eng` unless the
source is traditional Chinese or another language. If Tesseract is not
available, the OCR script records a skipped report rather than blocking the
whole restore.

### 7.5 Manifest Verification Gate

Run `verify_manifest.py` before reporting a version as ready. At minimum it
should confirm:

- The latest version has an SVG, full-size render, and comparison paths.
- The render dimensions match the source dimensions.
- `text_bounds_checked`, `source_crops_created`, and `local_render_compared`
  are true.
- If the version was pasted to Figma, `figma_node_url` and coordinates are
  recorded.

Use `--allow-remaining-issues` only when the final answer clearly says what
still needs human review.

### 7.6 Batch Test Workflow

When testing the skill on multiple screenshots:

1. Create a separate run directory for each source image.
2. Produce a first-pass SVG using the same workflow and naming pattern.
3. For each image, save at least three comparison crops:
   - global thumbnail comparison,
   - the densest text/list/card region,
   - the smallest icon/control region.
4. Mark every issue as one of:
   - `source-understood-wrong`: OCR/text/icon/region identification was wrong.
   - `layout-grid-wrong`: parent container, clipping, spacing, or baseline grid was wrong.
   - `asset-crop-wrong`: bitmap crop included extra pixels or lost important pixels.
   - `figma-render-drift`: local SVG looked acceptable but pasted Figma differed.
   - `tooling-gap`: no script/check currently catches this class of error.
5. Patch the skill only for repeated or workflow-level failures. Keep one-off
   coordinate fixes in the specific SVG version rather than overfitting the skill.
6. After 3 or more test images, report a compact scorecard: images tested,
   accepted regions, repeated failure modes, and the next skill improvement.

## External Tool Baseline

For one-click aspirations, do not insist on a fully hand-built SVG pipeline. When the user wants the best first pass:

- Try a dedicated screenshot-to-Figma tool such as Codia, image.to.design, or Banani if the user can run it in their Figma/Web account.
- Use the tool output as the editable baseline.
- Then apply this skill's QA loop: screenshot comparison, text-bound checks, icon repair, product image replacement, and version placement.
- Keep the local SVG pipeline as the fallback when external tools are unavailable, paid, blocked by login, or produce worse editable layers.

## Iteration Loop

After each paste/import:

1. Ask or inspect what looks wrong.
2. Use user screenshots as targeted diffs.
3. Crop corresponding original regions from the source PNG.
4. Fix only the mismatched layers and assets.
5. Paste a new version beside the prior version so comparison remains possible.
6. Run the screenshot calibration loop on the new Figma-rendered result.
7. If the user says a reported issue was not fixed, add that failure mode to this skill before the next major attempt.

Keep a short changelog for each version:

- v1: proof of SVG-to-Figma layer import.
- v2: replace placeholder icons and improve product asset sharpness.
- v3: fix specific controls, icon fidelity, and image aspect ratio/compression.

## Reporting

When summarizing, include:

- Which path was used: MCP, plugin, SVG Web paste, or manual.
- Whether the result is truly editable or only partially editable.
- What is still raster.
- What local files were generated.
- Figma link or draft location.
- Any hard limitations, especially source image resolution.

Never claim "perfect restoration" from a flattened bitmap. Say "high-fidelity iterative reconstruction" unless there is a true design source.
