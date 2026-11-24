#!/usr/bin/env python3
"""Download page images and OCR them.

Usage: python3 ocr_images.py <workdir> [--lang eng] [--tessdata DIR] [--jobs N] [--force]

Reads <workdir>/pages.json (or page-*-blocks.json files), fills each image
block's `local` path, and writes <workdir>/ocr/<key>/<stem>.txt.
"""
import argparse, base64, hashlib, json, os, pathlib, subprocess, sys, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'}


def pages(base: pathlib.Path) -> list:
    cfg = base / 'pages.json'
    if cfg.exists():
        d = json.loads(cfg.read_text(encoding='utf-8'))
        out = []
        for p in d.get('pages', []):
            key = str(p['key'])
            f = base / (p.get('blocks_file') or f'page-{key}-blocks.json')
            out.append((key, f, p.get('url', '')))
        return out
    return [(p.name[5:-11], p, '') for p in sorted(base.glob('page-*-blocks.json'))]


def fetch(url: str, dest: pathlib.Path) -> bool:
    if dest.exists() and dest.stat().st_size > 500:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=90) as r:
            body = r.read()
        if len(body) < 500:
            return False
        dest.write_bytes(body)
        return True
    except Exception as exc:
        print(f'  download failed {url[:90]}: {exc}', file=sys.stderr)
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('workdir')
    ap.add_argument('--lang', default='eng', help='tesseract language(s), e.g. eng, rus, rus+eng')
    ap.add_argument('--tessdata', default='/tmp/opencode/tessdata')
    ap.add_argument('--tesseract', default='tesseract')
    ap.add_argument('--jobs', type=int, default=8)
    ap.add_argument('--key', help='only process this page key')
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()

    base = pathlib.Path(args.workdir).resolve()
    tasks = []
    env = None
    if pathlib.Path(args.tessdata).exists():
        env = dict(os.environ, TESSDATA_PREFIX=args.tessdata)

    entries = [e for e in pages(base) if not args.key or e[0] == args.key]
    for key, p, page_url in entries:
        if not p.exists():
            print(f'missing {p.name}', file=sys.stderr)
            continue
        d = json.loads(p.read_text(encoding='utf-8'))
        changed = False
        for i, b in enumerate(d.get('blocks', [])):
            if b.get('type') != 'img':
                continue
            src = b.get('src', '')
            if not src:
                continue
            ext = '.jpg' if src.lower().split('?')[0].endswith(('.jpg', '.jpeg')) else '.png'
            h = hashlib.md5(src.encode()).hexdigest()[:8]
            dest = base / 'images' / key / f'{i:02d}_{h}{ext}'
            if src.lower().startswith('data:'):
                try:
                    payload = src.split(',', 1)[1]
                    body = base64.b64decode(payload)
                    if len(body) < 500:
                        continue
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(body)
                except Exception as exc:
                    print(f'  bad data URI: {exc}', file=sys.stderr)
                    continue
            elif not fetch(urllib.parse.urljoin(page_url or d.get('url', ''), src), dest):
                continue
            b['local'] = str(dest)
            changed = True
            ocr = base / 'ocr' / key / (dest.stem + '.txt')
            if args.force or not ocr.exists():
                tasks.append((dest, ocr))
        if changed:
            p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f'{len(tasks)} images to OCR (lang={args.lang})', flush=True)

    def run(item):
        src, dest = item
        dest.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([args.tesseract, str(src), 'stdout', '-l', args.lang, '--psm', '3'],
                           capture_output=True, env=env, timeout=240)
        dest.write_bytes(r.stdout)
        return r.returncode

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        codes = list(pool.map(run, tasks))
    print(f'OCR done: {len(codes)} images, failures={sum(c != 0 for c in codes)}', flush=True)


if __name__ == '__main__':
    main()
