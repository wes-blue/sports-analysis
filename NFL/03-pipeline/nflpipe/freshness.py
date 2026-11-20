"""Freshness helpers shared by ``resolve`` and ``watchdog`` (C1 Actions Engineer).

Standard library only. Deliberately independent of the pipeline core (B1's
``http.py`` and ``publish.py``) so the scheduling side can be tested and run
on its own.

What lives here:
- the schedule model: which NFL week has *finished* (kickoff + 6 h settle rule,
  regular season and playoffs), read from nflverse ``schedules/games.csv``;
- the upstream probe: the HTTP ``Last-Modified`` of an nflverse release file;
- readers for the published run files ``status.csv``, ``sources.csv`` and
  ``run_log.csv`` (CONTRACTS.md section 5.4).

Probe behaviour, measured from the build container on 2026-11-19:
``https://github.com/nflverse/nflverse-data/releases/download/...`` answers
``302 Found`` (no ``Last-Modified``) and redirects to a short-lived signed URL
on ``release-assets.githubusercontent.com``. That host returns
``Last-Modified``, ``ETag`` and ``Content-Length`` both to ``HEAD`` (200) and to
a ranged ``GET`` with ``Range: bytes=0-0`` (206, one byte). ``urllib`` keeps the
``HEAD`` method across the redirect. A missing season file answers 404. So the
probe sends ``HEAD`` and falls back to a one-byte ranged ``GET`` when ``HEAD``
is refused or carries no ``Last-Modified``.

Upstream content is untrusted data: it is parsed as CSV, never executed.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from typing import Callable, Iterable

BASE_URL = "https://github.com/nflverse/nflverse-data/releases/download/"
SCHEDULE_PATH = "schedules/games.csv"
USER_AGENT = "nflpipe-freshness/1 (+python-urllib)"

#: Hours after kickoff at which a game counts as settled (prior-art ADOPT 3).
SETTLE_HOURS = 6
#: Days after a season's last game during which the season still counts as "in season".
SEASON_TAIL_DAYS = 21

POST_GAME_TYPES = ("WC", "DIV", "CON", "SB")
GAME_TYPES = ("REG",) + POST_GAME_TYPES

UTC = dt.timezone.utc


class FreshnessError(RuntimeError):
    """Any failure that must stop a decision (callers exit 1: fail closed)."""


class UpstreamMissing(FreshnessError):
    """The upstream file does not exist (HTTP 404)."""


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def utc_now() -> dt.datetime:
    return dt.datetime.now(UTC).replace(microsecond=0)


def iso_utc(value: dt.datetime | None) -> str:
    """ISO 8601 UTC with a trailing ``Z``; blank for ``None``."""
    if value is None:
        return ""
    return value.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(text: str | None) -> dt.datetime | None:
    """Parse ISO 8601 (``Z``, offset, or naive meaning UTC) or an HTTP date.

    Returns ``None`` for blank input; raises ``ValueError`` on anything else
    that cannot be parsed.
    """
    if text is None:
        return None
    s = text.strip()
    if not s:
        return None
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    try:
        value = dt.datetime.fromisoformat(s)
    except ValueError:
        try:
            value = parsedate_to_datetime(text.strip())
        except (TypeError, ValueError, IndexError) as exc:
            raise ValueError(f"not a date/time: {text!r}") from exc
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _nth_sunday(year: int, month: int, n: int) -> dt.date:
    first = dt.date(year, month, 1)
    offset = (6 - first.weekday()) % 7  # weekday(): Monday=0 .. Sunday=6
    return first + dt.timedelta(days=offset + 7 * (n - 1))


def eastern_to_utc(day: dt.date, hhmm: str) -> dt.datetime:
    """Convert a US Eastern wall-clock time (nflverse ``gametime``) to UTC.

    Uses the US rule in force since 2007 (DST from 02:00 on the second Sunday
    of March to 02:00 on the first Sunday of November), so no ``tzdata``
    package is needed on any operating system.
    """
    hh, mm = (int(p) for p in hhmm.split(":")[:2])
    local = dt.datetime(day.year, day.month, day.day, hh, mm)
    dst_start = dt.datetime.combine(_nth_sunday(day.year, 3, 2), dt.time(2, 0))
    dst_end = dt.datetime.combine(_nth_sunday(day.year, 11, 1), dt.time(2, 0))
    offset_hours = 4 if dst_start <= local < dst_end else 5
    return (local + dt.timedelta(hours=offset_hours)).replace(tzinfo=UTC)


# ---------------------------------------------------------------------------
# Schedule model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Game:
    game_id: str
    season: int
    game_type: str
    week: int
    kickoff_utc: dt.datetime
    has_score: bool

    @property
    def season_type(self) -> str:
        return "REG" if self.game_type == "REG" else "POST"

    @property
    def settle_utc(self) -> dt.datetime:
        return self.kickoff_utc + dt.timedelta(hours=SETTLE_HOURS)


@dataclass(frozen=True)
class Week:
    season: int
    week: int
    season_type: str
    game_types: tuple[str, ...]
    games: int
    scored_games: int
    first_kickoff_utc: dt.datetime
    settle_utc: dt.datetime  # last kickoff + SETTLE_HOURS

    def label(self) -> str:
        return week_label(self.season, self.week, self.season_type)


def week_label(season: int | None, week: int | None, season_type: str | None) -> str:
    if season is None or week is None:
        return ""
    return f"{season}-W{int(week):02d}-{season_type or 'REG'}"


def parse_schedule(text: str) -> list[Game]:
    """Parse nflverse ``games.csv`` text into games (regular season and playoffs)."""
    reader = csv.DictReader(io.StringIO(text))
    needed = {"game_id", "season", "game_type", "week", "gameday", "gametime", "home_score", "away_score"}
    missing = needed - set(reader.fieldnames or [])
    if missing:
        raise FreshnessError(f"schedule is missing columns: {', '.join(sorted(missing))}")
    games: list[Game] = []
    for line_no, row in enumerate(reader, start=2):
        game_type = (row.get("game_type") or "").strip().upper()
        if game_type not in GAME_TYPES:
            continue
        try:
            season = int(row["season"])
            week = int(row["week"])
            day = dt.date.fromisoformat(row["gameday"].strip())
        except (TypeError, ValueError) as exc:
            raise FreshnessError(f"schedule line {line_no}: bad season/week/gameday ({exc})") from exc
        gametime = (row.get("gametime") or "").strip()
        try:
            # A blank kickoff time is treated as late evening, the conservative choice.
            kickoff = eastern_to_utc(day, gametime or "23:59")
        except ValueError as exc:
            raise FreshnessError(f"schedule line {line_no}: bad gametime {gametime!r}") from exc
        has_score = bool((row.get("home_score") or "").strip()) and bool((row.get("away_score") or "").strip())
        games.append(Game(row["game_id"], season, game_type, week, kickoff, has_score))
    if not games:
        raise FreshnessError("schedule has no games")
    return games


def weeks_of(games: Iterable[Game], season: int) -> list[Week]:
    groups: dict[int, list[Game]] = {}
    for g in games:
        if g.season == season:
            groups.setdefault(g.week, []).append(g)
    weeks = []
    for wk in sorted(groups):
        gs = groups[wk]
        types = tuple(sorted({g.game_type for g in gs}))
        weeks.append(Week(
            season=season,
            week=wk,
            season_type="REG" if types == ("REG",) else "POST",
            game_types=types,
            games=len(gs),
            scored_games=sum(g.has_score for g in gs),
            first_kickoff_utc=min(g.kickoff_utc for g in gs),
            settle_utc=max(g.settle_utc for g in gs),
        ))
    return weeks


@dataclass
class SeasonState:
    """Where the NFL calendar stands at ``now``."""

    season: int                      # the season whose first game has kicked off most recently
    weeks: list[Week]
    latest_finished: Week | None     # highest week whose every game has settled
    season_complete: bool            # the Super Bowl has settled
    last_settle_utc: dt.datetime     # settle time of the last scheduled game of the season
    next_season_start_utc: dt.datetime | None = None
    notes: list[str] = field(default_factory=list)

    def in_season(self, now: dt.datetime) -> bool:
        """True from the first settled game until SEASON_TAIL_DAYS after the season's last game."""
        if self.latest_finished is None:
            return False
        if self.season_complete:
            return now <= self.last_settle_utc + dt.timedelta(days=SEASON_TAIL_DAYS)
        return True


