---
name: web-to-audio
description: 'Turn a pasted web URL into an MP3 narration and, optionally, a print-ready PDF with full-resolution images and OCR of infographics. Language and voice are taken from the user prompt (ru/en, man/woman; en is the default). Use when the user pastes a URL and asks to make audio from an article or page, read a webpage aloud, save/archive a page with images, or turn a link into a PDF — including LMS lessons and social posts. Main content is auto-detected; accept CSS selectors, language/voice, and include/exclude notes.'
license: MIT
compatibility: 'Requires Python 3, Chromium/Chrome, edge-tts, ffmpeg/ffprobe, tesseract with traineddata, network access, and an OpenCode browse-compatible browser tool.'
metadata:
  version: "1.2"
  updated: "2026-11-24"
  author: "Vladimir Cores"
---

# Web URL → MP3 (+ PDF)

Extract one or more pasted pages into a clean spoken narration and a print-ready archive. No site-specific hardcoding; overrides come from the user's notes.

Skill root: `~/.config/opencode/skills/web-to-audio`. Paths below are relative to it — run commands from there.

## Defaults

- URL with no other notes → produce **both** MP3 and PDF.
- Language: **en** (default), voice: **en-US-GuyNeural**. Russian notes switch to `ru` / `ru-RU-DmitryNeural`.
- Auto-detect the main article; strip nav, ads, comments, cookie banners; keep full-resolution images.
- One workdir per batch. Each entry in `pages.json` yields one PDF section and one MP3.
- Read [references/configuration.md](references/configuration.md) when creating `pages.json`, `fixes.json`, or setting extractor options.

## Language and voice from the prompt

Resolve the user's note **before** writing `pages.json` — don't ask when the note already answers it:

```bash
python3 scripts/voice.py "in ru man"      # language ru, voice ru-RU-DmitryNeural
python3 scripts/voice.py "in en woman"    # language en, voice en-US-JennyNeural
python3 scripts/voice.py                  # default: en / en-US-GuyNeural
```

| Prompt note | language | OCR | voice |
|---|---|---|---|
| no language note / `en` / `1` / English | `en` | `eng` | `en-US-GuyNeural` |
| `en woman` / `in en female` | `en` | `eng` | `en-US-JennyNeural` |
| `ru` / `0` / Russian / по-русски | `ru` | `rus` | `ru-RU-DmitryNeural` |
| `ru woman` / `по-русски женским голосом` | `ru` | `rus` | `ru-RU-SvetlanaNeural` |

- Shortcuts: `0` = ru, `1` = en. Gender: `man`/`male`/`мужской`, `woman`/`female`/`женский`. Missing or unknown → en default.
- An explicit prompt always wins. The scripts use one language/voice per workdir; for mixed-language batches, create one workdir per language.
- Write the resolved `language` and `voice` into `pages.json` and pass `--lang`/`--voice` to the scripts. `run_tts.py` also accepts aliases (`ru-woman`, `woman`, `en-man`) through the same resolver.

## Inputs

- **Required:** the URL.
- **Optional notes:** CSS overrides (`contentSelector`, `titleSelector`), `exclude` selectors, `includeImages: false`, language/voice ("in ru man", "en woman"), output name, audio-only/PDF-only, OCR corrections.
- Login / 2FA / captcha / payment confirmation → call `tools.browse.handoff` and wait. Never solve it yourself.

## Scripts

- `scripts/voice.py` — resolve language/OCR/voice from a prompt note (0 = ru, 1 = en, default en).
- `scripts/recv.py` — loopback receiver for browser-extracted JSON.
- `scripts/extract.js` — browser-side extractor; pass its whole content as a `browse.eval` expression.
- `scripts/ocr_images.py` — download images and run tesseract.
- `scripts/build_texts.py` — OCR cleanup and narration scripts (language-aware).
- `scripts/run_tts.py` — per-page MP3s + `manifest.json`.
- `scripts/tts_dmitry.py` — chunked `edge-tts` engine used by `run_tts.py`.
- `scripts/build_pdf.py` — self-contained HTML → Chromium PDF with localized cover/TOC.

