#!/usr/bin/env python3
"""Build a print-ready PDF from extracted web pages + full-resolution images.

Usage: python3 build_pdf.py <workdir> --out FILE.pdf [--title TITLE] [--subtitle SUB]
                            [--lang en|ru] [--browser /path/to/chromium]

Page order, titles and URLs come from <workdir>/pages.json (or page-*-blocks.json).
Language defaults to pages.json -> en and localizes the cover and table of contents.
"""
import argparse, datetime, html, json, os, pathlib, re, shutil, subprocess, sys

CSS = r"""
@page { size: A4; margin: 17mm 16mm 18mm 16mm; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body { font-family: 'Noto Serif','DejaVu Serif',serif; font-size: 10.6pt; line-height: 1.55;
       color: #16181d; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
h1,h2,h3,h4,h5,h6,.sans { font-family:'Noto Sans','DejaVu Sans',sans-serif; }
.cover { height: 255mm; display:flex; flex-direction:column; justify-content:space-between; }
.cover .top { padding-top:18mm; }
.cover .kicker { font-size:9pt; letter-spacing:.18em; text-transform:uppercase;
                 color:#6b7280; margin-bottom:10mm; font-family:'Noto Sans',sans-serif; }
.cover h1 { font-size:30pt; line-height:1.15; margin:0 0 6mm; color:#13314f; font-weight:700; }
.cover .sub { font-size:13pt; color:#374151; margin:0 0 3mm; }
.cover .rule { height:3px; width:34mm; background:#2f6f8f; margin:8mm 0; }
.cover .toc { margin-top:10mm; }
.cover .toc .t { font-size:9pt; letter-spacing:.12em; text-transform:uppercase;
                 color:#6b7280; margin-bottom:4mm; font-family:'Noto Sans',sans-serif; }
.cover .toc ol { margin:0; padding-left:7mm; }
.cover .toc li { font-size:12pt; line-height:1.8; word-break:break-word; }
.cover .toc .url { display:block; color:#8a94a6; font-size:8.6pt;
                   font-family:'Noto Sans',sans-serif; }
.cover .foot { font-size:8.6pt; color:#6b7280; border-top:1px solid #d8dee7;
               padding-top:4mm; font-family:'Noto Sans',sans-serif; }
.doc { break-before:page; }
.doc-head { border-bottom:2px solid #2f6f8f; padding-bottom:3.5mm; margin-bottom:6mm; }
.doc-head .kicker { font-size:8.6pt; letter-spacing:.16em; text-transform:uppercase;
                    color:#2f6f8f; font-weight:700; font-family:'Noto Sans',sans-serif; }
.doc-head h1 { font-size:20pt; line-height:1.2; margin:2mm 0 1mm; color:#13314f; }
.doc-head .url { font-size:8.2pt; color:#6b7280; word-break:break-all;
                 font-family:'Noto Sans',sans-serif; }
h2 { font-size:14pt; color:#13314f; margin:7mm 0 2.5mm; break-after:avoid; }
h3 { font-size:12pt; color:#1f2937; margin:5mm 0 1.5mm; break-after:avoid; }
h4,h5,h6 { font-size:10.8pt; color:#374151; margin:4mm 0 1.2mm; break-after:avoid; }
p { margin:0 0 3.2mm; text-align:left; orphans:3; widows:3; }
blockquote { break-inside:avoid; margin:4mm 0; padding:2mm 5mm; border-left:4px solid #9cb3c4;
             background:#f5f8fa; color:#374151; font-style:italic; }
ul,ol { margin:0 0 3.5mm; padding-left:7mm; }
li { margin:0 0 1.2mm; }
pre { break-inside:avoid; white-space:pre-wrap; word-break:break-word; background:#f3f4f6;
      border:1px solid #dfe3e8; border-radius:3px; padding:3mm 4mm; font-size:9pt; }
table { width:100%; border-collapse:collapse; margin:4mm 0 5mm; font-size:9.4pt; }
th,td { border:1px solid #d3dbe6; padding:1.6mm 2mm; text-align:left; vertical-align:top; }
th { background:#eef4f8; font-family:'Noto Sans',sans-serif; }
figure { margin:4mm 0 5mm; break-inside:avoid; text-align:center; }
figure img { max-width:100%; max-height:218mm; width:auto; height:auto;
             display:block; margin:0 auto; border-radius:3px; }
figure.wide img { max-height:150mm; }
figcaption { font-size:8.8pt; color:#6b7280; margin-top:1.5mm; }
.note { font-size:9.6pt; color:#4b5563; }
.tip { break-inside:avoid; background:#fff8e8; border:1px solid #f0dfb4;
       border-left:4px solid #c99a2e; border-radius:4px; padding:3.5mm 5mm;
       margin:5mm 0; font-size:10.2pt; }
"""

