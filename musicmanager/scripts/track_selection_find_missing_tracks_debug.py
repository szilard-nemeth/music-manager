import argparse
from dataclasses import dataclass
from typing import List, Optional

from rapidfuzz import fuzz

from musicmanager.scripts.track_selection_find_missing_tracks import (
    MIN_SCORE,
    GoogleSheetFetcher,
    SPREADSHEET_ID,
    TrackEntry,
    TrackIndex,
    TrackIndexer,
    TrackTitleHelpers,
    artist_conflict,
    find_matching_tracks,
    version_conflict,
)


@dataclass
class MatchBreakdown:
    score: float
    blocked: bool
    block_reason: Optional[str]
    query_core_title: str
    candidate_core_title: str
    query_artist: str
    candidate_artist: str
    title_score: float
    artist_score: float
    context_score: float
    artist_conflict: bool
    version_conflict: bool
    single_token_exact_match: bool


def match_score_details(query, entry: TrackEntry, query_artist: str) -> MatchBreakdown:
    query_core_title = TrackTitleHelpers.core_title(query)
    query_artist_norm = TrackTitleHelpers.normalize(query_artist)

    cand_core_title = entry.core_title
    cand_artist = entry.artist

    artist_conflict_hit = artist_conflict(query_artist_norm, cand_artist)
    if artist_conflict_hit:
        return MatchBreakdown(
            score=0,
            blocked=True,
            block_reason="artist_conflict",
            query_core_title=query_core_title,
            candidate_core_title=cand_core_title,
            query_artist=query_artist_norm,
            candidate_artist=cand_artist,
            title_score=0,
            artist_score=0,
            context_score=0,
            artist_conflict=True,
            version_conflict=False,
            single_token_exact_match=False,
        )

    _, cand_raw_title = TrackTitleHelpers.split(entry.path.stem)
    version_conflict_hit = version_conflict(query, cand_raw_title)
    if version_conflict_hit:
        return MatchBreakdown(
            score=0,
            blocked=True,
            block_reason="version_conflict",
            query_core_title=query_core_title,
            candidate_core_title=cand_core_title,
            query_artist=query_artist_norm,
            candidate_artist=cand_artist,
            title_score=0,
            artist_score=0,
            context_score=0,
            artist_conflict=False,
            version_conflict=True,
            single_token_exact_match=False,
        )

    single_token_exact_match = False
    if TrackTitleHelpers.is_single_token_title(query_core_title):
        if query_core_title != cand_core_title:
            return MatchBreakdown(
                score=0,
                blocked=True,
                block_reason="single_token_title_mismatch",
                query_core_title=query_core_title,
                candidate_core_title=cand_core_title,
                query_artist=query_artist_norm,
                candidate_artist=cand_artist,
                title_score=0,
                artist_score=0,
                context_score=0,
                artist_conflict=False,
                version_conflict=False,
                single_token_exact_match=False,
            )

        title_score = 100
        single_token_exact_match = True
    else:
        title_score = fuzz.WRatio(query_core_title, cand_core_title)

    artist_score = (
        fuzz.WRatio(query_artist_norm, entry.artist)
        if query_artist_norm else 0
    )

    context_score = fuzz.partial_ratio(
        TrackTitleHelpers.normalize(query),
        entry.full_norm
    )

    score = (
        title_score * 0.85 +
        artist_score * 0.10 +
        context_score * 0.05
    )

    return MatchBreakdown(
        score=score,
        blocked=False,
        block_reason=None,
        query_core_title=query_core_title,
        candidate_core_title=cand_core_title,
        query_artist=query_artist_norm,
        candidate_artist=cand_artist,
        title_score=title_score,
        artist_score=artist_score,
        context_score=context_score,
        artist_conflict=False,
        version_conflict=False,
        single_token_exact_match=single_token_exact_match,
    )


