#!/usr/bin/env python3
"""Build clean narration/reading text from extracted blocks + OCR.

Usage: python3 build_texts.py <workdir> [--lang en] [--fixes FILE]

Reads pages.json (or page-*-blocks.json) and ocr/<key>/*.txt.
Writes script-<key>.txt for each page (run_tts.py creates speech-<key>.txt).
Language controls UI junk, OCR filtering and table prefixes (en default).
"""
import argparse, difflib, json, pathlib, re, sys

COMMON_JUNK = [
    r'^(Share|Tweet|Like|Follow|Subscribe|Sign in|Log in|Cookie|Cookies)$',
]
RU_JUNK = [
    r'Play Video', r'\bЗаметки\b', r'\bСохранить\b', r'^Смотреть$',
    r'Пройти заново', r'У вас есть ещё \d+ попытки?', r'^Заполнить анкету$',
    r'^Вопрос \d+/\d+\.?$', r'^Вопрос \d+$',
    r'^\s*(Читать далее|Далее|Подробнее|Назад|К содержанию)\s*$',
]
EN_JUNK = [
    r'^\s*(Read more|Next|Previous|Back|Continue watching|Watch now)\s*$',
    r'^\s*(Skip to (content|main)|Accept (all )?cookies?)\s*$',
]


def page_list(base: pathlib.Path) -> list:
    cfg = base / 'pages.json'
    if cfg.exists():
        d = json.loads(cfg.read_text(encoding='utf-8'))
        out = []
        for p in d.get('pages', []):
            key = str(p['key'])
            out.append((key, base / (p.get('blocks_file') or f'page-{key}-blocks.json')))
        return out
    return [(p.name[5:-11], p) for p in sorted(base.glob('page-*-blocks.json'))]


def norm(s: str) -> str:
    return re.sub(r'\s+', ' ', s.replace('\u200b', '').replace('\u00a0', ' ')).strip()


def strip_ui(s: str, lang: str = 'en') -> str:
    patterns = COMMON_JUNK + (RU_JUNK if lang.lower().startswith('ru') else EN_JUNK)
    for p in patterns:
        s = re.sub(p, ' ', s, flags=re.I | re.M)
    return norm(s)


def _paragraphs(raw):
    chunks, cur = [], []
    for line in raw.splitlines():
        line = norm(line)
        if not line:
            if cur:
                chunks.append(cur)
                cur = []
            continue
        compact = re.sub(r'\s', '', line)
        if len(compact) < 3:
            continue
        letters = sum(ch.isalpha() for ch in compact)
        if letters / len(compact) < 0.62:
            continue
        if re.search(r'[=~^_|<>]{3,}', compact):
            continue
        cur.append(line)
    if cur:
        chunks.append(cur)
    blocks = []
    for chunk in chunks:
        text = ''
        for line in chunk:
            if not text:
                text = line
            elif text.endswith(('.', '!', '?', ':', ';')):
                blocks.append(text)
                text = line
            else:
                text += ' ' + line
        if not text:
            continue
        if blocks and re.match(r'^[а-яёa-z]', text):
            blocks[-1] = blocks[-1].rstrip() + ' ' + text
        else:
            blocks.append(text)
    return blocks


def _drop_parens(s: str, ru: bool = False) -> str:
    """Drop parentheticals with digits/brackets; in ru mode also non-Cyrillic ones."""
    def repl(m):
        inner = m.group(1)
        if re.search(r'[0-9{}\[\]]', inner):
            return ''
        if ru:
            letters = [c for c in inner if c.isalpha()]
            cyr = [c for c in letters if 'а' <= c.lower() <= 'я' or c.lower() == 'ё']
            if letters and len(cyr) / len(letters) < 0.6:
                return ''
        return m.group(0)
    s = re.sub(r'\(([^()]*)\)', repl, s)
    return norm(re.sub(r'\s+([.,;:!?])', r'\1', s))


def clean_ocr(raw: str, lang: str = 'en') -> str:
    ru = lang.lower().startswith('ru')
    out = []
    for b in _paragraphs(raw):
        b = _drop_parens(norm(b), ru)
        if len(b) < (45 if ru else 40):
            continue
        compact = re.sub(r'\s', '', b)
        letters = sum(ch.isalpha() for ch in compact)
        if letters / max(len(compact), 1) < 0.70:
            continue
        words = re.findall(r"[А-Яа-яЁёA-Za-z][А-Яа-яЁёA-Za-z'-]*", b)
        if len(words) < 6:
            continue
        avg = sum(len(w) for w in words) / len(words)
        if not ((3.0 <= avg <= 9.0) if ru else (2.5 <= avg <= 10.0)):
            continue
        short = sum(1 for w in words if len(w) <= 2)
        if short / len(words) > (0.35 if ru else 0.45):
            continue
        weird = sum(1 for w in words if len(w) > 2 and any(c.isupper() for c in w[1:]))
        mixed = sum(1 for w in words
                    if re.search(r'[А-Яа-яЁё]', w) and re.search(r'[A-Za-z]', w))
        if (weird + mixed) / len(words) > (0.05 if ru else 0.08):
            continue
        up = sum(1 for c in b if c.isupper())
        if up / max(letters, 1) > 0.14:
            continue
        cyr = sum(1 for c in b if 'а' <= c.lower() <= 'я' or c.lower() == 'ё')
        if ru:
            if cyr / max(letters, 1) < 0.85:
                continue
            if re.search(r'[а-яё][А-ЯЁ]', b):
                continue
        elif cyr / max(letters, 1) > 0.15:
            continue
        b = re.sub(r'^[^A-ZА-ЯЁ"«“]+', '', b)
        b = norm(re.sub(r'\s+([.,;:!?])', r'\1', b))
        if b:
            out.append(b)
    return '\n\n'.join(out)


