"""Config validation (CONTRACTS.md section 1) and the season-window resolver."""

import pytest

import miniverse
from nflpipe.config import ConfigError, load_config, parse_season_spec, resolve_window
from nflpipe.run import parse_season_request


@pytest.fixture
def cfg(tmp_path):
    return miniverse.write_config(tmp_path / "cfg")


def edit(folder, name, old, new):
    path = folder / name
    text = path.read_text()
    assert old in text, f"{old!r} not in {name}"
    path.write_text(text.replace(old, new, 1))


def problems(folder):
    return load_config(folder).problems


def test_valid_config_has_no_problems(cfg):
    config = load_config(cfg)
    assert config.problems == []
    assert [lg.name for lg in config.control_leagues] == ["Standard", "PPR"]
    assert config.season_types == ("REG", "POST") and config.round_decimals == 2


@pytest.mark.parametrize("name,old,new,expected", [
    ("pipeline_config.csv", "RoundDecimals,2", "RoundDecimals,7", "RoundDecimals must be a whole number"),
    ("pipeline_config.csv", "SeasonTypes,REG+POST", "SeasonTypes,PRE", "SeasonTypes must be"),
    ("pipeline_config.csv", "EndSeason,Latest", "EndSeason,Latest-x", "EndSeason"),
    ("pipeline_config.csv", "StartSeason,Latest-1", "StartSeason,1990", "before 1999"),
    ("pipeline_config.csv", "ReconcileTolerance,0.005", "ReconcileTolerance,-1", "ReconcileTolerance"),
    ("pipeline_config.csv", "ReconcileTolerance,0.005,,", "ReconcileTolerance,0.005,,\nColour,Blue,,",
     "unknown setting 'Colour'"),
    ("pipeline_config.csv", "PublishExtraColumns,,,\n", "", "setting 'PublishExtraColumns' is missing"),
    ("leagues.csv", "Custom,Custom league,Yes", "Custom,Custom league,Maybe", "use Yes or No"),
    ("leagues.csv", "Custom,Custom league,Yes,,", "Custom,Custom league,Yes,points,", "Reconcile_To"),
    ("leagues.csv", "Custom,Custom league", "Custom2,Custom league", "no weights column for league 'Custom2'"),
    ("leagues.csv", "Custom,Custom league", "9Custom,Custom league", "not a valid league name"),
    ("scoring_weights.csv", "passing_tds,Passing,,4", "passing_tds,Passing,,four", "'four' is not a number"),
    ("scoring_weights.csv", "rushing_tds,", "passing_tds,", "metric 'passing_tds' appears more than once"),
    ("bonus_rules.csv", "Custom,passing_yards,300,399", "Custom,passing_yards,399,300", "greater than Upper"),
    ("bonus_rules.csv", "Custom,passing_yards,300,399,1", "Custom,passing_yards,300,399,x", "Points 'x'"),
    ("bonus_rules.csv", "Custom,passing_yards,300", "Nobody,passing_yards,300", "league 'Nobody' is not in"),
])
def test_config_problems_are_reported(cfg, name, old, new, expected):
    edit(cfg, name, old, new)
    found = problems(cfg)
    assert any(expected in p for p in found), found


def test_missing_file_or_column_is_an_error(cfg):
    (cfg / "bonus_rules.csv").unlink()
    with pytest.raises(ConfigError):
        load_config(cfg)


def test_missing_required_column_is_an_error(cfg):
    edit(cfg, "scoring_weights.csv", ",Applies_To", ",Gate")
    with pytest.raises(ConfigError):
        load_config(cfg)


def test_byte_order_mark_is_accepted(cfg):
    path = cfg / "leagues.csv"
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    assert problems(cfg) == []


# ---- season window -----------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("Latest", ("latest", 0)), ("latest-9", ("latest", 9)), (" Latest - 3 ", ("latest", 3)),
    ("2017", ("year", 2017)), ("LATEST-30", ("latest", 30)),
])
def test_parse_season_spec(text, expected):
    assert parse_season_spec(text) == expected


@pytest.mark.parametrize("text", ["", "Latest-31", "Latest+1", "1998", "next", "20x7"])
def test_parse_season_spec_rejects(text):
    with pytest.raises(ValueError):
        parse_season_spec(text)


def window(cfg, start, end, latest):
    edit(cfg, "pipeline_config.csv", "StartSeason,Latest-1", f"StartSeason,{start}")
    edit(cfg, "pipeline_config.csv", "EndSeason,Latest", f"EndSeason,{end}")
    return resolve_window(load_config(cfg), latest)


def test_rolling_ten_seasons(cfg):
    assert window(cfg, "Latest-9", "Latest", 2026) == (2017, 2026)


def test_pinned_start_and_lagging_end(cfg):
    assert window(cfg, "2020", "Latest-1", 2026) == (2020, 2025)


def test_start_after_end_is_an_error(cfg):
    with pytest.raises(ConfigError):
        window(cfg, "2027", "Latest", 2026)


def test_parse_season_request():
    w = list(range(2017, 2027))
    assert parse_season_request("current", w) is None
    assert parse_season_request("ALL", w) == w
    assert parse_season_request("2025", w) == [2025]
    assert parse_season_request("2023-2025", w) == [2023, 2024, 2025]
    for bad in ("2016", "2025-2027", "twenty", "2026-2025"):
        with pytest.raises(ConfigError):
            parse_season_request(bad, w)
