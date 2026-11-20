"""Read the downloaded nflverse files into plain Python rows.

Only the columns the pipeline needs are kept. Numbers are parsed with ``to_number``:
blank, 'NA' or anything non-numeric becomes None (null), never 0, because
"missing is never zero" (CONTRACTS.md section 3).
"""

from __future__ import annotations

import csv
import gzip
import math
from pathlib import Path
from typing import Iterable, Iterator

# Columns of stats_player_week that are text, not numbers (same list as Stats_Raw.pq).
TEXT_COLUMNS = {
    "player_id", "player_name", "player_display_name", "position", "position_group", "headshot_url",
    "season_type", "game_id", "team", "opponent_team", "fg_made_list", "fg_missed_list", "fg_blocked_list",
}
ID_COLUMNS = ["season", "week", "season_type", "player_id", "player_display_name",
              "position", "position_group", "team", "opponent_team"]
REFERENCE_COLUMNS = ["fantasy_points", "fantasy_points_ppr"]

# Untrusted input: allow long fields (the default 128 KB is plenty for nflverse) but no more.
csv.field_size_limit(1 << 20)


def to_number(text: str | None) -> float | None:
    """Parse an nflverse value as a float; blank, 'NA', NaN or text gives None."""
    if text is None:
        return None
    text = text.strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def read_header(path: Path) -> list[str]:
    """The header row of a CSV file (or .csv.gz)."""
    with _open_text(path) as handle:
        return next(csv.reader(handle), [])


def _open_text(path: Path):
    """Open a CSV, transparently decompressing .gz, as UTF-8 text for the csv module."""
    path = Path(path)
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return open(path, "r", encoding="utf-8", newline="")


def iter_columns(path: Path, wanted: Iterable[str]) -> Iterator[dict[str, str]]:
    """Stream a CSV and yield, per row, a dict holding only the ``wanted`` columns.

    Columns missing from the file come back as ''. Reading by position keeps memory and
    time low on the 370-column play-by-play files.
    """
    wanted = list(dict.fromkeys(wanted))
    with _open_text(path) as handle:
        reader = csv.reader(handle)
        header = next(reader, [])
        index = {name: i for i, name in enumerate(header)}
        positions = [(name, index.get(name)) for name in wanted]
        width = len(header)
        for record in reader:
            if len(record) < width:                   # short (damaged) line: pad, never guess
                record = record + [""] * (width - len(record))
            yield {name: (record[i] if i is not None else "") for name, i in positions}


def read_player_rows(path: Path, season_types: tuple[str, ...], numeric_columns: list[str]) -> list[dict]:
    """Player-game rows of one stats_player_week file.

    Drops placeholder rows (empty player_id) and rows of other season types. Identity
    columns stay text (season and week become int); ``numeric_columns`` and the two
    nflverse fantasy-point columns become float or None.
    """
    numeric = list(dict.fromkeys(numeric_columns + REFERENCE_COLUMNS))
    rows = []
    for raw in iter_columns(path, ID_COLUMNS + numeric):
        season, week = to_number(raw["season"]), to_number(raw["week"])
        if not raw["player_id"].strip() or raw["season_type"] not in season_types or season is None or week is None:
            continue
        row: dict = {c: raw[c] for c in ID_COLUMNS}
        row["season"], row["week"] = int(season), int(week)
        for c in numeric:
            row[c] = to_number(raw[c])
        rows.append(row)
    return rows


def read_games(path: Path) -> list[dict[str, str]]:
    """Schedule rows from games.csv (only the columns the pipeline uses)."""
    cols = ["game_id", "season", "game_type", "week", "away_team", "away_score", "home_team", "home_score"]
    return list(iter_columns(path, cols))


def season_status(games: list[dict[str, str]], season: int) -> str:
    """'complete' when every game of the season has a final score, the Super Bowl included."""
    season_games = [g for g in games if g["season"].strip() == str(season)]
    has_super_bowl = any(g["game_type"] == "SB" for g in season_games)
    all_final = all(g["home_score"].strip() and g["away_score"].strip() for g in season_games)
    return "complete" if season_games and has_super_bowl and all_final else "in_progress"
