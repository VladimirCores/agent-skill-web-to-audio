# PDF generation (`scripts/build_pdf.py`)

```bash
python3 scripts/build_pdf.py "$WORK" \
  --out "$WORK/collection.pdf" \
  --title "Web Collection" --subtitle "Saved pages"
```

- Input: `pages.json` plus the per-page `page-<key>-blocks.json` files.
- Output: a self-contained intermediate HTML next to the PDF and the final PDF rendered by headless Chromium. The browser binary is auto-detected (`chromium-browser`, `chromium`, `google-chrome`, `google-chrome-stable`); override it with `--browser /path/to/chrome`.
- `--lang` defaults to `language` in `pages.json` (en if absent). It localizes the cover kicker, "Contents" heading, source labels, footer and date (`en`: "November 23, 2026"; `ru`: "23 ноября 2026 г.").
- Cover page lists the table of contents and source URLs. Each page starts on a new page. Renders headings, paragraphs, ordered/unordered lists, quotes, code, tables, highlighted notes/figcaptions, and images.
- Images are embedded at full resolution when a local downloaded copy exists; very small (<50×50) and poster/tracking images are skipped. Session-cookie-only images without a local file are omitted.
- Page order follows `pages.json`.

## Validation

```bash
pdfinfo "$WORK/collection.pdf" | grep -E 'Pages|File size'
pdftotext "$WORK/collection.pdf" - | head -40
pdfimages -list "$WORK/collection.pdf" | head
```

Check that page count matches expectations, headings and key text appear, and the image count matches extracted content.

## Reruns

Rebuilding the PDF is cheap: rerun after fixing `fixes.json`/text, changing titles/subtitles, changing `--lang`, or swapping in higher-resolution images (e.g. X/Twitter `name=orig`). No re-extraction or re-OCR is required unless the source blocks/images changed.
