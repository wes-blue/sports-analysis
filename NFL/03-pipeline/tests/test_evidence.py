"""The owner's ESPN evidence and the fixtures the gates use agree (06-qa/evidence, 06-qa/fixtures).

``espn-game-log-ARI-DST-2026.txt`` is ESPN's game log exactly as pasted: a header block, then one
value per line in the columns WEEK, OPP, TD, INT, FR, SCK, SFTY, BLK, PA, FPTS. Its ten finished
weeks must appear unchanged in ``espn_actuals.csv`` (FPTS, checked by G-ESPN within +/-1) and in
``espn_dst_stats.csv`` (every stat column, checked by G-ESPN exactly), so a typo in a fixture, or
a fixture edited without new evidence, fails here.
"""

import csv
from pathlib import Path

QA = Path(__file__).resolve().parents[2] / "06-qa"
COLUMNS = ["WEEK", "OPP", "TD", "INT", "FR", "SCK", "SFTY", "BLK", "PA", "FPTS"]


def game_log() -> list[dict[str, str]]:
    lines = (QA / "evidence" / "espn-game-log-ARI-DST-2026.txt").read_text(encoding="utf-8").splitlines()
    start = lines.index("Game Log")
    assert lines[start + 1:start + 11] == COLUMNS
    values, weeks = lines[start + 11:], []
    while len(values) >= 10 and values[2] != "--":                  # "--" marks a week not played yet
        weeks.append(dict(zip(COLUMNS, values[:10])))
        values = values[10:]
    return weeks


def fixture(name: str) -> list[dict[str, str]]:
    with open(QA / "fixtures" / name, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_the_game_log_has_ten_finished_weeks():
    assert [w["WEEK"] for w in game_log()] == [str(n) for n in range(1, 11)]


def test_espn_actuals_carry_every_week_of_the_game_log():
    rows = {r["week"]: r for r in fixture("espn_actuals.csv") if r["player_id"] == "DST_ARI"}
    for week in game_log():
        r = rows[week["WEEK"]]
        assert (r["season"], r["season_type"], r["league"], r["row_expected"]) == ("2026", "REG", "ESPN_League", "Yes")
        assert float(r["espn_points"]) == float(week["FPTS"])
        assert r["tolerance"] == "1"                                  # D/ST rule of G-ESPN (CONTRACTS.md 6)
    assert len(rows) == 10


def test_espn_dst_stats_carry_every_column_of_the_game_log():
    rows = {r["week"]: r for r in fixture("espn_dst_stats.csv") if r["player_id"] == "DST_ARI"}
    for week in game_log():
        r = rows[week["WEEK"]]
        for column in ("TD", "INT", "FR", "SCK", "SFTY", "BLK", "PA"):
            assert r[f"espn_{column.lower()}"] == week[column], (week["WEEK"], column)
    assert len(rows) == 10