## Workflow

Progress:
- [ ] 1. Resolve language/voice; workdir + `pages.json`
- [ ] 2. Receiver + extraction, with payload validation
- [ ] 3. OCR images
- [ ] 4. Clean texts, review `script-<key>.txt`
- [ ] 5. Generate and verify MP3s
- [ ] 6. Generate and verify PDF
- [ ] 7. Cleanup

### 1. Language, workdir and config

```bash
python3 scripts/voice.py "in ru man"   # use the user's note; omit it for the en default
WORK=/tmp/opencode/web-example
mkdir -p "$WORK"
cp assets/pages.example.json "$WORK/pages.json"
# Edit: title, resolved language/voice, and one entry per URL (key/url/title).
```

### 2. Extract each URL

```bash
python3 scripts/recv.py 8765 "$WORK"    # background; keep running until extraction is done
```

Use `tools.browse.navigate` with `allowedOrigins` containing the exact host; wait until the article text and images are rendered. Then `tools.browse.eval` with `expression` = the full contents of `scripts/extract.js`, `arg` = config, `tab` = the tab id:

```js
{ port: 8765, name: "<key>", lang: "<en|ru>", contentSelector: "<override-if-needed>" }
```

**Gate:** continue only if `saved: true`, `blocks > 0`, and the first text block is the article, not a nav menu. If `saved: false` / `Failed to fetch`, or the wrong region was picked, follow [references/extraction.md](references/extraction.md).

### 3. OCR the images

```bash
python3 scripts/ocr_images.py "$WORK" --lang eng --tessdata /tmp/opencode/tessdata --jobs 8
```

Use the resolved OCR language (`eng`, `rus`, `rus+eng`, …). `--force` only when redoing OCR.

### 4. Clean the texts

```bash
python3 scripts/build_texts.py "$WORK" --lang en
```

Review `script-<key>.txt`. If infographic OCR is noisy, add corrections to `fixes.json` and rerun this step onward — no need to re-OCR. Rules and flags: [references/text-and-audio.md](references/text-and-audio.md).

### 5. Generate audio

```bash
python3 scripts/run_tts.py "$WORK" --lang en --voice en-US-GuyNeural
```

Verify: every entry in `manifest.json` has `status: "ok"` (or `"exists"` on a rerun), `ffprobe` reports a nonzero duration, and no `audio/*_chunks` directories remain. Never substitute gTTS. Details: [references/text-and-audio.md](references/text-and-audio.md).

### 6. Generate the PDF

```bash
python3 scripts/build_pdf.py "$WORK" \
  --out "$WORK/collection.pdf" --title "Web Collection" --subtitle "Saved pages"
```

`--lang` defaults to the `language` in `pages.json` (en if absent) and localizes cover, contents and date. Verify: `pdfinfo` reports pages, `pdftotext` contains the headings, `pdfimages -list` shows the expected images. Details: [references/pdf.md](references/pdf.md).

### 7. Cleanup

Stop the receiver, close tabs you opened, confirm chunk directories are gone, keep final artifacts plus `pages.json`/`manifest.json` unless asked otherwise.

## Gotchas

- `browse.eval` calls the expression as `(element, arg)` when `arg` is supplied; `extract.js` handles both that and the no-arg form. Always pass config via `arg`.
- Site CSP (notably X/Twitter) can block the loopback POST: `Failed to fetch`, `saved: false`. Use the neutral-tab fallback in [references/extraction.md](references/extraction.md).
- X articles: `contentSelector: "[data-testid=\"twitterArticleRichTextView\"]"`; replace `name=900x900` with `name=orig` in the blocks JSON before OCR/PDF.
- Auto-detection can select a wrapper `div` containing several articles; narrow with `contentSelector` or `exclude`.
- Lazy-loaded pages: wait for text and images before extraction. `og:title` is often marketing copy; prefer `h1` or `titleSelector`.
- `edge-tts` throttling / `NoAudioReceived` is normal; retries and splitting are built in. Do not fall back to gTTS.
- Images requiring session cookies are omitted from the PDF; mention this if the user expected them.
