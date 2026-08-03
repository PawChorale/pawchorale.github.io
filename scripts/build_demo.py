#!/usr/bin/env python3
"""Build the lightweight interactive PawChorale demo from retained work 93.

Run this script inside the ``hanyu_env`` Conda environment because it uses
``pretty_midi`` and ``soundfile`` to inspect the source assets.
"""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import pretty_midi
import soundfile as sf


PROJECT = Path(__file__).resolve().parents[1]
WORKSPACE = PROJECT.parent
SONG_ID = 93
SOURCE = WORKSPACE / "organized_mp3" / str(SONG_ID)
TARGET = PROJECT / "docs" / "demo" / str(SONG_ID)
TITLE = "Cucu, cucu! (Juan del Encina)"
PARTS = (
    ("Soprano", "93_Soprano.mp3", "01_Soprano.mid", "#7b2635"),
    ("Alto", "93_Alto.mp3", "02_Alto.mid", "#dd6a53"),
    ("Tenor", "93_Tenor.mp3", "03_Tenor.mid", "#d4a13e"),
    ("Bass", "93_Bass.mp3", "04_Bass.mid", "#5d8a72"),
)


def alignment_rows() -> dict[str, dict[str, float]]:
    source = WORKSPACE / "reports" / "table2" / "alignment_per_work.csv"
    results: dict[str, dict[str, float]] = {}
    with source.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if int(row["song_id"]) != SONG_ID:
                continue
            results[row["part"]] = {
                "matched_notes_percent": round(
                    float(row["corrected_matched_note_rate_percent"]), 2
                ),
                "onset_within_50ms_percent": round(
                    float(row["corrected_onset_within_50ms_percent_of_matched"]), 2
                ),
                "median_onset_error_ms": round(
                    float(row["corrected_median_absolute_onset_error_ms"]), 2
                ),
            }
    return results


def midi_track(part: str, audio_file: str, midi_file: str, color: str) -> dict:
    midi = pretty_midi.PrettyMIDI(str(SOURCE / midi_file))
    notes = sorted(
        (
            {
                "pitch": note.pitch,
                "start": round(note.start, 5),
                "end": round(note.end, 5),
            }
            for instrument in midi.instruments
            for note in instrument.notes
        ),
        key=lambda note: (note["start"], note["pitch"]),
    )
    return {
        "part": part,
        "audio_file": audio_file,
        "midi_file": midi_file,
        "color": color,
        "note_count": len(notes),
        "pitch_min": min(note["pitch"] for note in notes),
        "pitch_max": max(note["pitch"] for note in notes),
        "notes": notes,
    }


def main() -> None:
    if not SOURCE.is_dir():
        raise FileNotFoundError(SOURCE)
    TARGET.mkdir(parents=True, exist_ok=True)

    media_files = ["93_master.mp3", "manifest.json"]
    media_files.extend(item for _, audio, midi, _ in PARTS for item in (audio, midi))
    for filename in media_files:
        shutil.copy2(SOURCE / filename, TARGET / filename)
    (TARGET / "manifest.csv").write_text(
        (SOURCE / "manifest.csv").read_text(encoding="utf-8-sig").replace("\r\n", "\n"),
        encoding="utf-8",
    )

    audio_info = sf.info(str(SOURCE / "93_master.mp3"))
    tracks = [midi_track(*part) for part in PARTS]
    payload = {
        "song_id": SONG_ID,
        "title": TITLE,
        "duration_seconds": round(audio_info.duration, 5),
        "score_duration_seconds": 52.0,
        "master_file": "93_master.mp3",
        "tracks": tracks,
        "alignment": alignment_rows(),
        "rendering": {
            "format": "MP3 (MPEG Layer III)",
            "sample_rate_hz": audio_info.samplerate,
            "channels": audio_info.channels,
            "part_layout": "master mixture + SATB isolated parts",
            "time_reference": "seconds from recording start",
        },
        "source": {
            "source_file": "0840.xml",
            "original_folder": "0840",
            "manifest_file": "manifest.json",
        },
    }
    with (TARGET / "notes.json").open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    size = sum(path.stat().st_size for path in TARGET.iterdir() if path.is_file())
    print(f"Demo work: {SONG_ID} — {TITLE}")
    print(f"Tracks: {len(tracks)} parts + master")
    print(f"Notes: {sum(track['note_count'] for track in tracks)}")
    print(f"Demo size: {size / 1024**2:.2f} MiB")


if __name__ == "__main__":
    main()
