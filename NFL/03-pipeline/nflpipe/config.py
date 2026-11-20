"""Load and check the user's config files in ``02-config/`` (CONTRACTS.md section 1).

Loading is forgiving: a malformed value is recorded in ``Config.problems`` (and
replaced by a safe default) so the G-CONFIG gate can report every problem at once
and hold the run, instead of the pipeline stopping at the first typo. Only a
missing file or a missing required column raises ``ConfigError``.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_FILES = ("leagues.csv", "scoring_weights.csv", "bonus_rules.csv", "pipeline_config.csv")

KNOWN_SETTINGS = ("StartSeason", "EndSeason", "SeasonTypes", "RoundDecimals",
                  "PublishExtraColumns", "ReconcileTolerance")
SEASON_TYPE_CHOICES = {"REG": ("REG",), "POST": ("POST",), "REG+POST": ("REG", "POST")}
RECONCILE_CHOICES = ("", "fantasy_points", "fantasy_points_ppr")
WEIGHT_NON_LEAGUE_COLUMNS = ("Metric", "Category", "Description", "Notes", "Applies_To")
LEAGUE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
FIRST_NFLVERSE_SEASON = 1999


class ConfigError(Exception):
    """A config file is missing or unreadable; the run cannot start."""


@dataclass
class League:
    name: str
    description: str
    active: bool
    reconcile_to: str
    notes: str


@dataclass
class Weight:
    """One row of scoring_weights.csv: a metric and its weight in every league."""
    metric: str
    category: str
    description: str
    applies_to: str
    notes: str
    weights: dict[str, float]        # league -> weight (blank = 0)


@dataclass
class Band:
    """One row of bonus_rules.csv: award ``points`` when lower <= value <= upper."""
    league: str
    metric: str
    lower: float | None
    upper: float | None
    points: float
    applies_to: str
    notes: str


@dataclass
class Config:
    config_dir: Path
    settings: dict[str, str]
    leagues: list[League]
    weights: list[Weight]
    bands: list[Band]
    weight_league_columns: list[str]          # league columns found in scoring_weights.csv
    raw: dict[str, bytes]                     # file name -> exact bytes as read from 02-config
    problems: list[str] = field(default_factory=list)

    @property
    def normalized(self) -> dict[str, bytes]:
        """file name -> normalized bytes (CONTRACTS.md 5.4), published as 04-data/config/<name>."""
        return {name: normalize_csv(data) for name, data in self.raw.items()}

    # ---- convenient, already-validated views -------------------------------------------

    @property
    def active_leagues(self) -> list[League]:
        """Active leagues in leagues.csv order (each gets an FF_<League> column)."""
        return [lg for lg in self.leagues if lg.active]

    @property
    def control_leagues(self) -> list[League]:
        """Active leagues that reconcile to an nflverse fantasy-points column."""
        return [lg for lg in self.active_leagues if lg.reconcile_to]

    @property
    def season_types(self) -> tuple[str, ...]:
        return SEASON_TYPE_CHOICES.get(self.settings.get("SeasonTypes", "").strip().upper(), ("REG", "POST"))

    @property
    def season_types_text(self) -> str:
        return "+".join(self.season_types)

    @property
    def round_decimals(self) -> int:
        text = self.settings.get("RoundDecimals", "").strip()
        return int(text) if text.isdigit() and 0 <= int(text) <= 6 else 2

    @property
    def tolerance(self) -> float:
        value = _to_float(self.settings.get("ReconcileTolerance", ""))
        return value if value is not None and value >= 0 else 0.005

    @property
    def extra_columns_setting(self) -> str:
        """Raw PublishExtraColumns text: blank, a comma list, or ALL."""
        return self.settings.get("PublishExtraColumns", "").strip()

    @property
    def sha256(self) -> str:
        """One hash over the four normalized config files, used for status.csv config_sha256.

        Computed over the normalized copies (CONTRACTS.md 5.4), so re-saving a file from Excel
        (byte-order mark, CRLF, empty trailing columns and rows) without changing a value, or a
        Windows checkout with CRLF line endings, does not count as a config change.
        """
        digest = hashlib.sha256()
        normalized = self.normalized
        for name in CONFIG_FILES:
            digest.update(name.encode("utf-8") + b"\0" + normalized[name] + b"\0")
        return digest.hexdigest()

    def league_contract_hash(self, league: str) -> str:
        """SHA-256 of one league's rules, for status.csv contract_<League>.

        The hashed text is one line per non-zero weight, ``W|metric|weight|applies_to``,
        in scoring_weights.csv order, then one line per band of the league,
        ``B|metric|lower|upper|points|applies_to``, in bonus_rules.csv order; numbers use
        the published number format, gates are upper-cased without spaces; lines joined by
        ``\\n``. Notes and descriptions are not part of it.
        """
        from .publish import format_number  # local import: publish imports config
        lines = []
        for w in self.weights:
            value = w.weights.get(league, 0.0)
            if value:
                lines.append(f"W|{w.metric}|{format_number(value)}|{normalise_gate(w.applies_to)}")
        for b in self.bands:
            if b.league == league:
                lines.append("B|" + "|".join([b.metric, format_number(b.lower), format_number(b.upper),
                                              format_number(b.points), normalise_gate(b.applies_to)]))
        return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


# ---- helpers -------------------------------------------------------------------------------

def _to_float(text: str | None) -> float | None:
    """Parse a config number; blank or invalid gives None."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value if value == value and value not in (float("inf"), float("-inf")) else None


