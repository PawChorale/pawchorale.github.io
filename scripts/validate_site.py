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
        SITE / "demo" / "93" / "notes.json",
        SITE / "demo" / "93" / "93_master.mp3",
        SITE / "demo" / "93" / "93_Soprano.mp3",
        SITE / "demo" / "93" / "93_Alto.mp3",
        SITE / "demo" / "93" / "93_Tenor.mp3",
        SITE / "demo" / "93" / "93_Bass.mp3",
        SITE / "demo" / "93" / "RIGHTS_NOTICE.md",
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

    if len(songs) != 200 or len(manifest) != 200:
        fail(f"Expected 200 catalog rows, found JSON={len(songs)}, CSV={len(manifest)}")
    ids = [int(song["id"]) for song in songs]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        fail("Catalog IDs must be unique and sorted")
    if summary.get("song_count") != 200:
        fail("Release summary song_count is not 200")
    if set(summary.get("review_excluded_song_ids", [])) != {114, 250, 263, 290, 297}:
        fail("Release summary does not record the five reviewed exclusions")
    if set(ids) & {114, 250, 263, 290, 297}:
        fail("Reviewed exclusion IDs are still present in the catalog")
    if len(summary.get("archives", [])) != 4:
        fail("Release summary must contain exactly four archives")
    if sum(item["song_count"] for item in summary["archives"]) != 200:
        fail("Archive song counts do not sum to 200")
    if summary.get("downloads_enabled") and summary.get("rights_status") != "provided":
        fail("Downloads cannot be enabled without a provided rights notice")

    demo = json.loads(
        (SITE / "demo" / "93" / "notes.json").read_text(encoding="utf-8")
    )
    if demo.get("song_id") != 93 or len(demo.get("tracks", [])) != 4:
        fail("Interactive demo must contain work 93 and four vocal tracks")
    if sum(track["note_count"] for track in demo["tracks"]) != 251:
        fail("Interactive demo note count is not 251")

    size = sum(path.stat().st_size for path in SITE.rglob("*") if path.is_file())
    print("Site validation passed")
    print(f"HTML IDs: {len(parser.ids)}")
    print(f"Catalog works: {len(songs)}")
    print("Interactive demo: work 93, 5 synchronized audio tracks, 251 notes")
    print(f"Static site size: {size / 1024**2:.2f} MiB")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (AssertionError, ValueError) as error:
        print(f"Validation failed: {error}", file=sys.stderr)
        sys.exit(1)
