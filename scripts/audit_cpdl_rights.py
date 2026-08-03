#!/usr/bin/env python3
"""Audit upstream CPDL edition rights for the curated 205-work release.

The script joins the frozen PawChorale catalog to the original browser download
log, resolves each CPDL media file to its work page through the MediaWiki API,
and reads the edition-level ``{{Copy|...}}`` marker from the matching score
entry. Results are evidence for release review, not legal advice.
"""

from __future__ import annotations

import csv
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
WORKSPACE = PROJECT.parent
CATALOG = PROJECT / "docs" / "data" / "songs.json"
DOWNLOAD_LOG = Path(
    "/Users/hanyu/Desktop/sscs_direct_downloads/browser_download_click_log.html"
)
OUTPUT = PROJECT / "rights"
API = "https://www.cpdl.org/wiki/api.php"
USER_AGENT = "PawChorale-rights-audit/1.0 (https://pawchorale.github.io/)"


def normalize(value: str) -> str:
    folded = unicodedata.normalize("NFKD", urllib.parse.unquote(value)).casefold()
    return "".join(character for character in folded if character.isalnum())


def read_download_log() -> list[dict[str, str]]:
    text = DOWNLOAD_LOG.read_text(encoding="utf-8")
    match = re.search(r"const links = (\[.*?\]);", text, flags=re.DOTALL)
    if not match:
        raise RuntimeError("Could not find the links array in the browser download log")
    return json.loads(match.group(1))


