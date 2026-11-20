"""Write the published CSV files deterministically and move them into ``04-data/``.

Rules from CONTRACTS.md section 5: UTF-8 without BOM, ``\\n`` line endings, RFC 4180
quoting, blank = null, whole numbers without a decimal point, other numbers in the
shortest text that round-trips, rows sorted by season, week, season_type, player_id.

Every file is first written to a staging folder that holds the complete candidate
``04-data``. Only after the gates pass does ``sync`` copy the files whose bytes changed
into the real folder, so a HOLD or an error leaves ``04-data`` exactly as it was. ``sync``
itself is all or nothing: it proves every target writable first and restores a backup if a
replace fails part-way (QA finding M-03).
"""

from __future__ import annotations

import csv
import hashlib
import io
import os
import shutil
from pathlib import Path

# Files that change without the data changing: time stamps and run ids, and sources.csv,
# whose upstream Last-Modified / SHA-256 move whenever nflverse re-uploads a file (games.csv
# several times a day, finished seasons' play-by-play about weekly, often with re-gzipped but
# identical rows). They are rewritten on a PUBLISH but never decide on their own that a run
# has something to publish, so an unchanged week ends in SKIP and makes no empty commit.
VOLATILE_FILES = {"status.csv", "run_log.csv", "manifest.csv", "checks/gates.csv", "sources.csv"}

# Season files the pipeline owns; a file matching these that is no longer produced
# (a season that left the window) is removed from 04-data on publish.
SEASON_FOLDERS = {"player_week": "player_week_", "scored": "scored_", "long_td": "long_td_"}


# ---- values and CSV text -----------------------------------------------------------------

def format_number(value) -> str:
    """Published number text: '' for None, '12' for 12.0, '0.04' for 0.04, '0' for -0.0."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if value == 0:
        return "0"
    if value.is_integer() and abs(value) < 1e15:
        return str(int(value))
    return repr(float(value))


def format_cell(value) -> str:
    """Text cells pass through; numbers use format_number."""
    if isinstance(value, str):
        return value
    return format_number(value)


def csv_bytes(header: list[str], rows) -> bytes:
    """Encode a table as published CSV bytes (header first)."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(header)
    for row in rows:
        writer.writerow([format_cell(v) for v in row])
    return buffer.getvalue().encode("utf-8")


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read a published CSV as text dicts; a missing file gives []."""
    if not Path(path).is_file():
        return []
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def row_sort_key(row: dict) -> tuple:
    """Contract order: season, week (numeric), season_type, player_id."""
    return (int(row["season"]), int(row["week"]), str(row["season_type"]), str(row["player_id"]))


class Stage:
    """The staging folder: a complete candidate 04-data built by this run."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def path(self, relative: str) -> Path:
        return self.root / relative

    def write(self, relative: str, data: bytes) -> Path:
        target = self.path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target

    def write_table(self, relative: str, header: list[str], rows) -> Path:
        return self.write(relative, csv_bytes(header, rows))

    def copy_in(self, source: Path, relative: str) -> None:
        """Copy a published file into the stage, with CRLF line endings (a Windows checkout)
        turned back into the published ``\n``."""
        target = self.path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(lf_bytes(Path(source).read_bytes()))

    def files(self) -> list[str]:
        """Every staged file, relative with '/' separators, sorted."""
        return sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file())


# ---- season files ------------------------------------------------------------------------

def season_file(kind: str, season: int) -> str:
    """Relative path of a season file, e.g. ('scored', 2026) -> 'scored/scored_2026.csv'."""
    return f"{kind}/{SEASON_FOLDERS[kind]}{season}.csv"


def player_week_header(metrics: list[str]) -> list[str]:
    from .ingest import ID_COLUMNS, REFERENCE_COLUMNS
    return ID_COLUMNS + metrics + REFERENCE_COLUMNS


SCORED_ID_COLUMNS = ["season", "week", "season_type", "player_id", "player_display_name", "position", "team",
                     "fantasy_points", "fantasy_points_ppr"]
