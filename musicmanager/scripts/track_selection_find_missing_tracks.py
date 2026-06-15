from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import re
import csv
from typing import List, Dict, Tuple
import requests
from rapidfuzz import fuzz

# ---------------------------
# CONFIG
# ---------------------------

SPREADSHEET_ID = "1F2KvSq53AAgQg1wy0puytd0qWXlYu_R9OjhbzcwH2fc"

MUSIC_DIR = "/Volumes/NO NAME/music-library"

EXTENSIONS = {".mp3", ".flac", ".wav", ".aiff", ".m4a", ".aac"}

MIN_SCORE = 85


# ---------------------------
# NORMALIZATION
# ---------------------------

class TrackTitleHelpers:
    NOISE_WORDS = {
        "remix", "edit", "mix", "extended", "radio", "version",
        "remastered", "club", "live", "stereo", "feat", "featuring"
    }

    VERSION_WORDS = {
        "remix", "edit", "mix", "revisit", "rework",
        "reimagined", "version", "dub", "reconstruction"
    }

    SUFFIX_VERSION_TYPE_WORDS = VERSION_WORDS

    BASE_VERSION_WORDS = {"original"}

    @staticmethod
    def normalize(text: str) -> str:
        text = text.lower()

        text = re.sub(r"\[[^]]*]", "", text)
        text = re.sub(r"\([^)]*\)", "", text)

        text = re.sub(r"[^a-z0-9]+", " ", text)

        tokens = [
            t for t in text.split()
            if t not in TrackTitleHelpers.NOISE_WORDS
        ]

        return " ".join(tokens)

    @staticmethod
    def split(track_name: str) -> Tuple[str, str]:
        # Supported filename formats:
        #   "Artist - Title"              e.g. Miguel Ante - Whisper Secrets
        #   "NN-artist_name-track_title"  e.g. 01-miguel_ante-whisper_secrets
        parts = track_name.split(" - ", 1)
        if len(parts) == 2:
            return parts[0], parts[1]

        stem = re.sub(r"^\d+-", "", track_name)
        hyphen_parts = stem.split("-", 1)
        if len(hyphen_parts) == 2:
            artist = hyphen_parts[0].replace("_", " ")
            title = hyphen_parts[1].replace("_", " ")
            return artist, title

        return "", track_name

    @staticmethod
    def core_title(text: str) -> str:
        """Remove everything except the main song title signal."""
        text = TrackTitleHelpers.normalize(text)

        # remove feature noise inside titles
        text = re.sub(r"\bfeat\b.*", "", text)
        text = re.sub(r"\bft\b.*", "", text)

        return text.strip()

    @staticmethod
    def is_single_token_title(text: str) -> bool:
        return len(text.split()) == 1

    @staticmethod
    def extract_version(text: str) -> set:
        text = text.lower()
        tokens = re.sub(r"[^a-z0-9]+", " ", text).split()
        return set(w for w in tokens if w in TrackTitleHelpers.VERSION_WORDS)

    @staticmethod
    def extract_parenthetical_suffix(text: str) -> str:
        """Normalize parenthetical remix/version suffixes for comparison."""
        matches = re.findall(r"\(([^)]*)\)", text.lower())
        if not matches:
            return ""

        suffix = matches[-1]
        suffix = re.sub(r"[^a-z0-9]+", " ", suffix)
        tokens = [
            t for t in suffix.split()
            if t not in TrackTitleHelpers.SUFFIX_VERSION_TYPE_WORDS
        ]

        if not tokens or all(t in TrackTitleHelpers.BASE_VERSION_WORDS for t in tokens):
            return ""

        return " ".join(tokens)


# ---------------------------
# INDEX
# ---------------------------

@dataclass
class TrackEntry:
    path: Path
    artist: str
    title: str
    full_norm: str
    core_title: str


class TrackIndex:
    def __init__(self):
        self.tracks: List[TrackEntry] = []
        self._file_map = {}  # this is only for duplicate tracking
        self._duplicates: Dict[str, List[Path]] = defaultdict(list)

    def add_file(self, path: Path):
        artist, title = TrackTitleHelpers.split(path.stem)

        normalized_title = TrackTitleHelpers.normalize(title)
        if normalized_title in self._file_map:
            self._duplicates[normalized_title].append(self._file_map[normalized_title])
            self._duplicates[normalized_title].append(path)
        entry = TrackEntry(
            path=path,
            artist=TrackTitleHelpers.normalize(artist),
            title=TrackTitleHelpers.normalize(title),
            full_norm=TrackTitleHelpers.normalize(path.stem),
            core_title=TrackTitleHelpers.core_title(title),
        )

        self.tracks.append(entry)
        self._file_map[normalized_title] = path

    @property
    def normalized_names(self):
        return list(self.file_map.keys())

    def print_duplicates(self):
        print("Duplicates: ")
        # TODO This could be used as a duplicate file remover
        for k, v in self._duplicates.items():
            print(f"{k}: {v}")