def key(s: str) -> str:
    return re.sub(r'[^а-яa-z0-9 ]', '', s.lower().replace('ё', 'е'))


def is_dup(text: str, seen: list, threshold=0.82) -> bool:
    k = key(text)
    if len(k) < 40:
        return False
    for s in seen:
        ks = key(s)
        if not ks:
            continue
        if k in ks or ks in k:
            if min(len(k), len(ks)) / max(len(k), len(ks)) > 0.6:
                return True
        if abs(len(k) - len(ks)) < max(len(k), len(ks)) * 0.6:
            if difflib.SequenceMatcher(None, k[:300], ks[:300]).ratio() >= threshold:
                return True
    return False


def ocr_for(base, key_, b, lang):
    local = pathlib.Path(b.get('local', ''))
    f = base / 'ocr' / key_ / (local.stem + '.txt')
    if not f.exists():
        return ''
    return clean_ocr(f.read_text(encoding='utf-8', errors='replace'), lang)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('workdir')
    ap.add_argument('--lang', default=None)
    ap.add_argument('--fixes')
    args = ap.parse_args()
    base = pathlib.Path(args.workdir).resolve()

    fixes = {}
    fp = args.fixes or (base / 'fixes.json')
    if pathlib.Path(fp).exists():
        fixes = json.loads(pathlib.Path(fp).read_text(encoding='utf-8'))
    cfg = json.loads((base / 'pages.json').read_text(encoding='utf-8')) if (base / 'pages.json').exists() else {}
    lang = args.lang or cfg.get('language') or 'en'
    table_prefix = 'Таблица. ' if lang.lower().startswith('ru') else 'Table. '

    report = []
    for pkey, src in page_list(base):
        if not src.exists():
            print(f'missing {src.name}', file=sys.stderr)
            continue
        d = json.loads(src.read_text(encoding='utf-8'))
        title = norm(d.get('title', pkey))
        parts, seen = [title.rstrip('.') + '.'], [title]
        ocr_chars = page_chars = 0
        for b in d.get('blocks', []):
            t = b.get('type')
            txt = strip_ui(b.get('text', ''), lang)
            if t in ('p', 'li', 'quote'):
                if len(txt) < 12 or is_dup(txt, seen):
                    continue
                parts.append(txt)
                seen.append(txt)
                page_chars += len(txt)
            elif t == 'h':
                if len(txt) < 8 or is_dup(txt, seen):
                    continue
                parts.append(txt.rstrip('.') + '.')
                seen.append(txt)
                page_chars += len(txt)
            elif t == 'table':
                if len(txt) > 12 and not is_dup(txt, seen):
                    parts.append(table_prefix + txt.rstrip('.') + '.')
                    seen.append(txt)
                    page_chars += len(txt)
            elif t == 'code':
                continue  # code is kept in the PDF but not narrated
            elif t == 'img':
                ocr = ocr_for(base, pkey, b, lang)
                if not ocr:
                    continue
                kept = []
                for para in ocr.split('\n\n'):
                    para = norm(para)
                    if len(para) < 45 or is_dup(para, seen):
                        continue
                    kept.append(para)
                    seen.append(para)
                if kept:
                    parts.append('\n\n'.join(kept))
                    ocr_chars += sum(len(k) for k in kept)
        script = '\n\n'.join(parts)
        for bad, good in fixes.get(pkey, []):
            script = script.replace(bad, good)
        script = re.sub(r'\n{3,}', '\n\n', script).strip() + '\n'
        (base / f'script-{pkey}.txt').write_text(script, encoding='utf-8')
        report.append((pkey, title, page_chars, ocr_chars, len(script),
                       round(len(script) / 14 / 60, 1)))

    print(f'{"key":18} {"page":>5} {"ocr":>5} {"total":>6} {"min":>5}  title')
    for pkey, title, pc, oc, total, mins in report:
        print(f'{pkey:18} {pc:5} {oc:5} {total:6} {mins:5}  {title[:42]}')
    print('sum minutes ~', round(sum(r[5] for r in report), 1))


if __name__ == '__main__':
    main()
