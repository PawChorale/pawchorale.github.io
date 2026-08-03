#!/usr/bin/env python3
"""Validate the static site and frozen PawChorale release metadata."""

from __future__ import annotations

import csv
import json
import sys
from html.parser import HTMLParser
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
SITE = PROJECT / "docs"


class SiteParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.local_assets: set[str] = set()
        self.internal_fragments: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        element_id = values.get("id")
        if element_id:
            if element_id in self.ids:
                raise ValueError(f"Duplicate HTML id: {element_id}")
            self.ids.add(element_id)
        for attribute in ("href", "src"):
            value = values.get(attribute)
            if not value:
                continue
            if value.startswith("#"):
                self.internal_fragments.add(value[1:])
            elif not value.startswith(("http://", "https://", "mailto:", "data:")):
                clean = value.split("#", 1)[0].split("?", 1)[0]
                if clean:
                    self.local_assets.add(clean)


def fail(message: str) -> None:
    raise AssertionError(message)


def main() -> int:
    required = [
        SITE / "index.html",
        SITE / "styles.css",
        SITE / "script.js",
        SITE / "assets" / "og.png",
        SITE / "data" / "songs.json",
        SITE / "data" / "release-summary.json",
        SITE / "data" / "release-manifest.csv",
        SITE / ".nojekyll",
    ]
    missing = [str(path.relative_to(PROJECT)) for path in required if not path.is_file()]
    if missing:
        fail(f"Missing required files: {', '.join(missing)}")

    parser = SiteParser()
    parser.feed((SITE / "index.html").read_text(encoding="utf-8"))
    unresolved = sorted(parser.internal_fragments - parser.ids)
    if unresolved:
        fail(f"Unresolved page fragments: {', '.join(unresolved)}")
    for relative in parser.local_assets:
        if not (SITE / relative).is_file():
            fail(f"Missing local page asset: {relative}")

    songs = json.loads((SITE / "data" / "songs.json").read_text(encoding="utf-8"))
    summary = json.loads(
        (SITE / "data" / "release-summary.json").read_text(encoding="utf-8")
    )
    with (SITE / "data" / "release-manifest.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        manifest = list(csv.DictReader(handle))

    if len(songs) != 205 or len(manifest) != 205:
        fail(f"Expected 205 catalog rows, found JSON={len(songs)}, CSV={len(manifest)}")
    ids = [int(song["id"]) for song in songs]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        fail("Catalog IDs must be unique and sorted")
    if summary.get("song_count") != 205:
        fail("Release summary song_count is not 205")
    if len(summary.get("archives", [])) != 4:
        fail("Release summary must contain exactly four archives")
    if sum(item["song_count"] for item in summary["archives"]) != 205:
        fail("Archive song counts do not sum to 205")
    if summary.get("downloads_enabled") and summary.get("rights_status") != "provided":
        fail("Downloads cannot be enabled without a provided rights notice")

    size = sum(path.stat().st_size for path in SITE.rglob("*") if path.is_file())
    print("Site validation passed")
    print(f"HTML IDs: {len(parser.ids)}")
    print(f"Catalog works: {len(songs)}")
    print(f"Static site size: {size / 1024**2:.2f} MiB")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (AssertionError, ValueError) as error:
        print(f"Validation failed: {error}", file=sys.stderr)
        sys.exit(1)
