#!/usr/bin/env python3
"""Build PawChorale release metadata and optional GitHub Release archives.

The curated subset is reconstructed from the frozen alignment reports and the
reviewed 200-work release folder:

1. Start with works that have a work-level (``part == All``) alignment row.
2. Exclude every work listed in ``alignment_outliers.csv``.
3. Exclude the five post-hoc review IDs recorded in
   ``config/release_exclusions.csv``.
4. Keep only folders that still exist in ``organized_mp3_200``.

Archive creation intentionally requires an explicit rights notice. This prevents
the audio from being packaged for public distribution without release terms.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


RELEASE_FILES = {".mp3", ".mid", ".midi", ".csv", ".json"}
PART_NAMES = ("soprano", "alto", "tenor", "bass")


@dataclass(frozen=True)
class Song:
    song_id: int
    title: str
    original_folder: str
    folder: Path
    files: tuple[Path, ...]
    total_bytes: int
    master_file: str | None
    stem_count: int
    midi_count: int


def parse_args() -> argparse.Namespace:
    project_dir = Path(__file__).resolve().parents[1]
    workspace = project_dir.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=workspace)
    parser.add_argument("--project-dir", type=Path, default=project_dir)
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        help="Release dataset folder. Defaults to <workspace>/organized_mp3_200.",
    )
    parser.add_argument(
        "--review-exclusions",
        type=Path,
        default=project_dir / "config" / "release_exclusions.csv",
        help="Additional reviewed work-level exclusions for the public release.",
    )
    parser.add_argument("--version", default="v1.0.0")
    parser.add_argument("--shards", type=int, default=4)
    parser.add_argument(
        "--build-archives",
        action="store_true",
        help="Create ZIP archives in release/. Requires --rights-file.",
    )
    parser.add_argument(
        "--rights-file",
        type=Path,
        help="License/rights notice included in every public archive.",
    )
    parser.add_argument(
        "--personal-permissions-file",
        type=Path,
        help="Documented permission covering the four Personal CPDL editions.",
    )
    parser.add_argument(
        "--release-published",
        action="store_true",
        help="Enable archive links in the generated website metadata.",
    )
    return parser.parse_args()


def normalized_id(value: str) -> int:
    return int(str(value).strip())


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def choose_report(workspace: Path, filename: str) -> Path:
    candidates = (
        workspace / "reports" / "table2" / filename,
        workspace / "reports" / "alignment_visualizations" / filename,
        workspace / "alignment_results" / filename,
        workspace / filename,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    searched = "\n  - ".join(str(path) for path in candidates)
    raise FileNotFoundError(f"Could not find {filename}. Searched:\n  - {searched}")


def curated_ids(
    workspace: Path, organized: Path, review_exclusions: Path
) -> list[int]:
    per_work = choose_report(workspace, "alignment_per_work.csv")
    outliers = choose_report(workspace, "alignment_outliers.csv")

    analyzable: set[int] = set()
    for row in read_csv_rows(per_work):
        if row.get("part", "").strip().lower() == "all":
            key = row.get("song_id") or row.get("id") or ""
            analyzable.add(normalized_id(key))

    excluded: set[int] = set()
    for row in read_csv_rows(outliers):
        key = row.get("song_id") or row.get("id") or ""
        if key.strip():
            excluded.add(normalized_id(key))

    reviewed: set[int] = set()
    if review_exclusions.is_file():
        for row in read_csv_rows(review_exclusions):
            key = row.get("song_id") or row.get("id") or ""
            if key.strip():
                reviewed.add(normalized_id(key))

    active = {
        int(path.name)
        for path in organized.iterdir()
        if path.is_dir() and path.name.isdigit()
    }
    selected = sorted((analyzable - excluded - reviewed) & active)
    if len(selected) != 200:
        raise RuntimeError(
            f"Expected the frozen 200-song subset, but reconstructed {len(selected)}. "
            "Do not publish until the selection reports are reconciled."
        )
    return selected


def load_song_names(workspace: Path) -> dict[int, dict[str, str]]:
    path = workspace / "song_names.csv"
    names: dict[int, dict[str, str]] = {}
    for row in read_csv_rows(path):
        song_id = normalized_id(row["new_id"])
        names[song_id] = {
            "title": row["song_name"].strip(),
            "original_folder": row.get("original_folder", "").strip(),
        }
    return names


def release_files(folder: Path) -> tuple[Path, ...]:
    return tuple(
        sorted(
            (
                path
                for path in folder.rglob("*")
                if path.is_file() and path.suffix.lower() in RELEASE_FILES
            ),
            key=lambda path: path.relative_to(folder).as_posix().lower(),
        )
    )


def identify_master(files: Iterable[Path]) -> str | None:
    mp3s = [path for path in files if path.suffix.lower() == ".mp3"]
    named = [path for path in mp3s if "master" in path.stem.lower()]
    if named:
        return named[0].name
    part_files = [
        path
        for path in mp3s
        if any(part in path.stem.lower() for part in PART_NAMES)
    ]
    leftovers = [path for path in mp3s if path not in part_files]
    return leftovers[0].name if leftovers else None


def load_songs(
    workspace: Path, organized: Path, selected: list[int]
) -> list[Song]:
    names = load_song_names(workspace)
    songs: list[Song] = []
    for song_id in selected:
        folder = organized / str(song_id)
        files = release_files(folder)
        if song_id not in names:
            raise KeyError(f"Song {song_id} is missing from song_names.csv")
        mp3s = [path for path in files if path.suffix.lower() == ".mp3"]
        midis = [path for path in files if path.suffix.lower() in {".mid", ".midi"}]
        master = identify_master(files)
        songs.append(
            Song(
                song_id=song_id,
                title=names[song_id]["title"],
                original_folder=names[song_id]["original_folder"],
                folder=folder,
                files=files,
                total_bytes=sum(path.stat().st_size for path in files),
                master_file=master,
                stem_count=max(0, len(mp3s) - (1 if master else 0)),
                midi_count=len(midis),
            )
        )
    return songs


def contiguous_shards(songs: list[Song], shard_count: int) -> list[list[Song]]:
    if shard_count < 1 or shard_count > len(songs):
        raise ValueError("--shards must be between 1 and the number of songs")
    total = sum(song.total_bytes for song in songs)
    groups: list[list[Song]] = [[]]
    cumulative = 0
    next_cut = total / shard_count
    for index, song in enumerate(songs):
        remaining_songs = len(songs) - index
        remaining_groups = shard_count - len(groups)
        if (
            len(groups) < shard_count
            and groups[-1]
            and cumulative >= next_cut
            and remaining_songs > remaining_groups
        ):
            groups.append([])
            next_cut = total * len(groups) / shard_count
        groups[-1].append(song)
        cumulative += song.total_bytes
    while len(groups) < shard_count:
        groups.append([groups[-1].pop()])
    return groups


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def asset_name(version: str, number: int, group: list[Song]) -> str:
    clean_version = version.lstrip("v")
    return (
        f"PawChorale-{clean_version}-part-{number:02d}-"
        f"songs-{group[0].song_id:03d}-{group[-1].song_id:03d}.zip"
    )


def metadata_rows(
    groups: list[list[Song]], version: str
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    song_rows: list[dict[str, object]] = []
    archive_rows: list[dict[str, object]] = []
    for number, group in enumerate(groups, start=1):
        name = asset_name(version, number, group)
        archive_rows.append(
            {
                "part": number,
                "asset": name,
                "first_song_id": group[0].song_id,
                "last_song_id": group[-1].song_id,
                "song_count": len(group),
                "uncompressed_bytes": sum(song.total_bytes for song in group),
                "download_url": (
                    "https://github.com/PawChorale/pawchorale.github.io/"
                    f"releases/download/{version}/{name}"
                ),
            }
        )
        for song in group:
            song_rows.append(
                {
                    "id": song.song_id,
                    "title": song.title,
                    "original_folder": song.original_folder,
                    "archive_part": number,
                    "master_file": song.master_file or "",
                    "stem_count": song.stem_count,
                    "midi_count": song.midi_count,
                    "file_count": len(song.files),
                    "bytes": song.total_bytes,
                }
            )
    return song_rows, archive_rows


def build_archives(
    project_dir: Path,
    groups: list[list[Song]],
    version: str,
    rights_file: Path,
    manifest_path: Path,
    source_rights_manifest: Path,
    personal_permissions_file: Path,
) -> list[Path]:
    if not rights_file.is_file():
        raise FileNotFoundError(f"Rights notice does not exist: {rights_file}")
    output_dir = project_dir / "release"
    output_dir.mkdir(parents=True, exist_ok=True)
    root_name = f"PawChorale-{version.lstrip('v')}"
    created: list[Path] = []

    readme = project_dir / "release" / "DATASET_README.md"
    readme.write_text(
        "# PawChorale\n\n"
        "This archive is one part of the PawChorale curated release. "
        "Folders use the public song IDs recorded in release-manifest.csv.\n\n"
        "Each available work contains a master mixture, isolated vocal parts, "
        "MIDI labels, and source manifests. Voicing is variable; a work is not "
        "required to contain all four SATB parts.\n",
        encoding="utf-8",
    )

    for number, group in enumerate(groups, start=1):
        archive = output_dir / asset_name(version, number, group)
        temporary = archive.with_suffix(".zip.partial")
        if temporary.exists():
            temporary.unlink()
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as handle:
            handle.write(readme, f"{root_name}/DATASET_README.md")
            handle.write(rights_file, f"{root_name}/RIGHTS_NOTICE.md")
            handle.write(manifest_path, f"{root_name}/release-manifest.csv")
            handle.write(
                source_rights_manifest,
                f"{root_name}/source-rights-manifest.csv",
            )
            handle.write(
                personal_permissions_file,
                f"{root_name}/PERSONAL_EDITION_PERMISSIONS.md",
            )
            for song in group:
                for source in song.files:
                    relative = source.relative_to(song.folder)
                    target = Path(root_name) / "songs" / str(song.song_id) / relative
                    handle.write(source, target.as_posix())
        os.replace(temporary, archive)
        if archive.stat().st_size >= 2 * 1024**3:
            raise RuntimeError(
                f"{archive.name} is at least 2 GiB and cannot be uploaded as a "
                "GitHub Release asset. Increase --shards."
            )
        created.append(archive)
    readme.unlink(missing_ok=True)
    return created


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    args = parse_args()
    workspace = args.workspace.resolve()
    project_dir = args.project_dir.resolve()
    organized = (
        args.dataset_dir.resolve()
        if args.dataset_dir
        else workspace / "organized_mp3_200"
    )
    selected = curated_ids(workspace, organized, args.review_exclusions.resolve())
    songs = load_songs(workspace, organized, selected)
    groups = contiguous_shards(songs, args.shards)
    song_rows, archive_rows = metadata_rows(groups, args.version)

    site_data = project_dir / "docs" / "data"
    manifest_path = site_data / "release-manifest.csv"
    fields = [
        "id",
        "title",
        "original_folder",
        "archive_part",
        "master_file",
        "stem_count",
        "midi_count",
        "file_count",
        "bytes",
    ]
    write_csv(manifest_path, song_rows, fields)
    write_json(site_data / "songs.json", song_rows)

    created: list[Path] = []
    if args.build_archives:
        if args.rights_file is None:
            raise SystemExit(
                "Refusing to build public archives without --rights-file. "
                "Choose and review the dataset release terms first."
            )
        if (
            args.personal_permissions_file is None
            or not args.personal_permissions_file.is_file()
        ):
            raise SystemExit(
                "Refusing to build the 200-work public archives without "
                "--personal-permissions-file. CPDL marks source editions for "
                "IDs 169, 183, 190, and 270 as Personal. Obtain permission or "
                "build a separately defined release that excludes them."
            )
        source_rights_manifest = project_dir / "rights" / "source_rights_manifest.csv"
        if not source_rights_manifest.is_file():
            raise SystemExit(
                "Run scripts/audit_cpdl_rights.py before building archives."
            )
        created = build_archives(
            project_dir,
            groups,
            args.version,
            args.rights_file.resolve(),
            manifest_path,
            source_rights_manifest,
            args.personal_permissions_file.resolve(),
        )

    checksums: dict[str, str] = {}
    if created:
        checksums = {path.name: sha256(path) for path in created}
        sums_path = project_dir / "release" / "SHA256SUMS.txt"
        sums_path.write_text(
            "".join(f"{digest}  {name}\n" for name, digest in checksums.items()),
            encoding="utf-8",
        )
        shutil.copy2(manifest_path, project_dir / "release" / manifest_path.name)

    permissions_ready = bool(
        args.personal_permissions_file and args.personal_permissions_file.is_file()
    )
    rights_ready = bool(args.rights_file and permissions_ready)
    if args.release_published and not rights_ready:
        raise SystemExit(
            "Refusing to enable public download links without both the release "
            "rights notice and documented Personal-edition permissions."
        )

    summary = {
        "release": args.version,
        "downloads_enabled": bool(args.release_published),
        "rights_status": "provided" if rights_ready else "pending",
        "song_count": len(songs),
        "review_excluded_song_ids": [114, 250, 263, 290, 297],
        "total_files": sum(len(song.files) for song in songs),
        "total_bytes": sum(song.total_bytes for song in songs),
        "master_hours": 6.473846695277778,
        "stem_hours": 25.8051192630556,
        "midi_notes": 107570,
        "alignment_scope": "available isolated vocal parts",
        "alignment": {
            "evaluated_notes": 106411,
            "matched_notes_percent": 75.0,
            "onset_within_100ms_percent": 90.05,
            "median_onset_error_ms": 19.998550415039062,
            "median_offset_error_ms": 45.00007629394531,
        },
        "archives": archive_rows,
        "checksums": checksums,
    }
    write_json(site_data / "release-summary.json", summary)

    print(f"Curated songs: {len(songs)}")
    print(f"Release files: {summary['total_files']}")
    print(f"Uncompressed size: {summary['total_bytes'] / 1024**3:.2f} GiB")
    for archive in archive_rows:
        print(
            f"Part {archive['part']}: {archive['song_count']} songs, "
            f"IDs {archive['first_song_id']}-{archive['last_song_id']}, "
            f"{archive['uncompressed_bytes'] / 1024**3:.2f} GiB"
        )
    if created:
        print(f"Created {len(created)} archives in {project_dir / 'release'}")
    else:
        print("Metadata only; no archives created.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