# ---------------------------
# INDEXER
# ---------------------------

class TrackIndexer:
    def __init__(self):
        self.index = TrackIndex()

    def build_index(self):
        path = self._validate_path()

        if not path.exists():
            raise FileNotFoundError(f"MUSIC_DIR does not exist: {path}")

        files = list(path.rglob("*"))
        indexed = 0

        for file in files:
            if file.is_dir():
                continue

            if file.suffix.lower() not in EXTENSIONS:
                continue

            self.index.add_file(file)
            indexed += 1

        if indexed == 0:
            raise RuntimeError(f"No audio files found in {path}")

        print(f"Indexed {indexed} tracks")
        return self.index

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

        tracks = [
            row[0].strip()
            for row in reader
            if row and row[0].strip()
        ]

        print(f"Loaded {len(tracks)} tracks from {sheet_name}")
        return tracks


# ---------------------------
# MATCHER
# ---------------------------

class TrackMatcher:

    @staticmethod
    def artist_conflict(query_artist: str, candidate_artist: str) -> bool:
        if not query_artist:
            return False

        query = set(query_artist.split())
        candidate = set(candidate_artist.split())

        # no overlap at all → strong signal mismatch
        return len(query & candidate) == 0

    @staticmethod
    def version_conflict(q: str, c: str) -> bool:
        q_suffix = TrackTitleHelpers.extract_parenthetical_suffix(q)
        c_suffix = TrackTitleHelpers.extract_parenthetical_suffix(c)

        if q_suffix != c_suffix and (q_suffix or c_suffix):
            return True

        qv = TrackTitleHelpers.extract_version(q)
        cv = TrackTitleHelpers.extract_version(c)

        # if both have version tags but they differ → conflict
        return bool(qv and cv and qv != cv)

    @staticmethod
    def match_score(query, entry: TrackEntry, query_artist: str) -> float:
        query_title = TrackTitleHelpers.core_title(query)
        query_artist = TrackTitleHelpers.normalize(query_artist)

        cand_title = entry.core_title
        cand_artist = entry.artist

        # Hard block if artist would not match
        if artist_conflict(query_artist, cand_artist):
            return 0
        _, cand_raw_title = TrackTitleHelpers.split(entry.path.stem)
        if version_conflict(query, cand_raw_title):
            return 0

        # 🚨 HARD RULE: single-token titles cannot match loosely
        if TrackTitleHelpers.is_single_token_title(query_title):
            # require exact token match only
            if query_title != cand_title:
                return 0

            title_score = 100
        else:
            title_score = fuzz.WRatio(query_title, cand_title)

        artist_score = (
            fuzz.WRatio(query_artist, entry.artist)
            if query_artist else 0
        )

        # weak full-context signal
        context_score = fuzz.partial_ratio(
            TrackTitleHelpers.normalize(query),
            entry.full_norm
        )

        return (
            title_score * 0.85 +
            artist_score * 0.10 +
            context_score * 0.05
        )

    @staticmethod
    def find_matching_tracks(tracks: List[str], index: TrackIndex) -> None:
        found = 0

        for idx, track in enumerate(tracks):
            artist, title = TrackTitleHelpers.split(track)

            best = None
            best_score = 0

            for entry in index.tracks:
                score = match_score(title, entry, artist)

                if score > best_score:
                    best_score = score
                    best = entry

            prefix = f"[{idx + 1} / {len(tracks)}]"
            if best and best_score >= MIN_SCORE:
                print(
                    f"{prefix} FOUND: {track}\n"
                    f"    -> {best.path} ({best_score:.0f}%)"
                )
                found += 1
            else:
                print(f"{prefix} NOT FOUND: {track}")

        print()
        print(f"{found}/{len(tracks)} tracks found")


# ---------------------------
# MAIN
# ---------------------------

def main():
    indexer = TrackIndexer()
    index = indexer.build_index()

    old_tracks = GoogleSheetFetcher.fetch_tracks(SPREADSHEET_ID, "OLD TRACKS")
    new_tracks = GoogleSheetFetcher.fetch_tracks(SPREADSHEET_ID, "NEW TRACKS")

    all_tracks = old_tracks + new_tracks

    TrackMatcher.find_matching_tracks(all_tracks, index)


if __name__ == "__main__":
    main()