LONG_TD_HEADER = ["season", "week", "season_type", "player_id",
                  "pass_td_40", "pass_td_50", "rush_td_40", "rush_td_50", "rec_td_40", "rec_td_50"]


# ---- comparing and syncing -----------------------------------------------------------------

# Written last, in this order, so a reader (or an interrupted run) never sees a new index that
# points at old data: manifest.csv is the very last file replaced.
INDEX_LAST = ["seasons.csv", "sources.csv", "dictionary.csv", "run_log.csv", "status.csv", "manifest.csv"]
TEMP_SUFFIX = ".nflpipe-tmp"


class PublishError(Exception):
    """Publishing could not complete; 04-data was left (or put back) exactly as it was."""


def lf_bytes(data: bytes) -> bytes:
    """Bytes with Windows line endings (CRLF) turned into ``\n``.

    Published files never contain a carriage return, but a Git for Windows checkout with
    ``core.autocrlf=true`` adds one to every line. Comparing through this function lets such a
    checkout count as unchanged instead of forcing a rewrite or a manifest failure.
    """
    return data.replace(b"\r\n", b"\n")


def same_content(published: Path, staged: Path) -> bool:
    """True when two files hold the same published content (CRLF in ``published`` tolerated)."""
    published, staged = Path(published), Path(staged)
    if not published.is_file():
        return False
    if published.stat().st_size == staged.stat().st_size and published.read_bytes() == staged.read_bytes():
        return True
    return lf_bytes(published.read_bytes()) == staged.read_bytes()


def changed_files(stage: Stage, data_dir: Path, include_volatile: bool, exact: bool = False) -> list[str]:
    """Staged files whose content differs from 04-data (new files count as changed).

    With ``exact`` the bytes must be identical (used by ``sync``, so a CRLF copy is rewritten
    with ``\n`` whenever a publish happens); otherwise a CRLF-only difference counts as unchanged.
    """
    changed = []
    for relative in stage.files():
        if not include_volatile and relative in VOLATILE_FILES:
            continue
        published = Path(data_dir) / relative
        staged = stage.path(relative)
        if exact:
            differs = not published.is_file() or published.stat().st_size != staged.stat().st_size \
                or published.read_bytes() != staged.read_bytes()
        else:
            differs = not same_content(published, staged)
        if differs:
            changed.append(relative)
    return changed


def obsolete_files(stage: Stage, data_dir: Path) -> list[str]:
    """Published season files the run no longer produces (seasons outside the window)."""
    staged = set(stage.files())
    obsolete = []
    for folder, prefix in SEASON_FOLDERS.items():
        directory = Path(data_dir) / folder
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob(f"{prefix}*.csv")):
            relative = f"{folder}/{path.name}"
            if relative not in staged:
                obsolete.append(relative)
    return obsolete


def publish_order(files: list[str]) -> list[str]:
    """Data files first (sorted), then the index files in INDEX_LAST order."""
    rank = {name: i for i, name in enumerate(INDEX_LAST)}
    return sorted(files, key=lambda f: (rank.get(f, -1), f))


def ensure_writable(path: Path) -> None:
    """Prove an existing file can be replaced, by opening it for writing without changing it.

    On Windows a CSV that is open in Excel is locked: this open fails with PermissionError, as
    the later replace would. Raises PublishError naming the file.
    """
    try:
        with open(path, "r+b"):
            pass
    except OSError as exc:
        raise PublishError(locked_message(path, exc)) from exc


def locked_message(path: Path, exc: BaseException) -> str:
    return (f"cannot write {path}: it is open in another program (probably Excel) or read-only "
            f"({type(exc).__name__}: {exc}). Close that file and run the same command again. "
            "Nothing in the data folder was changed.")