def normalize_csv(raw: bytes) -> bytes:
    """A config CSV in the published form (CONTRACTS.md 5.4).

    No byte-order mark, ``\n`` line endings, RFC 4180 minimal quoting, and the empty trailing
    columns and rows that Excel adds when it saves a CSV removed. Values are not touched.
    Text that is not UTF-8 is returned unchanged (loading reports it).
    """
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw
    rows = list(csv.reader(io.StringIO(text, newline="")))
    while rows and not any(cell.strip() for cell in rows[-1]):
        rows.pop()                                            # empty trailing rows (",,,," or blank)
    width = 0
    for row in rows:
        filled = [i for i, cell in enumerate(row) if cell.strip()]
        width = max(width, filled[-1] + 1 if filled else 0)
    rows = [row[:width] + [""] * (width - len(row)) for row in rows]
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\n", quoting=csv.QUOTE_MINIMAL).writerows(rows)
    return buffer.getvalue().encode("utf-8")


def normalise_gate(text: str | None) -> str:
    """Position gate text in canonical form: upper case, no spaces, e.g. 'DL,LB,DB'."""
    return ",".join(c for c in (text or "").upper().replace(" ", "").split(",") if c)


def _read_table(path: Path, required: tuple[str, ...]) -> tuple[bytes, list[str], list[dict[str, str]]]:
    """Read one config CSV: raw bytes, header and rows. Accepts a UTF-8 byte-order mark."""
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}")
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ConfigError(f"{path.name} is not UTF-8: {exc}") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    header = [h.strip() for h in (reader.fieldnames or [])]
    reader.fieldnames = header
    missing = [c for c in required if c not in header]
    if missing:
        raise ConfigError(f"{path.name} is missing column(s): {', '.join(missing)}")
    rows = [{k: (v or "").strip() if isinstance(v, str) else "" for k, v in r.items() if k is not None}
            for r in reader]
    rows = [r for r in rows if any(r.values())]          # ignore fully blank lines
    return raw, header, rows


# ---- loading -------------------------------------------------------------------------------