MONTHS = {
    'en': ['January', 'February', 'March', 'April', 'May', 'June', 'July',
           'August', 'September', 'October', 'November', 'December'],
    'ru': ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля',
           'августа', 'сентября', 'октября', 'ноября', 'декабря'],
}

I18N = {
    'en': {
        'kicker': 'Web Collection',
        'toc': 'Contents',
        'source': 'Source',
        'footer': 'Sources: web pages; text and images saved at original resolution.',
        'material': 'material',
        'materials': 'materials',
    },
    'ru': {
        'kicker': 'Сборник материалов · Web',
        'toc': 'Содержание',
        'source': 'Источник',
        'footer': 'Источники: страницы в сети; текст и изображения сохранены в исходном разрешении.',
        'material': 'материал',
        'material_few': 'материала',
        'materials': 'материалов',
    },
}


def locale(lang):
    """Return (language key, localized strings) for a language code."""
    key = 'ru' if (lang or '').lower().startswith('ru') else 'en'
    return key, I18N[key]


def material_label(count, lang_key):
    """Pluralize the cover's material count in English or Russian."""
    if lang_key == 'en':
        return I18N['en']['material' if count == 1 else 'materials']
    if count % 10 == 1 and count % 100 != 11:
        return I18N['ru']['material']
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return I18N['ru']['material_few']
    return I18N['ru']['materials']


def find_browser(candidate=None):
    """Use the requested binary, or the first Chromium/Chrome found on PATH."""
    if candidate:
        return candidate
    for name in ('chromium-browser', 'chromium', 'google-chrome', 'google-chrome-stable'):
        found = shutil.which(name)
        if found:
            return found
    return 'chromium-browser'


def esc(t):
    return html.escape(t or '', quote=False)


def sanitize(h):
    h = re.sub(r'(?is)<(script|style|iframe|object|embed)\b.*?</\1\s*>', '', h)
    h = re.sub(r'(?i)\son\w+\s*=\s*"[^"]*"', '', h)
    h = re.sub(r"(?i)\son\w+\s*=\s*'[^']*'", '', h)
    h = re.sub(r'(?i)(href|src)\s*=\s*["\']?\s*javascript:[^"\'\s>]*', '', h)
    return h


def skip_image(b):
    src = b.get('src') or ''
    if re.search(r'boomstream|poster|placeholder|1x1|pixel|tracking', src, re.I):
        return True
    w, h = b.get('w', 0) or 0, b.get('h', 0) or 0
    return 0 < w < 50 and 0 < h < 50