def season_state(games: list[Game], now: dt.datetime) -> SeasonState:
    starts: dict[int, dt.datetime] = {}
    for g in games:
        if g.season not in starts or g.kickoff_utc < starts[g.season]:
            starts[g.season] = g.kickoff_utc
    started = [s for s, t in starts.items() if t <= now]
    if not started:
        raise FreshnessError("no season in the schedule has started yet")
    season = max(started)
    later = [t for s, t in starts.items() if s > season]
    weeks = weeks_of(games, season)
    finished = [w for w in weeks if w.settle_utc <= now]
    latest = max(finished, key=lambda w: w.week) if finished else None
    sb = [w for w in weeks if "SB" in w.game_types]
    complete = bool(sb) and sb[-1].settle_utc <= now
    return SeasonState(
        season=season,
        weeks=weeks,
        latest_finished=latest,
        season_complete=complete,
        last_settle_utc=max(w.settle_utc for w in weeks),
        next_season_start_utc=min(later) if later else None,
    )


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

Opener = Callable[[urllib.request.Request, float], "object"]


def _default_open(req: urllib.request.Request, timeout: float):
    return urllib.request.urlopen(req, timeout=timeout)  # noqa: S310 - fixed https base


def _with_retries(fn, what: str, attempts: int = 3, pause: float = 2.0):
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise UpstreamMissing(f"{what}: HTTP 404 (not published upstream)") from exc
            if exc.code < 500 and exc.code not in (408, 429):
                raise FreshnessError(f"{what}: HTTP {exc.code}") from exc
            last = exc
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            last = exc
        if i + 1 < attempts:
            time.sleep(pause * (i + 1))
    raise FreshnessError(f"{what}: failed after {attempts} attempts ({last})")


