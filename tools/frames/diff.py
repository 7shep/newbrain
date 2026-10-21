"""Diff consecutive screencast frames: flag stalls (gaps between new frames while things move) and jumps,
and save a marked copy (red box round what changed) of each flagged frame. Usage: python3 diff.py <rundir>"""
import glob, json, os, sys
from PIL import Image, ImageChops, ImageDraw
run = sys.argv[1]
for d in sorted(glob.glob(f"{run}/*-*/")):
    t = json.load(open(d + "times.json")); ts = t["frames"]
    fs = sorted(glob.glob(d + "[0-9]*.jpg"))
    os.makedirs(d + "marked", exist_ok=True)
    flags = []
    prev = None
    for i, f in enumerate(fs):
        im = Image.open(f).convert("L")
        if prev is not None:
            diff = ImageChops.difference(im, prev).point(lambda v: 255 if v > 24 else 0)
            box = diff.getbbox()
            gap = (ts[i] - ts[i - 1]) * 1000
            changed = sum(diff.histogram()[255:]) / (im.width * im.height)
            if gap > 40:
                flags.append((i, round(gap), "stall", box, round(changed, 3)))
                m = Image.open(f).convert("RGB"); dr = ImageDraw.Draw(m)
                if box: dr.rectangle(box, outline=(255, 0, 0), width=3)
                m.save(f"{d}marked/{i:04d}-gap{round(gap)}ms.jpg")
        prev = im
    gaps = [(b - a) * 1000 for a, b in zip(ts, ts[1:])]
    print(os.path.basename(d.rstrip('/')), f"{len(fs)} frames, stalls>40ms: {len(flags)}", [(i, g, round(c, 2)) for i, g, _, _, c in flags][:8])
