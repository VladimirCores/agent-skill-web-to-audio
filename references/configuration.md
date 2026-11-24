# Configuration reference

## Language and voice

Resolve the user's prompt note with `python3 scripts/voice.py "<note>"` before writing `pages.json`:

| Note | `language` | OCR `--lang` | `voice` |
|---|---|---|---|
| none / `en` / `1` / English | `en` | `eng` | `en-US-GuyNeural` |
| `en woman` / `en female` | `en` | `eng` | `en-US-JennyNeural` |
| `ru` / `0` / Russian | `ru` | `rus` | `ru-RU-DmitryNeural` |
| `ru woman` / `женским голосом` | `ru` | `rus` | `ru-RU-SvetlanaNeural` |

`0` = ru, `1` = en. An explicit note wins; without one the default is **en**. `run_tts.py` also accepts voice aliases such as `woman`, `ru-woman` or `en-man`.

## Workdir layout

```
<workdir>/                       # e.g. /tmp/opencode/web-example
├── pages.json                   # page list + language/voice/title (start from assets/pages.example.json)
├── fixes.json                   # optional OCR corrections: {"page-key": [["bad","good"]]}
├── page-<key>-blocks.json       # extracted blocks, one per URL
├── images/<key>/*.png|jpg       # downloaded full-resolution images
├── ocr/<key>/*.txt              # raw tesseract output
├── script-<key>.txt             # cleaned reading text
├── speech-<key>.txt             # normalized TTS input
├── audio/NN-<key>-<slug>.mp3    # final MP3s
└── manifest.json                # paths, titles, URLs, durations, status
```

Multiple URLs share one workdir: add one `pages` entry per URL and the scripts produce one PDF section and one MP3 per entry.

## pages.json

```json
{
  "title": "My Web Collection",
  "subtitle": "Saved pages",
  "language": "en",
  "voice": "en-US-GuyNeural",
  "pages": [
    {
      "key": "article",
      "url": "https://example.com/a",
      "title": "Article",
      "blocks_file": "page-article-blocks.json"
    }
  ]
}
```

- `key`: short slug used in all derived filenames; keep it stable and unique.
- `blocks_file`: optional; defaults to `page-<key>-blocks.json`.
- `language`: TTS/cleanup/PDF language code (`en`, `ru`, …). OCR language is passed separately via `--lang` to `scripts/ocr_images.py` (tesseract codes: `eng`, `rus`, `rus+eng`).
- `voice`: any `edge-tts` voice ID, or an alias resolved by `scripts/voice.py`. Keep the resolved default unless the user asks for another voice.
- The scripts read one top-level `language`/`voice` per workdir. For a mixed-language batch, use one workdir per language.

## fixes.json

Optional, used by `scripts/build_texts.py`. Corrections apply to the cleaned text for a given page key:

```json
{
  "deepseek-superagent": [
    ["Super-agent Please add support for this feature", ""],
    ["font row", "font row"]
  ]
}
```

Use it for repeated OCR artifacts only; after editing, rerun `build_texts.py` → `run_tts.py` → `build_pdf.py`. No re-OCR needed.

## extract.js config (`arg` to `browse.eval`)

| Key | Meaning | Default |
|---|---|---|
| `port` | receiver port | `8765` |
| `name` | page key / output filename | host + path slug |
| `lang` | language code; chooses the figcaption prefix | `en` (`ru` → "Иллюстрация. ") |
| `figcaptionPrefix` | explicit prefix for image captions | from `lang` |
| `contentSelector` | override auto-detection | auto |
| `titleSelector` | override title detection | auto |
| `titlePrefix` | text prepended to detected title | — |
| `exclude` | extra CSS selectors to remove | — |
| `includeImages` | `false` skips images | `true` |
| `maxChars` | extracted text cap | `250000` |

Name the page in `extract.js` the same as `key` in `pages.json` so the files line up.