def _remove_quietly(path: Path) -> None:
    try:
        Path(path).unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def sync(stage: Stage, data_dir: Path, backup_dir: Path | None = None) -> tuple[list[str], list[str]]:
    """Copy changed staged files into 04-data and remove obsolete season files, all or nothing.

    1. Every target that will be replaced or removed is opened for writing first; a locked file
       (a CSV open in Excel on Windows) stops the publish before anything changes.
    2. Every new file is written next to its target as ``<name>.nflpipe-tmp``.
    3. Each existing target is copied to ``backup_dir``; then the files are moved into place with
       ``os.replace`` (data files first, index files last, ``manifest.csv`` last of all) and the
       obsolete season files are removed.
    4. If any step fails, every file already replaced or removed is restored from the backup,
       new files are deleted and the temporary files are cleaned up, then PublishError is raised.

    Returns (written, removed).
    """
    data_dir = Path(data_dir)
    backup_dir = Path(backup_dir) if backup_dir is not None else data_dir.parent / ".nflpipe-backup"
    for leftover in data_dir.rglob(f"*{TEMP_SUFFIX}") if data_dir.is_dir() else []:
        _remove_quietly(leftover)                     # from an interrupted run of an older version
    written = publish_order(changed_files(stage, data_dir, include_volatile=True, exact=True))
    removed = obsolete_files(stage, data_dir)
    if not written and not removed:
        return written, removed

    for relative in written + removed:                # step 1: prove every target is writable
        target = data_dir / relative
        if target.exists():
            ensure_writable(target)

    temporaries: list[Path] = []
    try:                                              # step 2: write every new file beside its target
        for relative in written:
            target = data_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + TEMP_SUFFIX)
            temporaries.append(temporary)
            shutil.copyfile(stage.path(relative), temporary)
    except OSError as exc:
        for temporary in temporaries:
            _remove_quietly(temporary)
        raise PublishError(f"cannot write into {data_dir} ({type(exc).__name__}: {exc}); "
                           "nothing in the data folder was changed") from exc

    if backup_dir.exists():                           # step 3: back up, then replace
        shutil.rmtree(backup_dir)
    backup_dir.mkdir(parents=True)
    backed_up: dict[str, Path] = {}
    done: list[tuple[str, str]] = []                  # (action, relative) in the order applied
    current = ""
    try:
        for relative in written + removed:
            target = data_dir / relative
            if target.exists():
                copy = backup_dir / relative
                copy.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(target, copy)
                backed_up[relative] = copy
        for relative in written:
            current = relative
            target = data_dir / relative
            os.replace(target.with_name(target.name + TEMP_SUFFIX), target)
            done.append(("write", relative))
        for relative in removed:
            current = relative
            (data_dir / relative).unlink()
            done.append(("remove", relative))
    except OSError as exc:
        problems = _roll_back(data_dir, done, backed_up)
        for temporary in temporaries:
            _remove_quietly(temporary)
        if problems:
            # The restore itself failed (for example a second file is locked): do NOT claim nothing changed.
            where = f"{data_dir / current}" if current else "the data folder"
            message = (f"cannot write {where} ({type(exc).__name__}: {exc}), and restoring the old files also "
                       "failed for " + ", ".join(problems) + ". Some files in the data folder are new and some "
                       "are old. Close any 04-data file that is open in Excel, then run the pipeline again with "
                       "`--seasons all` (on Windows: `py -m nflpipe run --seasons all`), which repairs the folder; "
                       "or restore 04-data from git (`git checkout -- 04-data`). Copies of the old files are in "
                       f"{backup_dir} until the next run.")
        else:
            message = locked_message(data_dir / current, exc) if current else \
                f"cannot back up the data folder ({type(exc).__name__}: {exc}); nothing was changed"
            shutil.rmtree(backup_dir, ignore_errors=True)
        raise PublishError(message) from exc
    shutil.rmtree(backup_dir, ignore_errors=True)
    return written, removed


def _roll_back(data_dir: Path, done: list[tuple[str, str]], backed_up: dict[str, Path]) -> list[str]:
    """Undo the replaces and removals already applied. Returns the files that could not be restored."""
    problems = []
    for action, relative in reversed(done):
        target = data_dir / relative
        try:
            if relative in backed_up:
                temporary = target.with_name(target.name + TEMP_SUFFIX)
                shutil.copyfile(backed_up[relative], temporary)
                os.replace(temporary, target)
            elif action == "write":
                target.unlink()                       # a file this publish created
        except OSError:
            problems.append(relative)
    return problems