def render_doc(base, d, idx, strings):
    title = d.get('title') or d.get('key') or f'Page {idx}'
    url = d.get('url', '')
    parts = ['<section class="doc">', '<div class="doc-head">',
             f'<div class="kicker">{esc(strings["source"])} {idx} · {esc(d.get("host", ""))}</div>',
             f'<h1>{esc(title)}</h1>']
    if url:
        parts.append(f'<div class="url">{esc(url)}</div>')
    if d.get('meta', {}).get('description'):
        parts.append(f'<p class="note">{esc(d["meta"]["description"])}</p>')
    parts.append('</div>')

    for b in d.get('blocks', []):
        t = b.get('type')
        if t == 'img':
            src = b.get('local', '')
            if not src or skip_image(b) or not pathlib.Path(src).exists():
                continue
            rel = pathlib.Path(os.path.relpath(pathlib.Path(src).resolve(), base)).as_posix()
            cls = 'wide' if (b.get('h', 0) or 0) < 300 else ''
            parts.append(f'<figure class="{cls}"><img src="{esc(rel)}" alt="{esc(b.get("alt",""))}">')
            if b.get('alt'):
                parts.append(f'<figcaption>{esc(b["alt"])}</figcaption>')
            parts.append('</figure>')
        elif t == 'h':
            lvl = min(max(int(b.get('level', 2) or 2), 2), 4)
            parts.append(f'<h{lvl}>{esc(b.get("text",""))}</h{lvl}>')
        elif t == 'p':
            text = (b.get('text') or '').strip()
            if not text:
                continue
            if text.lower().startswith(('рабочая тетрадь', 'workbook')) and '(pdf)' in text.lower():
                parts.append(f'<div class="tip">📄 {esc(text)}</div>')
            else:
                parts.append(f'<p>{sanitize(b.get("html") or esc(text))}</p>')
        elif t == 'li':
            order = 'ordered' if b.get('ordered') else 'unordered'
            parts.append(f'<li class="{order}">{esc(b.get("text",""))}</li>')
        elif t == 'quote':
            parts.append(f'<blockquote>{esc(b.get("text",""))}</blockquote>')
        elif t == 'code':
            parts.append(f'<pre>{esc(b.get("text",""))}</pre>')
        elif t == 'table':
            parts.append(sanitize(b.get('html') or f'<p>{esc(b.get("text",""))}</p>'))
    parts.append('</section>')
    # wrap consecutive <li> elements into lists
    out, i = [], 0
    while i < len(parts):
        if parts[i].startswith('<li>'):
            items, ordered = [], None
            while i < len(parts) and parts[i].startswith('<li>'):
                m = re.match(r'<li class="(ordered|unordered)">(.*)</li>$', parts[i])
                if m:
                    is_ord = m.group(1) == 'ordered'
                    if ordered is not None and is_ord != ordered:
                        break
                    ordered = is_ord
                    items.append(m.group(2))
                else:
                    items.append(parts[i][4:-5])
                i += 1
            tag = 'ol' if ordered else 'ul'
            out.append(f'<{tag}>' + ''.join(f'<li>{x}</li>' for x in items) + f'</{tag}>')
        else:
            out.append(parts[i])
            i += 1
    return ''.join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('workdir')
    ap.add_argument('--out', required=True)
    ap.add_argument('--title')
    ap.add_argument('--subtitle')
    ap.add_argument('--lang', default=None, help='language code (en default); localizes the cover')
    ap.add_argument('--browser', default=None, help='Chromium/Chrome binary (auto-detected by default)')
    args = ap.parse_args()

    base = pathlib.Path(args.workdir).resolve()
    out = pathlib.Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    cfg_path = base / 'pages.json'
    cfg = json.loads(cfg_path.read_text(encoding='utf-8')) if cfg_path.exists() else {}
    lang = args.lang or cfg.get('language') or 'en'
    lang_key, strings = locale(lang)
    title = args.title or cfg.get('title') or cfg.get('book_title') or strings['kicker']
    subtitle = args.subtitle or cfg.get('subtitle', '')
    entries = cfg.get('pages') or [{'key': p.name[5:-11]} for p in sorted(base.glob('page-*-blocks.json'))]

    docs = []
    for entry in entries:
        key = str(entry['key'])
        f = base / (entry.get('blocks_file') or f'page-{key}-blocks.json')
        if f.exists():
            d = json.loads(f.read_text(encoding='utf-8'))
            d.setdefault('key', key)
            d.setdefault('title', entry.get('title', key))
            d.setdefault('url', entry.get('url', d.get('url', '')))
            docs.append(d)
        else:
            print(f'missing {f.name}', file=sys.stderr)

    today = datetime.date.today()
    month = MONTHS[lang_key][today.month - 1]
    date = (f'{today.day} {month} {today.year} г.' if lang_key == 'ru'
            else f'{month} {today.day}, {today.year}')
    cover = f"""
<section class="cover">
  <div class="top">
    <div class="kicker">{esc(strings['kicker'])}</div>
    <h1>{esc(title)}</h1>
    <div class="sub">{esc(subtitle)}</div>
    <div class="rule"></div>
    <div class="toc">
      <div class="t">{esc(strings['toc'])}</div>
      <ol>{''.join(f'<li>{esc(d.get("title", d["key"]))}<span class="url">{esc(d.get("url",""))}</span></li>' for d in docs)}</ol>
    </div>
  </div>
  <div class="foot">
    {esc(strings['footer'])}<br>
    {esc(date)} · {len(docs)} {esc(material_label(len(docs), lang_key))}
  </div>
</section>
"""
    body = ''.join(render_doc(base, d, i + 1, strings) for i, d in enumerate(docs))
    doc = f"""<!DOCTYPE html><html lang="{esc(lang)}"><head><meta charset="utf-8">
<title>{esc(title)}</title><style>{CSS}</style></head><body>{cover}{body}</body></html>"""
    hp = out.with_suffix('.html')
    hp.write_text(doc, encoding='utf-8')
    print('HTML written', hp, len(doc), 'bytes', flush=True)
    r = subprocess.run([find_browser(args.browser), '--headless', '--no-sandbox', '--disable-gpu',
                        f'--print-to-pdf={out}', '--print-to-pdf-no-header',
                        '--no-pdf-header-footer', f'file://{hp}'],
                       capture_output=True, text=True, timeout=600)
    print('browser rc', r.returncode, flush=True)
    print((r.stderr or '')[-500:], flush=True)
    print('PDF:', out, out.stat().st_size if out.exists() else 'MISSING', flush=True)


if __name__ == '__main__':
    main()
