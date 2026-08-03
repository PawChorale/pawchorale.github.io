#!/usr/bin/env python3
"""Build the lightweight catalog and piano-roll payloads for the web demo.

Audio is not copied into the website.  Instead, the generated ZIP index lets
the browser retrieve only the selected files from the public Zenodo archive.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import struct
import zipfile
from collections import defaultdict
from pathlib import Path

import pretty_midi
import pretty_midi.pretty_midi as pretty_midi_core
import soundfile as sf


PARTS = ("Soprano", "Alto", "Tenor", "Bass")
PART_ALIASES = {
    "Soprano": ("Soprano", "Sopran", "Superius", "Canto", "Cantus", "Air"),
    "Alto": ("Alto", "Alt", "Altus", "Medius", "Contralto"),
    "Tenor": ("Tenor", "Tenore"),
    "Bass": ("Bass", "Basso", "Bassus"),
}
COLORS = {
    "Soprano": "#7b2635",
    "Alto": "#dd6a53",
    "Tenor": "#d4a13e",
    "Bass": "#5d8a72",
}

# A few valid long-form scores exceed pretty_midi's conservative corruption
# guard while still decoding to sensible work-length timelines.
pretty_midi_core.MAX_TICK = 100_000_000


def compact_dump(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def natural_key(path: Path) -> list[object]:
    return [int(piece) if piece.isdigit() else piece.lower() for piece in re.split(r"(\d+)", path.name)]


def part_from_filename(filename: str) -> str | None:
    stem = Path(filename).stem
    for part in PARTS:
        for alias in PART_ALIASES[part]:
            if re.search(rf"(?:^|[_\-\s]){alias}(?=$|[_\-\s\d])", stem, re.IGNORECASE):
                return part
    return None


def split_title(full_title: str) -> tuple[str, str]:
    match = re.match(r"^(.*?)\s+\(([^()]*)\)\s*$", full_title)
    if not match:
        return full_title, ""
    return match.group(1).strip(), match.group(2).strip()


def load_csv_by_key(path: Path, key: str) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return {row[key].strip(): row for row in csv.DictReader(handle) if row.get(key, "").strip()}


def read_notes(midi_paths: list[Path]) -> list[list[float | int]]:
    notes: list[list[float | int]] = []
    for midi_path in midi_paths:
        midi = pretty_midi.PrettyMIDI(str(midi_path))
        for instrument in midi.instruments:
            if instrument.is_drum:
                continue
            for note in instrument.notes:
                if note.end <= note.start:
                    continue
                notes.append([int(note.pitch), round(float(note.start), 5), round(float(note.end), 5)])
    notes.sort(key=lambda note: (note[1], note[0], note[2]))
    return notes


def build_tracks(song_dir: Path) -> list[dict[str, object]]:
    grouped_audio: dict[str, list[Path]] = defaultdict(list)
    grouped_midi: dict[str, list[Path]] = defaultdict(list)

    for path in sorted(song_dir.glob("*.mp3"), key=natural_key):
        part = part_from_filename(path.name)
        if part:
            grouped_audio[part].append(path)
    for path in sorted([*song_dir.glob("*.mid"), *song_dir.glob("*.midi")], key=natural_key):
        part = part_from_filename(path.name)
        if part:
            grouped_midi[part].append(path)

    tracks: list[dict[str, object]] = []
    song_id = song_dir.name
    for part in PARTS:
        audio_paths = grouped_audio[part]
        midi_paths = grouped_midi[part]
        count = max(len(audio_paths), len(midi_paths), 1 if audio_paths or midi_paths else 0)
        if count == 0:
            continue

        # A single recording may legitimately have multiple MIDI voices of the
        # same choral part; merge those voices into its one piano-roll lane.
        if len(audio_paths) <= 1:
            pairings = [(audio_paths[0] if audio_paths else None, midi_paths)]
        else:
            pairings = []
            for index, audio_path in enumerate(audio_paths):
                paired = [midi_paths[index]] if index < len(midi_paths) else []
                pairings.append((audio_path, paired))
            for midi_path in midi_paths[len(audio_paths) :]:
                pairings.append((None, [midi_path]))

        multiple = len(pairings) > 1
        for index, (audio_path, paired_midi) in enumerate(pairings, start=1):
            notes = read_notes(paired_midi)
            label = f"{part} {index}" if multiple else part
            tracks.append(
                {
                    "label": label,
                    "part": part,
                    "color": COLORS[part],
                    "audio_file": audio_path.name if audio_path else None,
                    "audio_path": f"songs/{song_id}/{audio_path.name}" if audio_path else None,
                    "midi_files": [path.name for path in paired_midi],
                    "midi_paths": [f"songs/{song_id}/{path.name}" for path in paired_midi],
                    "notes": notes,
                    "note_count": len(notes),
                    "pitch_min": min((note[0] for note in notes), default=None),
                    "pitch_max": max((note[0] for note in notes), default=None),
                }
            )
    return tracks


def alignment_for_song(rows: list[dict[str, str]]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for row in rows:
        label = row.get("part", "").strip()
        if not label:
            continue
        try:
            result[label] = {
                "matched_percent": round(float(row["corrected_matched_note_rate_percent"]), 2),
                "onset_50ms_percent": round(float(row["corrected_onset_within_50ms_percent_of_matched"]), 2),
                "median_onset_error_ms": round(float(row["corrected_median_absolute_onset_error_ms"]), 2),
            }
        except (KeyError, TypeError, ValueError):
            continue
    return result


def zip_entry_index(archive: Path) -> dict[str, list[int]]:
    entries: dict[str, list[int]] = {}
    with zipfile.ZipFile(archive) as bundle, archive.open("rb") as raw:
        names = [info.filename for info in bundle.infolist() if not info.is_dir()]
        root = "PawChorale-1.0.0/" if any(name.startswith("PawChorale-1.0.0/") for name in names) else ""
        for info in bundle.infolist():
            if info.is_dir():
                continue
            raw.seek(info.header_offset)
            header = raw.read(30)
            if len(header) != 30 or header[:4] != b"PK\x03\x04":
                raise RuntimeError(f"Invalid local ZIP header for {info.filename}")
            name_length, extra_length = struct.unpack_from("<HH", header, 26)
            data_offset = info.header_offset + 30 + name_length + extra_length
            relative_name = info.filename[len(root) :] if root and info.filename.startswith(root) else info.filename
            entries[relative_name] = [
                data_offset,
                info.compress_size,
                info.file_size,
                info.compress_type,
                info.CRC,
            ]
    return entries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--rights", type=Path, required=True)
    parser.add_argument("--alignment", type=Path, required=True)
    args = parser.parse_args()

    songs_path = args.site / "docs/data/songs.json"
    songs = {str(row["id"]): row for row in json.loads(songs_path.read_text(encoding="utf-8"))}
    rights = load_csv_by_key(args.rights, "song_id")

    alignment_rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    if args.alignment.exists():
        with args.alignment.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                alignment_rows[row.get("song_id", "").strip()].append(row)

    notes_dir = args.site / "docs/demo/notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    for stale in notes_dir.glob("*.json"):
        stale.unlink()

    catalog: list[dict[str, object]] = []
    song_dirs = sorted((path for path in args.dataset.iterdir() if path.is_dir() and path.name.isdigit()), key=lambda p: int(p.name))
    for song_dir in song_dirs:
        song_id = song_dir.name
        song_row = songs.get(song_id, {})
        full_title = str(song_row.get("title", f"Work {song_id}"))
        title, composer = split_title(full_title)
        master_candidates = sorted(song_dir.glob("*_master.mp3"), key=natural_key)
        if not master_candidates:
            raise RuntimeError(f"No master MP3 in {song_dir}")
        master = master_candidates[0]
        audio_info = sf.info(str(master))
        tracks = build_tracks(song_dir)
        all_notes = sum(int(track["note_count"]) for track in tracks)
        voicing = "".join(track["part"][0] for track in tracks)
        alignment = alignment_for_song(alignment_rows.get(song_id, []))
        rights_row = rights.get(song_id, {})

        mixture_midi = next(iter(sorted(song_dir.glob("choral_mixture.mid*"), key=natural_key)), None)
        score_xml = next(iter(sorted(song_dir.glob("choral_music_score.*"), key=natural_key)), None)
        manifest_csv = song_dir / "manifest.csv"
        manifest_json = song_dir / "manifest.json"

        payload = {
            "id": int(song_id),
            "title": title,
            "full_title": full_title,
            "composer": composer,
            "duration_seconds": round(float(audio_info.duration), 3),
            "sample_rate": int(audio_info.samplerate),
            "channels": int(audio_info.channels),
            "voicing": voicing or "—",
            "note_count": all_notes,
            "master": {"filename": master.name, "path": f"songs/{song_id}/{master.name}"},
            "tracks": tracks,
            "alignment": alignment,
            "source": {
                "original_folder": rights_row.get("original_folder", ""),
                "source_file": rights_row.get("manifest_source_file", ""),
                "edition_license": rights_row.get("edition_license", ""),
                "editor": rights_row.get("editor", ""),
                "cpdl_number": rights_row.get("cpdl_number", ""),
                "cpdl_work_page": rights_row.get("cpdl_work_page", ""),
            },
            "files": {
                "mixture_midi": f"songs/{song_id}/{mixture_midi.name}" if mixture_midi else None,
                "score_xml": f"songs/{song_id}/{score_xml.name}" if score_xml else None,
                "manifest_csv": f"songs/{song_id}/manifest.csv" if manifest_csv.exists() else None,
                "manifest_json": f"songs/{song_id}/manifest.json" if manifest_json.exists() else None,
            },
        }
        compact_dump(notes_dir / f"{song_id}.json", payload)
        catalog.append(
            {
                "id": int(song_id),
                "title": title,
                "full_title": full_title,
                "composer": composer,
                "duration_seconds": payload["duration_seconds"],
                "voicing": payload["voicing"],
                "note_count": all_notes,
                "track_count": len(tracks),
            }
        )

    compact_dump(args.site / "docs/data/demo-catalog.json", catalog)
    compact_dump(args.site / "docs/data/zenodo-zip-index.json", zip_entry_index(args.archive))
    print(f"Built demo data for {len(catalog)} works")


if __name__ == "__main__":
    main()
