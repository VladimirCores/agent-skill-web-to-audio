#!/usr/bin/env python3
"""Robust chunked edge-tts synthesis with retries, backoff and recursive splitting.

Usage: tts_dmitry.py <src.txt> <out.mp3> [voice] [--maxlen N] [--keep-chunks]

Default voice: en-US-GuyNeural. Chunk files are deleted on success
(pass --keep-chunks to retain them for debugging).
"""
import argparse, pathlib, re, shutil, subprocess, sys, time


def split_text(text, maxlen=850):
    parts = re.split(r'(?<=[.!?…])\s+', text)
    chunks, cur = [], ''
    for s in parts:
        s = s.strip()
        if not s:
            continue
        if len(s) > maxlen:
            for piece in re.split(r'(?<=,)\s+', s):
                if cur and len(cur) + len(piece) + 1 > maxlen:
                    chunks.append(cur.strip())
                    cur = piece
                else:
                    cur = (cur + ' ' + piece if cur else piece)
            continue
        if cur and len(cur) + len(s) + 1 > maxlen:
            chunks.append(cur.strip())
            cur = s
        else:
            cur = (cur + ' ' + s if cur else s)
    if cur.strip():
        chunks.append(cur.strip())
    return chunks


def probe(p):
    try:
        r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                            '-of', 'csv=p=0', str(p)], capture_output=True, text=True, timeout=60)
        return float(r.stdout.strip())
    except Exception:
        return 0.0


class Synth:
    def __init__(self, voice, work, keep_chunks):
        self.voice, self.work, self.keep_chunks = voice, work, keep_chunks

    def one(self, text, mp3, label, depth=0):
        if mp3.exists() and mp3.stat().st_size > 1000:
            return True
        txt = mp3.with_suffix('.txt')
        txt.write_text(text, encoding='utf-8')
        delays = [2, 3, 5, 8, 12, 18, 25, 30, 30, 30, 30, 30]
        for attempt, delay in enumerate(delays, 1):
            try:
                subprocess.run(['edge-tts', '--voice', self.voice, '--file', str(txt),
                                '--write-media', str(mp3)], capture_output=True,
                               text=True, timeout=150)
            except subprocess.TimeoutExpired:
                print(f'  {label} attempt {attempt}: timeout', flush=True)
                time.sleep(delay)
                continue
            ok = mp3.exists() and mp3.stat().st_size > 1000
            if ok:
                d = probe(mp3)
                if d and d > 0.4:
                    print(f'  {label} ok after {attempt} ({d:.1f}s)', flush=True)
                    return True
            print(f'  {label} attempt {attempt}: fail, sleep {delay}s', flush=True)
            time.sleep(delay)
        if depth < 3 and len(text) > 120:
            mid = len(text) // 2
            cut = text.rfind(' ', 0, mid)
            if cut < 40:
                cut = mid
            a, b = text[:cut].strip(), text[cut:].strip()
            print(f'  {label} SPLIT into {len(a)} + {len(b)}', flush=True)
            pa = self.work / (mp3.stem + '_a.mp3')
            pb = self.work / (mp3.stem + '_b.mp3')
            if self.one(a, pa, label + 'a', depth + 1) and self.one(b, pb, label + 'b', depth + 1):
                lst = self.work / (mp3.stem + '_halves.txt')
                lst.write_text(f"file '{pa.resolve()}'\nfile '{pb.resolve()}'\n", encoding='utf-8')
                subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0',
                                '-i', str(lst), '-c', 'copy', str(mp3)], check=True)
                return True
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('out')
    ap.add_argument('voice', nargs='?', default='en-US-GuyNeural')
    ap.add_argument('--maxlen', type=int, default=850)
    ap.add_argument('--keep-chunks', action='store_true')
    args = ap.parse_args()

    src, out = pathlib.Path(args.src), pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    work = pathlib.Path(str(out.with_suffix('')) + '_chunks')
    work.mkdir(parents=True, exist_ok=True)

    text = src.read_text(encoding='utf-8')
    chunks = split_text(text, args.maxlen)
    print(f'{len(chunks)} chunks, {len(text)} chars -> {work}', flush=True)
    synth = Synth(args.voice, work, args.keep_chunks)
    mp3s = []
    for i, chunk in enumerate(chunks):
        mp3 = work / f'chunk_{i:02d}.mp3'
        print(f'[{i:02d}] {len(chunk)} chars', flush=True)
        if not synth.one(chunk, mp3, f'[{i:02d}]'):
            print(f'FAILED chunk {i}', flush=True)
            sys.exit(1)
        mp3s.append(mp3)
        time.sleep(0.4)

    lst = work / 'list.txt'
    lst.write_text(''.join(f"file '{p.resolve()}'\n" for p in mp3s), encoding='utf-8')
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0',
                    '-i', str(lst), '-c', 'copy', str(out)], check=True)
    dur = probe(out)
    print(f'WROTE {out} {out.stat().st_size}B {dur:.1f}s', flush=True)
    if not args.keep_chunks:
        shutil.rmtree(work, ignore_errors=True)
        print(f'cleaned {work}', flush=True)


if __name__ == '__main__':
    main()