@dataclass(frozen=True)
class Probe:
    url: str
    last_modified: dt.datetime
    size_bytes: int | None
    etag: str
    method: str  # "HEAD" or "GET-range"


def probe_last_modified(url: str, *, opener: Opener = _default_open, timeout: float = 30.0) -> Probe:
    """Return the upstream ``Last-Modified`` of ``url`` (following redirects).

    Raises ``UpstreamMissing`` on 404 and ``FreshnessError`` on any other failure,
    including a response without a parseable ``Last-Modified``.
    """

    def attempt(method: str):
        headers = {"User-Agent": USER_AGENT}
        if method == "GET-range":
            headers["Range"] = "bytes=0-0"
        req = urllib.request.Request(url, method="HEAD" if method == "HEAD" else "GET", headers=headers)
        resp = opener(req, timeout)
        try:
            hdrs = resp.headers
            lm = hdrs.get("Last-Modified")
            size = None
            content_range = hdrs.get("Content-Range") or ""
            if "/" in content_range and content_range.rsplit("/", 1)[1].strip().isdigit():
                size = int(content_range.rsplit("/", 1)[1])
            elif method == "HEAD" and (hdrs.get("Content-Length") or "").isdigit():
                size = int(hdrs["Content-Length"])
            if method != "HEAD":
                resp.read(1024)
            return lm, size, hdrs.get("ETag") or ""
        finally:
            close = getattr(resp, "close", None)
            if close:
                close()

    lm = None
    size = None
    etag = ""
    used = "HEAD"
    try:
        lm, size, etag = _with_retries(lambda: attempt("HEAD"), f"HEAD {url}")
    except UpstreamMissing:
        raise
    except FreshnessError:
        lm = None  # HEAD refused or failing: try the ranged GET below
    if not lm:
        used = "GET-range"
        lm, size, etag = _with_retries(lambda: attempt("GET-range"), f"ranged GET {url}")
    if not lm:
        raise FreshnessError(f"{url}: no Last-Modified header from HEAD or ranged GET")
    try:
        when = parse_utc(lm)
    except ValueError as exc:
        raise FreshnessError(f"{url}: unparseable Last-Modified {lm!r}") from exc
    assert when is not None
    return Probe(url=url, last_modified=when, size_bytes=size, etag=etag, method=used)


def fetch_text(url: str, *, opener: Opener = _default_open, timeout: float = 60.0) -> str:
    def attempt():
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        resp = opener(req, timeout)
        try:
            return resp.read()
        finally:
            close = getattr(resp, "close", None)
            if close:
                close()

    raw = _with_retries(attempt, f"GET {url}")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FreshnessError(f"{url}: not UTF-8 text") from exc


def upstream_url(kind: str, season: int | None = None) -> str:
    if kind == "schedules":
        return BASE_URL + SCHEDULE_PATH
    if kind == "stats_player":
        return f"{BASE_URL}stats_player/stats_player_week_{season}.csv"
    if kind == "stats_team":
        return f"{BASE_URL}stats_team/stats_team_week_{season}.csv"
    raise ValueError(f"unknown kind {kind!r}")


def load_schedule(schedule_file: str | None, *, opener: Opener = _default_open) -> list[Game]:
    if schedule_file:
        try:
            with open(schedule_file, encoding="utf-8-sig", newline="") as fh:
                return parse_schedule(fh.read())
        except OSError as exc:
            raise FreshnessError(f"cannot read schedule file {schedule_file}: {exc}") from exc
    return parse_schedule(fetch_text(upstream_url("schedules"), opener=opener))


# ---------------------------------------------------------------------------
# Published state (04-data)
# ---------------------------------------------------------------------------