def load_config(config_dir: Path) -> Config:
    """Read the four config files. Raises ConfigError only when a file cannot be used at all."""
    config_dir = Path(config_dir)
    problems: list[str] = []
    raw: dict[str, bytes] = {}

    raw["pipeline_config.csv"], _, setting_rows = _read_table(
        config_dir / "pipeline_config.csv", ("Setting", "Value"))
    settings: dict[str, str] = {}
    for r in setting_rows:
        name = r["Setting"]
        if name in settings:
            problems.append(f"pipeline_config.csv: setting '{name}' appears more than once")
        settings[name] = r["Value"]

    raw["leagues.csv"], _, league_rows = _read_table(
        config_dir / "leagues.csv", ("League", "Description", "Active", "Reconcile_To", "Notes"))
    leagues = []
    for r in league_rows:
        active_text = r["Active"].strip().lower()
        if active_text not in ("yes", "no"):
            problems.append(f"leagues.csv: league '{r['League']}' has Active '{r['Active']}' (use Yes or No)")
        leagues.append(League(r["League"], r["Description"], active_text == "yes",
                              r["Reconcile_To"].strip(), r["Notes"]))

    raw["scoring_weights.csv"], weight_header, weight_rows = _read_table(
        config_dir / "scoring_weights.csv", ("Metric", "Applies_To"))
    league_columns = [h for h in weight_header if h and h not in WEIGHT_NON_LEAGUE_COLUMNS]
    weights = []
    for r in weight_rows:
        per_league = {}
        for lg in league_columns:
            text = r.get(lg, "")
            value = _to_float(text)
            if text and value is None:
                problems.append(f"scoring_weights.csv: metric '{r['Metric']}', league '{lg}': '{text}' is not a number")
            per_league[lg] = value or 0.0
        weights.append(Weight(r["Metric"], r.get("Category", ""), r.get("Description", ""),
                              r["Applies_To"], r.get("Notes", ""), per_league))

    raw["bonus_rules.csv"], _, band_rows = _read_table(
        config_dir / "bonus_rules.csv", ("League", "Metric", "Lower", "Upper", "Points", "Applies_To"))
    bands = []
    for i, r in enumerate(band_rows, start=2):
        lower, upper, points = _to_float(r["Lower"]), _to_float(r["Upper"]), _to_float(r["Points"])
        for col, text, value in (("Lower", r["Lower"], lower), ("Upper", r["Upper"], upper)):
            if text and value is None:
                problems.append(f"bonus_rules.csv line {i}: {col} '{text}' is not a number")
        if points is None:
            problems.append(f"bonus_rules.csv line {i}: Points '{r['Points']}' is not a number")
        bands.append(Band(r["League"], r["Metric"], lower, upper, points or 0.0, r["Applies_To"], r.get("Notes", "")))

    config = Config(config_dir, settings, leagues, weights, bands, league_columns, raw, problems)
    config.problems.extend(structural_problems(config))
    return config