def format_match_breakdown(track: str, entry: TrackEntry, breakdown: MatchBreakdown) -> str:
    lines = [
        f"  candidate: {entry.path}",
        f"    total score: {breakdown.score:.1f}% (threshold: {MIN_SCORE}%)",
    ]

    if breakdown.blocked:
        lines.append(f"    blocked: {breakdown.block_reason}")
    else:
        lines.extend([
            "    components:",
            f"      title:   {breakdown.title_score:.1f}% x 0.85 = {breakdown.title_score * 0.85:.1f}%",
            f"      artist:  {breakdown.artist_score:.1f}% x 0.10 = {breakdown.artist_score * 0.10:.1f}%",
            f"      context: {breakdown.context_score:.1f}% x 0.05 = {breakdown.context_score * 0.05:.1f}%",
        ])

    lines.extend([
        "    normalized:",
        f"      query title:      {breakdown.query_core_title!r}",
        f"      candidate title:  {breakdown.candidate_core_title!r}",
        f"      query artist:     {breakdown.query_artist!r}",
        f"      candidate artist: {breakdown.candidate_artist!r}",
        f"      candidate full:   {entry.full_norm!r}",
    ])

    return "\n".join(lines)


def debug_track_match(track: str, index: TrackIndex, top_n: int = 10) -> None:
    artist, title = TrackTitleHelpers.split(track)

    ranked = []
    for entry in index.tracks:
        breakdown = match_score_details(title, entry, artist)
        ranked.append((breakdown.score, entry, breakdown))

    ranked.sort(key=lambda item: item[0], reverse=True)

    print(f"DEBUG: {track}")
    print(f"  parsed artist: {artist!r}")
    print(f"  parsed title:  {title!r}")
    print(f"  top {top_n} candidates:")

    for _, entry, breakdown in ranked[:top_n]:
        print(format_match_breakdown(track, entry, breakdown))
        print()


def find_matching_tracks_with_debug(
    tracks: List[str],
    index: TrackIndex,
    debug: bool = False,
    debug_track: Optional[str] = None,
) -> None:
    found = 0

    for idx, track in enumerate(tracks):
        if debug_track and track != debug_track:
            continue

        artist, title = TrackTitleHelpers.split(track)

        best = None
        best_score = 0
        best_breakdown = None

        for entry in index.tracks:
            breakdown = match_score_details(title, entry, artist)
            score = breakdown.score

            if score > best_score:
                best_score = score
                best = entry
                best_breakdown = breakdown

        prefix = f"[{idx + 1} / {len(tracks)}]"
        if best and best_score >= MIN_SCORE:
            print(
                f"{prefix} FOUND: {track}\n"
                f"    -> {best.path} ({best_score:.0f}%)"
            )
            if debug or debug_track:
                print(format_match_breakdown(track, best, best_breakdown))
            found += 1
        else:
            print(f"{prefix} NOT FOUND: {track}")
            if debug or debug_track:
                debug_track_match(track, index)

    print()
    print(f"{found}/{len(tracks)} tracks found")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Debug track matching against the local music library."
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print score breakdown for every match.",
    )
    parser.add_argument(
        "--debug-track",
        metavar="TRACK",
        help='Debug one track and show top candidates, e.g. "Guy J - Against The Wall".',
    )
    return parser.parse_args()


def main():
    args = parse_args()
    indexer = TrackIndexer()
    index = indexer.build_index()

    if args.debug_track and not args.debug:
        debug_track_match(args.debug_track, index)
        return

    old_tracks = GoogleSheetFetcher.fetch_tracks(SPREADSHEET_ID, "OLD TRACKS")
    new_tracks = GoogleSheetFetcher.fetch_tracks(SPREADSHEET_ID, "NEW TRACKS")
    all_tracks = old_tracks + new_tracks

    if args.debug or args.debug_track:
        find_matching_tracks_with_debug(
            all_tracks,
            index,
            debug=args.debug,
            debug_track=args.debug_track,
        )
        return

    find_matching_tracks(all_tracks, index)


if __name__ == "__main__":
    main()