@dataclass
class Published:
    """What ``--data-dir`` says has been published."""

    exists: bool = False                 # data dir exists and holds at least one file
    status: dict[str, str] = field(default_factory=dict)
    sources: list[dict[str, str]] = field(default_factory=list)
    run_log: list[dict[str, str]] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def first_run(self) -> bool:
        return not self.exists or (not self.status and not self.sources and not self.run_log)

    def through(self) -> tuple[int, int, str] | None:
        """(season, week, season_type) of the newest published week, from status.csv."""
        try:
            season = int(self.status.get("latest_season", ""))
            week = int(self.status.get("latest_week", ""))
        except ValueError:
            return None
        return season, week, (self.status.get("latest_season_type") or "REG").upper()

    def recorded_last_modified(self, kind: str, season: int | None) -> dt.datetime | None:
        """Newest ``last_modified`` recorded in sources.csv for (kind, season)."""
        best = None
        for row in self.sources:
            if (row.get("kind") or "").strip() != kind:
                continue
            row_season = (row.get("season") or "").strip()
            if season is not None and row_season != str(season):
                continue
            try:
                when = parse_utc(row.get("last_modified"))
            except ValueError:
                self.problems.append(f"sources.csv: bad last_modified {row.get('last_modified')!r}")
                continue
            if when and (best is None or when > best):
                best = when
        return best

    def last_publish_utc(self) -> dt.datetime | None:
        """Newest PUBLISH time from status.csv (``generated_utc``) and run_log.csv (``finished_utc``)."""
        candidates: list[dt.datetime] = []
        if (self.status.get("outcome") or "PUBLISH").upper() == "PUBLISH":
            try:
                when = parse_utc(self.status.get("generated_utc"))
                if when:
                    candidates.append(when)
            except ValueError:
                self.problems.append("status.csv: bad generated_utc")
        for row in self.run_log:
            if (row.get("outcome") or "").strip().upper() != "PUBLISH":
                continue
            try:
                when = parse_utc(row.get("finished_utc") or row.get("started_utc"))
            except ValueError:
                self.problems.append("run_log.csv: bad finished_utc")
                continue
            if when:
                candidates.append(when)
        return max(candidates) if candidates else None


REQUIRED_COLUMNS = {
    "status.csv": {"key", "value"},
    "sources.csv": {"season", "kind", "last_modified"},
    "run_log.csv": {"finished_utc", "outcome"},
}


def _read_csv(path: str) -> tuple[list[str], list[dict[str, str]]]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def read_published(data_dir: str) -> Published:
    """Read status.csv, sources.csv and run_log.csv. Never raises for a missing or broken file;
    problems are listed so callers can decide (resolve treats them as "run", B5 fail-open)."""
    pub = Published()
    if not os.path.isdir(data_dir):
        return pub
    try:
        pub.exists = any(True for _ in os.scandir(data_dir))
    except OSError as exc:
        pub.problems.append(f"cannot list {data_dir}: {exc}")
        return pub
    for name, attr in (("status.csv", "status"), ("sources.csv", "sources"), ("run_log.csv", "run_log")):
        path = os.path.join(data_dir, name)
        if not os.path.exists(path):
            continue
        try:
            columns, rows = _read_csv(path)
        except (OSError, UnicodeDecodeError, csv.Error) as exc:
            pub.problems.append(f"{name}: unreadable ({exc})")
            continue
        missing = REQUIRED_COLUMNS[name] - set(columns)
        if columns and missing:
            pub.problems.append(f"{name}: missing columns {', '.join(sorted(missing))}")
            continue
        if attr == "status":
            pub.status = {(r.get("key") or "").strip(): (r.get("value") or "").strip() for r in rows}
        else:
            setattr(pub, attr, rows)
    return pub


def season_type_rank(season_type: str) -> int:
    return 1 if (season_type or "").upper() == "POST" else 0


def week_key(season: int, week: int, season_type: str) -> tuple[int, int, int]:
    """Sortable key; nflverse numbers playoff weeks 19-22 so week order already works,
    the season-type rank only breaks ties."""
    return season, int(week), season_type_rank(season_type)


def write_outputs(pairs: list[tuple[str, str]], stream=None) -> None:
    """Print ``key=value`` lines and append them to ``$GITHUB_OUTPUT`` when it is set."""
    import sys

    out = stream or sys.stdout
    clean = [(k, " ".join(str(v).split())) for k, v in pairs]  # no newlines can reach GITHUB_OUTPUT
    for k, v in clean:
        print(f"{k}={v}", file=out)
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a", encoding="utf-8") as fh:
            for k, v in clean:
                fh.write(f"{k}={v}\n")
