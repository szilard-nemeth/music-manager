from pathlib import Path
import re
import csv
import requests
from rapidfuzz import process, fuzz

# ---------------------------
# CONFIGURATION
# ---------------------------

SPREADSHEET_ID = "1F2KvSq53AAgQg1wy0puytd0qWXlYu_R9OjhbzcwH2fc"
SHEET_NAME = "Sheet1"  # adjust if needed

MUSIC_DIR = "'/Volumes/NO NAME/music-library'"

EXTENSIONS = {
    ".mp3",
    ".flac",
    ".wav",
    ".aiff",
    ".m4a",
    ".aac",
}

MIN_SCORE = 90


# ---------------------------
# HELPERS
# ---------------------------

def normalize(text: str) -> str:
    text = text.lower()

    # remove bracketed mix/version info
    text = re.sub(r"\[[^]]*]", "", text)
    text = re.sub(r"\([^)]*]", "", text)

    # remove punctuation
    text = re.sub(r"[^a-z0-9]+", " ", text)

    return " ".join(text.split())


def extract_title(track_name: str) -> str:
    parts = track_name.split(" - ", 1)
    return parts[1] if len(parts) == 2 else track_name


# ---------------------------
# FETCH TRACKS FROM GOOGLE SHEET
# ---------------------------

def fetch_tracks_from_google_sheet():
    global url, reader, tracks
    url = (
        f"https://docs.google.com/spreadsheets/d/"
        f"{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&sheet={SHEET_NAME}"
    )

    response = requests.get(url)
    response.raise_for_status()

    reader = csv.reader(response.text.splitlines())

    tracks = []

    for row in reader:
        if row and row[0].strip():
            tracks.append(row[0].strip())

    print(f"Loaded {len(tracks)} tracks from Google Sheet")


# ---------------------------
# BUILD INDEX
# ---------------------------

def build_index():
    global file_map, choices
    file_map = {}

    for file in Path(MUSIC_DIR).rglob("*"):
        if file.suffix.lower() not in EXTENSIONS:
            continue

        normalized = normalize(file.stem)
        file_map[normalized] = file

    choices = list(file_map.keys())

    print(f"Indexed {len(choices)} music files")


# ---------------------------
# MATCH
# ---------------------------

def find_matching_tracks():
    global title, match
    found_count = 0

    for track in tracks:
        title = normalize(extract_title(track))

        match = process.extractOne(
            title,
            choices,
            scorer=fuzz.token_set_ratio,
            score_cutoff=MIN_SCORE,
        )

        if match:
            matched_name, score, _ = match

            print(
                f"✓ {track}\n"
                f"    -> {file_map[matched_name].name} "
                f"({score:.0f}%)"
            )

            found_count += 1

        else:
            print(f"✗ {track}")

    print()
    print(f"{found_count}/{len(tracks)} tracks found")


def main():
    fetch_tracks_from_google_sheet()
    build_index()
    find_matching_tracks()

if __name__ == '__main__':
    main()
