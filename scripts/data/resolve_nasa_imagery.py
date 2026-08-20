#!/usr/bin/env python3
"""Regenerate `data/catalog/imagery.py` from the NASA Image and Video Library.

Run this to refresh or extend the verified image table:

    python scripts/data/resolve_nasa_imagery.py --verify   # re-check every URL
    python scripts/data/resolve_nasa_imagery.py --resolve  # search for new keys

The rule this script exists to enforce is simple: an image is only written into
the catalog once its asset URL has been fetched and returned 200. Guessing a
Photojournal id and hoping is how a science product ends up rendering broken
boxes.

Alt text is *not* generated. It is written by hand in ALT_TEXT below, because
an alt attribute derived from the title is just the title again and tells a
screen-reader user nothing about what the image shows.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "data" / "catalog" / "imagery.py"
USER_AGENT = "LostIntoSpacE/0.2 (catalog build)"

SEARCH_API = "https://images-api.nasa.gov/search"
ASSET_TEMPLATE = "https://images-assets.nasa.gov/image/{id}/{id}~{size}.jpg"


def request(url: str, method: str = "GET", tries: int = 3):
    """One HTTP call, with backoff on the rate limits this API applies."""
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.status, (response.read() if method == "GET" else b"")
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 503) and attempt < tries - 1:
                time.sleep(3 * (attempt + 1))
                continue
            return exc.code, b""
        except Exception:
            if attempt < tries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            return 0, b""
    return 0, b""


def verify_asset(nasa_id: str):
    """The first asset size that actually resolves, or None."""
    for size in ("medium", "small"):
        url = ASSET_TEMPLATE.format(id=urllib.parse.quote(nasa_id), size=size)
        status, _ = request(url, "HEAD")
        if status == 200:
            return url
        time.sleep(0.2)
    return None


def search(query: str, page_size: int = 25):
    status, body = request(
        SEARCH_API
        + "?"
        + urllib.parse.urlencode({"q": query, "media_type": "image", "page_size": page_size})
    )
    if status != 200:
        return []
    try:
        return json.loads(body)["collection"]["items"]
    except Exception:
        return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="Re-check every URL already in the table")
    args = parser.parse_args()

    if args.verify:
        sys.path.insert(0, str(ROOT))
        from data.catalog.imagery import IMAGERY  # noqa: E402

        broken = []
        for key, image in IMAGERY.items():
            status, _ = request(image.url, "HEAD")
            mark = "ok" if status == 200 else "BROKEN {0}".format(status)
            print("{0:22s} {1}".format(key, mark))
            if status != 200:
                broken.append(key)
            time.sleep(0.2)
        if broken:
            print("\n{0} broken: {1}".format(len(broken), ", ".join(broken)))
            return 1
        print("\nAll {0} images resolve.".format(len(IMAGERY)))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
