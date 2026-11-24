#!/usr/bin/env python3
"""Resolve language and TTS voice from a user phrase (single source of truth).

Usage:
    python3 voice.py "in ru man"     # ru-RU-DmitryNeural
    python3 voice.py "in en woman"   # en-US-JennyNeural
    python3 voice.py "1 woman"       # 1 = en -> en-US-JennyNeural
    python3 voice.py                 # default: en / en-US-GuyNeural

Shortcuts: 0 = ru, 1 = en. Gender words: man/male/mужской, woman/female/женский.
"""
from __future__ import annotations

import argparse
import json
import re

DEFAULT_LANG = "en"

# OCR and neural voice IDs per language. Man is the default gender for both.
LANGUAGES = {
    "en": {
        "ocr": "eng",
        "voice_man": "en-US-GuyNeural",
        "voice_woman": "en-US-JennyNeural",
    },
    "ru": {
        "ocr": "rus",
        "voice_man": "ru-RU-DmitryNeural",
        "voice_woman": "ru-RU-SvetlanaNeural",
    },
}

LANG_ALIASES = {
    "en": "en", "eng": "en", "english": "en",
    "английский": "en", "английском": "en", "английская": "en", "английскую": "en",
    "ru": "ru", "rus": "ru", "russian": "ru",
    "русский": "ru", "русском": "ru", "русская": "ru", "русскую": "ru", "по-русски": "ru",
    "0": "ru", "1": "en",
}

GENDER_ALIASES = {
    "man": "man", "male": "man", "m": "man",
    "мужской": "man", "мужским": "man", "мужчина": "man",
    "woman": "woman", "female": "woman", "f": "woman",
    "женский": "woman", "женским": "woman", "женщина": "woman",
}

TOKEN_RE = re.compile(r"[a-zа-яё]+(?:-[a-zа-яё]+)?|[01]", re.I)
VOICE_IDS = {v["voice_man"].lower(): v["voice_man"] for v in LANGUAGES.values()}
VOICE_IDS.update({v["voice_woman"].lower(): v["voice_woman"] for v in LANGUAGES.values()})


def voice_for(lang: str = DEFAULT_LANG, gender: str | None = None) -> str:
    """Return the canonical edge-tts voice ID for a language and gender."""
    info = LANGUAGES.get(lang, LANGUAGES[DEFAULT_LANG])
    return info["voice_woman"] if gender == "woman" else info["voice_man"]


def resolve_voice(value: str | None, lang: str = DEFAULT_LANG) -> str:
    """Accept a voice ID, a gender, or a 'lang-gender' alias; default per language."""
    if not value:
        return voice_for(lang)
    v = value.strip()
    low = v.lower()
    if low in VOICE_IDS:
        return VOICE_IDS[low]
    if low in GENDER_ALIASES:
        return voice_for(lang, GENDER_ALIASES[low])
    m = re.fullmatch(r"(en|ru)[-_ ]?(man|woman)", low)
    if m:
        return voice_for(*m.groups())
    return v  # allow any custom edge-tts voice ID


def resolve(phrase: str = "") -> dict:
    """Parse a user note like 'in ru man' into language, OCR code and voice."""
    lang, gender, explicit = DEFAULT_LANG, None, False
    for tok in TOKEN_RE.findall((phrase or "").lower()):
        if tok in LANG_ALIASES:
            lang = LANG_ALIASES[tok]
            explicit = True
        elif tok in GENDER_ALIASES:
            gender = GENDER_ALIASES[tok]

    canonical_lang = lang if lang in LANGUAGES else DEFAULT_LANG
    return {
        "input": phrase or "",
        "language": canonical_lang,
        "tts_lang": canonical_lang,
        "ocr_lang": LANGUAGES[canonical_lang]["ocr"],
        "gender": gender or "man",
        "voice": voice_for(canonical_lang, gender),
        "explicit_language": explicit,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("phrase", nargs="*", help='e.g. "in ru man" or "en woman"')
    args = ap.parse_args()
    print(json.dumps(resolve(" ".join(args.phrase)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
