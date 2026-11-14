"""Fetch IIIF regions politely, cached on disk. Limited scope (POC).
python3 fetch.py SERIES first last region size outdir
region: full | pct:x,y,w,h ; size: e.g. 1600, (width)"""
import sys
import time
import urllib.request
from pathlib import Path

REF = "https://sok.riksarkivet.se/"
UA = "synthetic-genealogy/0.1 (research sketch; few pages)"


def get(series, n, region="full", size="full", outdir=Path("img")):
    key = f"{series}_{n:05d}"
    out = outdir / f"{key}_{region.replace(':', '').replace(',', '-')}_{size.replace(',', '')}.jpg"
    if out.exists():
        return out, False
    url = f"https://lbiiif.riksarkivet.se/v2/arkis!{key}/{region}/{size}/0/default.jpg"
    req = urllib.request.Request(url, headers={"Referer": REF, "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        out.write_bytes(r.read())
    return out, True


if __name__ == "__main__":
    s, a, b, region, size, od = sys.argv[1:7]
    od = Path(od); od.mkdir(parents=True, exist_ok=True)
    for n in range(int(a), int(b) + 1):
        try:
            p, fresh = get(s, n, region, size, od)
            print(n, p.name, p.stat().st_size)
            if fresh:
                time.sleep(1.0)
        except Exception as e:
            print(n, "ERR", e)
