from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import re
import csv
from typing import List, Dict

import requests
from rapidfuzz import process, fuzz

# ---------------------------
# CONFIGURATION
# ---------------------------

SPREADSHEET_ID = "1F2KvSq53AAgQg1wy0puytd0qWXlYu_R9OjhbzcwH2fc"
SHEET_NAME = "Sheet1"  # adjust if needed

MUSIC_DIR = "/Volumes/NO NAME/music-library"

EXTENSIONS = {
    ".mp3",
    ".flac",
    ".wav",
    ".aiff",
    ".m4a",
    ".aac",
}

MIN_SCORE = 90

class TrackTitleHelpers:
    @staticmethod
    def normalize(text: str) -> str:
        text = text.lower()

        # remove bracketed mix/version info
        text = re.sub(r"\[[^]]*]", "", text)
        text = re.sub(r"\([^)]*]", "", text)

        # remove punctuation
        text = re.sub(r"[^a-z0-9]+", " ", text)
        return " ".join(text.split())

    @staticmethod
    def extract_title(track_name: str) -> str:
        parts = track_name.split(" - ", 1)
        return parts[1] if len(parts) == 2 else track_name


class TrackIndexer:
    def __init__(self):
        self._index = None

    def build_index(self):
        path = self._validate_path()
        self._index = TrackIndex()

        files = list(path.rglob("*"))
        indexed_count = 0
        for file in files:
            if file.is_dir():
                continue

            if file.suffix.lower() not in EXTENSIONS:
                continue

            normalized_name = TrackTitleHelpers.normalize(file.stem)
            self._index.add_file(normalized_name, file)
            indexed_count += 1

        if indexed_count == 0:
            raise RuntimeError(
                f"Directory scanned but no valid audio files found in: {path}"
            )

        print(f"Indexed {indexed_count} music files")
        self._index.print_duplicates()

        return self._index

    @staticmethod
    def _validate_path() -> Path:
        path = Path(MUSIC_DIR)

        if not path.exists():
            raise FileNotFoundError(f"MUSIC_DIR does not exist: {path}")

        files = list(path.rglob("*"))

        if not files:
            raise RuntimeError(
                f"No files found in MUSIC_DIR: {path}. "
                "Check path or permissions."
            )
        return path


@dataclass
class TrackIndex:
    def __init__(self):
        self.file_map = {}
        self._duplicates: Dict[str, List[Path]] = defaultdict(list)

    def add_file(self, normalized_name: str, file: Path):
        if normalized_name in self.file_map:
            self._duplicates[normalized_name].append(self.file_map[normalized_name])
            self._duplicates[normalized_name].append(file)
        self.file_map[normalized_name] = file

    @property
    def normalized_names(self):
        return list(self.file_map.keys())

    def print_duplicates(self):
        print("Duplicates: ")
        # TODO This could be used as a duplicate file remover
        for k, v in self._duplicates.items():
            print(f"{k}: {v}")


class GoogleSheetFetcher:
    @staticmethod
    def fetch_tracks(spreadsheet_id, sheet_name: str):
        url = (
            f"https://docs.google.com/spreadsheets/d/"
            f"{spreadsheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
        )

        response = requests.get(url)
        response.raise_for_status()

        reader = csv.reader(response.text.splitlines())

        tracks = []

        for row in reader:
            if row and row[0].strip():
                tracks.append(row[0].strip())

        print(f"Loaded {len(tracks)} tracks from Google Sheet")
        return tracks


def find_matching_tracks(tracks: List[str], index: TrackIndex) -> None:
    found_count = 0

    file_map = index.file_map
    for track in tracks:
        title = TrackTitleHelpers.normalize(TrackTitleHelpers.extract_title(track))

        match = process.extractOne(
            title,
            index.normalized_names,
            scorer=fuzz.token_set_ratio,
            score_cutoff=MIN_SCORE,
        )

        if match:
            matched_name, score, _ = match

            print(
                f"FOUND: {track}\n"
                f"    -> {file_map[matched_name]} "
                f"({score:.0f}%)"
            )

            found_count += 1

        else:
            print(f"NOT FOUND: {track}")

    print()
    print(f"{found_count}/{len(tracks)} tracks found")


def main():
    indexer = TrackIndexer()
    index: TrackIndex = indexer.build_index()

    old_tracks = GoogleSheetFetcher.fetch_tracks(SPREADSHEET_ID, "OLD TRACKS")
    new_tracks = GoogleSheetFetcher.fetch_tracks(SPREADSHEET_ID, "NEW TRACKS")
    all_tracks = old_tracks + new_tracks
    find_matching_tracks(all_tracks, index)

if __name__ == '__main__':
    main()
