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
        assert r["tolerance"] in ("1", "2")                           # D/ST rule of G-ESPN (CONTRACTS.md 6): 2 where already 1 off
    assert len(rows) == 10


def test_espn_dst_stats_carry_every_column_of_the_game_log():
    rows = {r["week"]: r for r in fixture("espn_dst_stats.csv") if r["player_id"] == "DST_ARI"}
    for week in game_log():
        r = rows[week["WEEK"]]
        for column in ("TD", "INT", "FR", "SCK", "SFTY", "BLK", "PA"):
            assert r[f"espn_{column.lower()}"] == week[column], (week["WEEK"], column)
    assert len(rows) == 10


# ---- the 2026-11-22 game logs: Allgeier (player rows exact), IND and NYJ D/ST (+/-1; stats exact) -------------

def log_rows(name: str, columns: int) -> list[list[str]]:
    lines = (QA / "evidence" / name).read_text(encoding="utf-8").splitlines()
    values = lines[lines.index("Game Log") + 1 + columns:]
    assert len(values) % columns == 0
    return [values[i:i + columns] for i in range(0, len(values), columns)]


def test_allgeier_game_log_is_in_espn_actuals_exactly():
    weeks = log_rows("espn-game-log-Allgeier-ARI-RB-2026.txt", 11)
    assert [w[0] for w in weeks] == [str(n) for n in range(1, 11)]
    rows = {r["week"]: r for r in fixture("espn_actuals.csv") if r["player_id"] == "00-0037263"}
    assert len(rows) == 10
    for w in weeks:
        r = rows[w[0]]
        assert (r["season"], r["season_type"], r["league"], r["row_expected"]) == ("2026", "REG", "ESPN_League", "Yes")
        assert float(r["espn_points"]) == float(w[10]) and r["tolerance"] == "0"      # a player row is exact


def test_colts_and_jets_game_logs_are_in_espn_actuals_and_stats():
    actuals = fixture("espn_actuals.csv")
    stats = fixture("espn_dst_stats.csv")
    for name, team, last_week in (("espn-game-log-IND-DST-2026.txt", "IND", 11), ("espn-game-log-NYJ-DST-2026.txt", "NYJ", 10)):
        weeks = log_rows(name, 10)
        assert [w[0] for w in weeks] == [str(n) for n in range(1, last_week + 1)]
        a = {r["week"]: r for r in actuals if r["player_id"] == f"DST_{team}"}
        s = {r["week"]: r for r in stats if r["player_id"] == f"DST_{team}"}
        assert len(a) == last_week and len(s) == last_week
        for w in weeks:
            assert float(a[w[0]]["espn_points"]) == float(w[9]) and a[w[0]]["tolerance"] in ("1", "2")
            for column, value in zip(("td", "int", "fr", "sck", "sfty", "blk", "pa"), w[2:9]):
                assert s[w[0]][f"espn_{column}"] == value, (team, w[0], column)


def test_myers_game_log_is_in_espn_actuals_exactly():
    """The blocked-field-goal rule (fg_blocked -1 for ESPN_League) is checked by G-ESPN against ESPN's own score:
    week 8 (CHI) had one blocked kick, and ESPN scores it 2.0 (3.0 without the rule)."""
    weeks = log_rows("espn-game-log-Myers-SEA-K-2026.txt", 8)
    assert [w[0] for w in weeks] == [str(n) for n in range(1, 11)]
    rows = {r["week"]: r for r in fixture("espn_actuals.csv") if r["player_id"] == "00-0031492"}
    assert len(rows) == 10
    for w in weeks:
        r = rows[w[0]]
        assert (r["season"], r["season_type"], r["league"], r["row_expected"]) == ("2026", "REG", "ESPN_League", "Yes")
        assert float(r["espn_points"]) == float(w[7]) and r["tolerance"] == "0"      # a player row is exact
    assert rows["8"]["espn_points"] == "2"