def structural_problems(config: Config) -> list[str]:
    """Problems that do not need any nflverse data (the data-dependent checks are in gates.py)."""
    problems = []
    names = [lg.name for lg in config.leagues]
    for lg in config.leagues:
        if not LEAGUE_NAME.match(lg.name):
            problems.append(f"leagues.csv: '{lg.name}' is not a valid league name (letters, digits, underscore; starts with a letter)")
        if lg.name not in config.weight_league_columns:
            problems.append(f"scoring_weights.csv has no weights column for league '{lg.name}'")
        if lg.reconcile_to not in RECONCILE_CHOICES:
            problems.append(f"leagues.csv: league '{lg.name}' has Reconcile_To '{lg.reconcile_to}' "
                            "(use fantasy_points, fantasy_points_ppr or blank)")
    if len(set(names)) != len(names):
        problems.append("leagues.csv: a league name appears more than once")
    for col in config.weight_league_columns:
        if col not in names:
            problems.append(f"scoring_weights.csv column '{col}' is not a league in leagues.csv")
    if not config.active_leagues:
        problems.append("leagues.csv: no league is Active")

    metrics = [w.metric for w in config.weights]
    for m in sorted({m for m in metrics if metrics.count(m) > 1}):
        problems.append(f"scoring_weights.csv: metric '{m}' appears more than once")
    if "" in metrics:
        problems.append("scoring_weights.csv: a row has a blank Metric")

    for i, b in enumerate(config.bands, start=2):
        if b.league not in names:
            problems.append(f"bonus_rules.csv line {i}: league '{b.league}' is not in leagues.csv")
        if not b.metric:
            problems.append(f"bonus_rules.csv line {i}: blank Metric")
        if b.lower is not None and b.upper is not None and b.lower > b.upper:
            problems.append(f"bonus_rules.csv line {i}: Lower {b.lower} is greater than Upper {b.upper}")

    for name in config.settings:
        if name not in KNOWN_SETTINGS:
            problems.append(f"pipeline_config.csv: unknown setting '{name}'")
    for name in KNOWN_SETTINGS:
        if name not in config.settings:
            problems.append(f"pipeline_config.csv: setting '{name}' is missing")
    for name in ("StartSeason", "EndSeason"):
        try:
            parse_season_spec(config.settings.get(name, ""))
        except ValueError as exc:
            problems.append(f"pipeline_config.csv: {name}: {exc}")
    if config.settings.get("SeasonTypes", "").strip().upper() not in SEASON_TYPE_CHOICES:
        problems.append("pipeline_config.csv: SeasonTypes must be REG, POST or REG+POST")
    text = config.settings.get("RoundDecimals", "").strip()
    if not (text.isdigit() and 0 <= int(text) <= 6):
        problems.append("pipeline_config.csv: RoundDecimals must be a whole number from 0 to 6")
    tol = _to_float(config.settings.get("ReconcileTolerance", ""))
    if tol is None or tol < 0:
        problems.append("pipeline_config.csv: ReconcileTolerance must be 0 or a small positive number")
    return problems


# ---- season window -----------------------------------------------------------------------

def parse_season_spec(text: str) -> tuple[str, int]:
    """Parse StartSeason / EndSeason: a year, 'Latest' or 'Latest-N' (same rules as Stats_Raw.pq).

    Returns ('year', 2017) or ('latest', N). Spaces are ignored, case does not matter.
    """
    u = (text or "").replace(" ", "").replace(" ", "").upper()
    if u == "LATEST":
        return ("latest", 0)
    if u.startswith("LATEST-"):
        n = u[len("LATEST-"):]
        if n.isdigit() and int(n) <= 30:
            return ("latest", int(n))
    elif u.isdigit():
        if int(u) < FIRST_NFLVERSE_SEASON:
            raise ValueError(f"{u} is before {FIRST_NFLVERSE_SEASON}, when nflverse weekly stats start")
        return ("year", int(u))
    raise ValueError(f"must be a year such as 2017, Latest, or Latest-N with N from 0 to 30 (found: '{text}')")


def resolve_window(config: Config, latest_season: int) -> tuple[int, int]:
    """Turn StartSeason / EndSeason into concrete years, given the newest published season.

    An EndSeason after the newest published season is clamped to it (G-WINDOW names the
    unpublished seasons); ``requested_end`` gives the year as written.
    """
    start, end = _resolve_spec(config, "StartSeason", latest_season), requested_end(config, latest_season)
    if start < FIRST_NFLVERSE_SEASON:
        raise ConfigError(f"StartSeason resolves to {start}, before {FIRST_NFLVERSE_SEASON}")
    if start > latest_season:
        raise ConfigError(f"StartSeason {start} is after the newest season nflverse has published "
                          f"({latest_season}), so there is nothing to build yet; set StartSeason in "
                          "pipeline_config.csv to a published year or to Latest-N")
    end = min(end, latest_season)
    if start > end:
        raise ConfigError(f"StartSeason ({start}) is after EndSeason ({end})")
    return start, end


def _resolve_spec(config: Config, name: str, latest_season: int) -> int:
    kind, n = parse_season_spec(config.settings.get(name, ""))
    return n if kind == "year" else latest_season - n


def requested_end(config: Config, latest_season: int) -> int:
    """EndSeason as written (a year may be after the newest published season)."""
    return _resolve_spec(config, "EndSeason", latest_season)
