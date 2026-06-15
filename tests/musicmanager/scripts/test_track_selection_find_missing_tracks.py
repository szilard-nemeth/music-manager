import unittest
from pathlib import Path

from musicmanager.scripts.track_selection_find_missing_tracks import (
    MIN_SCORE,
    TrackEntry,
    TrackTitleHelpers,
    match_score,
    version_conflict,
)
from musicmanager.scripts.track_selection_find_missing_tracks_debug import match_score_details


def make_entry(stem: str) -> TrackEntry:
    artist, title = TrackTitleHelpers.split(stem)
    return TrackEntry(
        path=Path(f"/music-library/{stem}.mp3"),
        artist=TrackTitleHelpers.normalize(artist),
        title=TrackTitleHelpers.normalize(title),
        full_norm=TrackTitleHelpers.normalize(stem),
        core_title=TrackTitleHelpers.core_title(title),
    )


class TrackSelectionFindMissingTracksTest(unittest.TestCase):
    def test_different_remix_suffixes_are_not_a_match(self):
        query_track = "Luka Sambe - Sooti (Emotional Tourist & RVNZ Revisit)"
        library_track = "Luka Sambe - Sooti (Eli Nissan Remix)"

        query_artist, query_title = TrackTitleHelpers.split(query_track)
        entry = make_entry(library_track)

        self.assertTrue(version_conflict(query_title, TrackTitleHelpers.split(library_track)[1]))
        self.assertLess(match_score(query_title, entry, query_artist), MIN_SCORE)

    def test_same_remix_suffix_still_matches(self):
        query_track = "Luka Sambe - Sooti (Eli Nissan Remix)"
        library_track = "Luka Sambe - Sooti (Eli Nissan Remix)"

        query_artist, query_title = TrackTitleHelpers.split(query_track)
        entry = make_entry(library_track)

        self.assertFalse(version_conflict(query_title, TrackTitleHelpers.split(library_track)[1]))
        self.assertGreaterEqual(match_score(query_title, entry, query_artist), MIN_SCORE)

    def test_plain_title_matches_original_mix_in_library(self):
        query_track = "Matter - Embrace"
        library_track = "Matter - Embrace (Original Mix)"

        query_artist, query_title = TrackTitleHelpers.split(query_track)
        entry = make_entry(library_track)

        self.assertFalse(version_conflict(query_title, TrackTitleHelpers.split(library_track)[1]))
        self.assertGreaterEqual(match_score(query_title, entry, query_artist), MIN_SCORE)

    def test_plain_title_does_not_match_extended_mix_in_library(self):
        query_track = "Matter - Embrace"
        library_track = "Matter - Embrace (Extended Mix)"

        query_artist, query_title = TrackTitleHelpers.split(query_track)
        entry = make_entry(library_track)

        self.assertTrue(version_conflict(query_title, TrackTitleHelpers.split(library_track)[1]))
        self.assertLess(match_score(query_title, entry, query_artist), MIN_SCORE)

    def test_numbered_underscore_filename_matches_spreadsheet_title(self):
        query_track = "Miguel Ante - Whisper Secrets"
        library_track = "01-miguel_ante-whisper_secrets"

        query_artist, query_title = TrackTitleHelpers.split(query_track)
        entry = make_entry(library_track)

        self.assertEqual(TrackTitleHelpers.split(library_track), ("miguel ante", "whisper secrets"))
        self.assertGreaterEqual(match_score(query_title, entry, query_artist), MIN_SCORE)

    def test_match_score_details_exposes_component_scores(self):
        query_track = "Guy J - Against The Wall"
        library_track = "Guy J - The Fall (Original Mix)"

        query_artist, query_title = TrackTitleHelpers.split(query_track)
        entry = make_entry(library_track)
        breakdown = match_score_details(query_title, entry, query_artist)

        self.assertFalse(breakdown.blocked)
        self.assertEqual(breakdown.query_core_title, "against the wall")
        self.assertEqual(breakdown.candidate_core_title, "the fall")
        self.assertGreater(breakdown.artist_score, 90)
        self.assertGreater(breakdown.title_score, 80)
        self.assertGreaterEqual(breakdown.score, MIN_SCORE)


if __name__ == "__main__":
    unittest.main()