def api_query(titles: list[str]) -> list[dict]:
    parameters = urllib.parse.urlencode(
        {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "prop": "revisions",
            "rvprop": "content",
            "rvslots": "main",
            "redirects": "1",
            "titles": "|".join(titles),
        }
    )
    request = urllib.request.Request(f"{API}?{parameters}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    return payload.get("query", {}).get("pages", [])


def api_file_query(titles: list[str]) -> list[dict]:
    parameters = urllib.parse.urlencode(
        {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "prop": "revisions|fileusage",
            "rvprop": "content",
            "rvslots": "main",
            "fulimit": "max",
            "redirects": "1",
            "titles": "|".join(titles),
        }
    )
    request = urllib.request.Request(f"{API}?{parameters}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    return payload.get("query", {}).get("pages", [])


def fetch_pages(titles: list[str]) -> dict[str, str]:
    results: dict[str, str] = {}
    unique = sorted(set(titles))
    for offset in range(0, len(unique), 20):
        for page in api_query(unique[offset : offset + 20]):
            revisions = page.get("revisions", [])
            content = ""
            if revisions:
                content = revisions[0].get("slots", {}).get("main", {}).get("content", "")
            results[page.get("title", "")] = content
        time.sleep(0.1)
    return results


def fetch_file_work_titles(titles: list[str]) -> dict[str, str]:
    results: dict[str, str] = {}
    unique = sorted(set(titles))
    for offset in range(0, len(unique), 20):
        for page in api_file_query(unique[offset : offset + 20]):
            filename = page.get("title", "").removeprefix("File:")
            usages = [
                item["title"]
                for item in page.get("fileusage", [])
                if item.get("ns") == 0 and not item.get("redirect")
            ]
            if usages:
                results[normalize(filename)] = usages[0]
                continue
            revisions = page.get("revisions", [])
            content = ""
            if revisions:
                content = revisions[0].get("slots", {}).get("main", {}).get("content", "")
            results[normalize(filename)] = source_work_title(content)
        time.sleep(0.1)
    return results


def source_work_title(file_content: str) -> str:
    content = file_content.strip()
    redirect = re.search(r"\[\[([^\]|]+)", content)
    if redirect and content.casefold().startswith("#redirect"):
        return redirect.group(1).strip()
    return content.splitlines()[0].strip() if content else ""


def score_entry(page_content: str, source_filename: str) -> dict[str, str]:
    target = normalize(source_filename)
    blocks = re.split(r"(?m)^\*", page_content)
    for block in blocks:
        media_files = re.findall(r"\[\[(?:Media|File):([^\]|]+)", block, flags=re.I)
        if not any(normalize(filename) == target for filename in media_files):
            continue
        def capture(pattern: str) -> str:
            match = re.search(pattern, block, flags=re.I)
            return match.group(1).strip() if match else ""

        return {
            "edition_license": capture(r"\{\{Copy\|([^}|]+)"),
            "editor": capture(r"\{\{Editor\|([^}|]+)"),
            "cpdl_number": capture(r"\{\{CPDLno\|([^}|]+)"),
            "posted_date": capture(r"\{\{PostedDate\|([^}|]+)"),
        }
    return {
        "edition_license": "",
        "editor": "",
        "cpdl_number": "",
        "posted_date": "",
    }


def review_status(license_name: str) -> str:
    key = normalize(license_name)
    if key == "cpdl":
        return "redistributable_cpdl_terms"
    if key in {"pd", "publicdomain"}:
        return "public_domain_marker"
    if key.startswith("cc") or key.startswith("creativecommons"):
        return "review_creative_commons_variant"
    if key == "personal":
        return "permission_or_terms_review_required"
    if key:
        return "license_review_required"
    return "unresolved"


def main() -> None:
    songs = json.loads(CATALOG.read_text(encoding="utf-8"))
    links = read_download_log()
    by_row = {int(link["row_id"]): link for link in links}
    by_filename: dict[str, list[dict[str, str]]] = {}
    for link in links:
        filename = Path(urllib.parse.urlparse(link["url"]).path).name
        by_filename.setdefault(normalize(filename), []).append(link)

    rows: list[dict[str, str | int]] = []
    unresolved_mapping: list[int] = []
    for song in songs:
        song_id = int(song["id"])
        original = str(song["original_folder"])
        manifest_path = WORKSPACE / "organized_mp3" / str(song_id) / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source_file = manifest.get("source_file", "")

        link: dict[str, str] | None = None
        if original.isdigit():
            link = by_row.get(int(original))
        if link is None and source_file:
            candidates = by_filename.get(normalize(source_file), [])
            if candidates and len({item["url"] for item in candidates}) == 1:
                link = candidates[0]
        if link is None:
            unresolved_mapping.append(song_id)
            source_url = ""
            source_title = ""
            row_id = ""
        else:
            source_url = link["url"]
            source_title = link["title"]
            row_id = link["row_id"]

        source_filename = Path(urllib.parse.urlparse(source_url).path).name if source_url else ""
        rows.append(
            {
                "song_id": song_id,
                "song_title": song["title"],
                "original_folder": original,
                "download_log_row": row_id,
                "manifest_source_file": source_file,
                "cpdl_source_title": source_title,
                "cpdl_media_filename": urllib.parse.unquote(source_filename),
                "cpdl_media_url": source_url,
            }
        )

    file_titles = [
        f"File:{row['cpdl_media_filename']}"
        for row in rows
        if row["cpdl_media_filename"]
    ]
    file_to_work = fetch_file_work_titles(file_titles)

    work_titles = [title for title in file_to_work.values() if title]
    work_pages = fetch_pages(work_titles)
    normalized_work_pages = {normalize(title): (title, content) for title, content in work_pages.items()}

    for row in rows:
        filename = str(row["cpdl_media_filename"])
        work_title = file_to_work.get(normalize(filename), "")
        returned_title, work_content = normalized_work_pages.get(
            normalize(work_title), (work_title, "")
        )
        edition = score_entry(work_content, filename)
        row.update(edition)
        row["cpdl_work_page"] = (
            "https://www.cpdl.org/wiki/index.php/"
            + urllib.parse.quote(returned_title.replace(" ", "_"), safe="()!,_'")
            if returned_title
            else ""
        )
        row["rights_review_status"] = review_status(edition["edition_license"])

    OUTPUT.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with (OUTPUT / "source_rights_manifest.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    license_counts = Counter(str(row["edition_license"]) or "UNRESOLVED" for row in rows)
    status_counts = Counter(str(row["rights_review_status"]) for row in rows)
    summary = {
        "work_count": len(rows),
        "mapped_source_urls": sum(bool(row["cpdl_media_url"]) for row in rows),
        "resolved_edition_licenses": sum(bool(row["edition_license"]) for row in rows),
        "unresolved_mapping_song_ids": unresolved_mapping,
        "edition_license_counts": dict(sorted(license_counts.items())),
        "rights_review_status_counts": dict(sorted(status_counts.items())),
        "method": (
            "Joined each selected work to the original CPDL media URL, resolved the "
            "media file page through the official MediaWiki API, and parsed the "
            "matching score entry's edition-level Copy marker."
        ),
        "disclaimer": "Evidence for release review; not legal advice.",
    }
    (OUTPUT / "source_rights_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
