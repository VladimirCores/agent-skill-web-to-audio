# web-to-audio

[![skills.sh](https://skills.sh/b/VladimirCores/agent-skill-web-to-audio)](https://skills.sh/VladimirCores/agent-skill-web-to-audio)

An [agent skill](https://skills.sh/) that turns a pasted web URL into a clean MP3 narration and, by default, a print-ready PDF archive of the same page. It auto-detects the main article, removes navigation and ads, downloads full-resolution images, and OCRs infographics so they can be narrated too. It works with Claude Code, OpenCode, Codex, Cursor and other agents that read `SKILL.md`.

## Install

```bash
npx skills add VladimirCores/agent-skill-web-to-audio
```

Or copy this folder into `~/.config/opencode/skills/web-to-audio` (or your agent's equivalent skills directory). Requires Node.js 22.20+ for the `npx skills` CLI.

## Requirements

- Python 3.10+ and a Chromium/Chrome binary for PDF rendering (auto-detected, or set `--browser`)
- `edge-tts`, `ffmpeg` / `ffprobe`
- `tesseract` with traineddata (e.g. `eng.traineddata`, `rus.traineddata`); pass its directory with `--tessdata`
- Network access, and an OpenCode `browse`-compatible browser tool for page extraction
- No API keys, accounts or credentials are used by the skill itself

## Usage

Paste a URL with optional notes, for example:

```text
https://example.com/article — in ru man, audio only
https://example.com/article — in en woman
```

Language and voice are parsed from the note. `en` / `1` selects English (default, `en-US-GuyNeural` or `en-US-JennyNeural`); `ru` / `0` selects Russian (`ru-RU-DmitryNeural` or `ru-RU-SvetlanaNeural`). `man`/`woman`, `male`/`female` and their Russian equivalents select the voice gender. Resolve a note yourself with:

```bash
python3 scripts/voice.py "in ru man"
```

You can also add CSS overrides (`contentSelector`, `titleSelector`, `exclude`), set `includeImages: false`, or supply OCR corrections in `fixes.json`. See [SKILL.md](SKILL.md) for the full workflow and [references/](references/) for configuration details.

## Output

One work directory per batch, containing `script-<key>.txt` / `speech-<key>.txt`, `audio/*.mp3`, `manifest.json`, and `collection.pdf` with a cover page, table of contents and source URLs. Files are written under `/tmp/opencode/` by default.

## Security and trust

Everything runs locally. Page data is received by a loopback-only HTTP server on `127.0.0.1:8765`; images and narration are fetched from the source page and Microsoft's `edge-tts` service. The extractor sanitizes inline HTML before PDF rendering. Review `scripts/` before installing, and never place credentials in a work directory. Report issues at https://github.com/VladimirCores/agent-skill-web-to-audio/issues.

## License

MIT — see [LICENSE](LICENSE).
