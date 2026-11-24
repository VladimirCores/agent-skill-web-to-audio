# Text cleanup and audio

Language and voice come from the prompt via `scripts/voice.py` (see [configuration.md](configuration.md)). Defaults: **en** / `eng` OCR / `en-US-GuyNeural`. For Russian use `--lang ru` with `rus` OCR and `ru-RU-DmitryNeural` (or the `woman` aliases for `en-US-JennyNeural` / `ru-RU-SvetlanaNeural`).

## OCR (`scripts/ocr_images.py`)

```bash
python3 scripts/ocr_images.py "$WORK" --lang eng --tessdata /tmp/opencode/tessdata --jobs 8
# --force to redo; --key page-key to OCR a single page
```

- Downloads images from `page-*-blocks.json`, saves under `images/<key>/`, and writes raw text to `ocr/<key>/*.txt`.
- Handles absolute URLs, URLs relative to the page, and `data:` images.
- Use tesseract language codes matching the resolved language: `eng`, `rus`, `eng+rus`, etc. `--lang` defaults to `eng`.

## Text cleanup (`scripts/build_texts.py`)

```bash
python3 scripts/build_texts.py "$WORK" --lang en
```

- Drops UI junk (language-specific) and very short/garbled blocks, filters stylized OCR, merges broken paragraphs, removes foreign/garbled parentheticals, deduplicates repeated text, and applies `fixes.json` for the page key.
- Language controls the OCR heuristics, UI-junk patterns and table prefix ("Table." vs "Таблица."). `--lang` falls back to `pages.json` → `en`.
- Code blocks are kept in the PDF but excluded from narration.
- Produces `script-<key>.txt` (readable); `speech-<key>.txt` is created later by `run_tts.py`.
- **Validate:** read `script-<key>.txt` before TTS, especially for pages that are mostly video or highly stylized diagrams. Correct repeated OCR mistakes in `fixes.json` and rerun this step onward.

## Audio generation (`scripts/run_tts.py`)

```bash
python3 scripts/run_tts.py "$WORK" --lang en --voice en-US-GuyNeural
# --voice woman / ru-woman / en-man aliases are accepted; --force to regenerate MP3s
```

- Voice selection: CLI `--voice` → `pages.json` `voice` → default for the resolved language. Printed at startup as `lang=… voice=…`.
- Never fall back to gTTS.
- Normalization covers percentages and Russian ratio/verbalization cases (including `80/20`, `70/30`, `2/3`, `1/2`) and removes `.Pdf` artifacts.
- `tts_dmitry.py` chunks text (~850 chars), retries `edge-tts` with backoff, splits stubborn chunks, concatenates with ffmpeg, and deletes chunk directories on success. Throttling and `NoAudioReceived` are expected and retried.

## Validation gate

- `python3 -m json.tool "$WORK/manifest.json"`: every entry has `status == "ok"` (or `"exists"` when an MP3 was reused on a rerun), with `mp3`, `duration`, `chars`.
- `ffprobe -v error -show_entries format=duration -of csv=p=0 "$WORK"/audio/*.mp3` reports nonzero durations.
- No `audio/*_chunks` directories remain.
- For multi-page batches, spot-check the start of at least the first and last MP3 by filename/title match.

Typical scale from real runs: ~5 min per 5k chars to synthesize (network/throttle dependent); a 49k-char English article produced ~49 min of audio.
