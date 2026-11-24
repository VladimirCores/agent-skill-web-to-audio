#!/usr/bin/env python3
"""Synthesize one MP3 per page (default: en / en-US-GuyNeural).

Usage: python3 run_tts.py <workdir> [--voice VOICE] [--lang en] [--tts PATH] [--force]

VOICE may be an edge-tts ID, a gender (woman), or a lang-gender alias (ru-woman).
Reads script-<key>.txt, writes speech-<key>.txt, audio/NN-<key>-<slug>.mp3
and manifest.json. Existing MP3s are skipped unless --force.
"""
import argparse, json, pathlib, re, subprocess, sys, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import voice  # noqa: E402

TR = dict(zip(
    'абвгдеёжзийклмнопрстуфхцчшщъыьэюя',
    ['a','b','v','g','d','e','e','zh','z','i','y','k','l','m','n','o','p','r',
     's','t','u','f','kh','ts','ch','sh','shch','','y','','e','yu','ya']))


def slug(s: str) -> str:
    s = s.lower().replace('№', ' ')
    out = ''.join(TR.get(c, c) for c in s)
    return re.sub(r'[^a-z0-9]+', '-', out).strip('-')[:48].strip('-')


def normalize(text: str, lang='ru') -> str:
    t = text
    t = re.sub(r'(\d+)\s*[-\u2013]\s*(\d+)\s*%', r'\1-\2 процентов' if lang.startswith('ru') else r'\1-\2 percent', t)
    t = re.sub(r'(\d+)\s*%', r'\1 процентов' if lang.startswith('ru') else r'\1 percent', t)
    if lang.startswith('ru'):
        t = (t.replace('80/20', 'восемьдесят на двадцать')
               .replace('70/30', 'семьдесят на тридцать')
               .replace('2/3', 'две трети')
               .replace('1/2', 'один из двух'))
    t = t.replace('.Pdf', '').replace('.PDF', '')
    t = re.sub(r'[ \t]+', ' ', t)
    return re.sub(r'\n{3,}', '\n\n', t).strip() + '\n'


def duration(p: pathlib.Path) -> float:
    try:
        r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                            '-of', 'csv=p=0', str(p)], capture_output=True, text=True, timeout=60)
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('workdir')
    ap.add_argument('--voice', default=None,
                    help='edge-tts voice ID, gender (woman), or lang-gender (ru-woman)')
    ap.add_argument('--lang', default=None)
    ap.add_argument('--tts', default=str(pathlib.Path(__file__).with_name('tts_dmitry.py')))
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()

    base = pathlib.Path(args.workdir).resolve()
    audio = base / 'audio'
    audio.mkdir(exist_ok=True)
    cfg = json.loads((base / 'pages.json').read_text(encoding='utf-8')) if (base / 'pages.json').exists() else {}
    lang = args.lang or cfg.get('language') or voice.DEFAULT_LANG
    voice_id = voice.resolve_voice(args.voice or cfg.get('voice'), lang)
    print(f'lang={lang} voice={voice_id}', flush=True)
    entries = cfg.get('pages') or [{'key': p.name[7:-4]} for p in sorted(base.glob('script-*.txt'))]

    manifest = []
    for idx, entry in enumerate(entries, 1):
        key = str(entry['key'])
        src = base / f'script-{key}.txt'
        if not src.exists():
            print(f'missing {src.name}', file=sys.stderr)
            continue
        blocks_file = base / (entry.get('blocks_file') or f'page-{key}-blocks.json')
        d = json.loads(blocks_file.read_text(encoding='utf-8')) if blocks_file.exists() else {}
        title = entry.get('title') or d.get('title', key)
        speech = base / f'speech-{key}.txt'
        text = normalize(src.read_text(encoding='utf-8'), lang)
        speech.write_text(text, encoding='utf-8')
        out = audio / f'{idx:02d}-{slug(key)}-{slug(title)}.mp3'
        rec = {'n': idx, 'key': key, 'title': title, 'url': entry.get('url', d.get('url', '')),
               'script': str(src), 'speech': str(speech), 'mp3': str(out), 'chars': len(text)}
        if not args.force and out.exists() and duration(out) > 1:
            rec['duration'] = round(duration(out), 1)
            rec['status'] = 'exists'
            print(f"{idx:02d} {key} exists {rec['duration']}s", flush=True)
        else:
            t0 = time.time()
            print(f"{idx:02d} {key} synth {len(text)} chars -> {out.name}", flush=True)
            r = subprocess.run([sys.executable, args.tts, str(speech), str(out), voice_id],
                               capture_output=True, text=True)
            dur = duration(out)
            rec['duration'] = round(dur, 1)
            rec['status'] = 'ok' if dur > 5 else 'FAILED'
            rec['elapsed'] = round(time.time() - t0, 1)
            if rec['status'] != 'ok':
                rec['stderr'] = (r.stdout or '')[-800:] + (r.stderr or '')[-800:]
                print(f"   FAILED: {rec.get('stderr','')[-300:]}", flush=True)
            else:
                print(f"   ok {dur:.1f}s in {rec['elapsed']}s", flush=True)
        manifest.append(rec)
        (base / 'manifest.json').write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')

    total = sum(r.get('duration', 0) for r in manifest)
    bad = [r['key'] for r in manifest if r.get('status') == 'FAILED']
    print(f'DONE total {total/60:.1f} min, failed={bad}', flush=True)


if __name__ == '__main__':
    main()
