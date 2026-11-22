"""Contract test for the GitHub Actions workflow files (CONTRACTS.md section 8).

Parses every NFL workflow in ``/.github/workflows/`` and asserts the scheduling, safety and
publishing rules, then executes the workflows' own shell steps against stand-ins (a fake ``gh``,
a fake ``python`` where the real pipeline is not the point, and throwaway git remotes), so the
behaviour that cannot be run here on GitHub is still exercised. Needs PyYAML (test-only).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

PIPELINE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = PIPELINE_DIR.parents[1]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
GUIDE = PIPELINE_DIR / "AUTOMATION.md"
WORKDIR = "NFL/03-pipeline"
DATA_PATH = "NFL/04-data"
PUBLISH_GROUP = "nfl-pipeline-publish"
SEASON_MONTHS = "1,2,9-12"
ALLOWED_JOB_PERMISSIONS = {"contents": {"read", "write"}, "issues": {"write"}}
ALLOWED_EVENTS = {"schedule", "push", "pull_request", "workflow_dispatch"}
# Each file has exactly the events it needs: a pull request must never reach a publishing workflow (A2-13 #23).
EVENTS = {
    "nfl-pipeline-weekly.yml": {"schedule", "push", "workflow_dispatch"},
    "nfl-pipeline-monthly.yml": {"schedule", "workflow_dispatch"},
    "nfl-pipeline-watchdog.yml": {"schedule", "workflow_dispatch"},
    "nfl-pipeline-ci.yml": {"push", "pull_request", "workflow_dispatch"},
}
JOB_TIMEOUT = {"nfl-pipeline-weekly.yml": 45, "nfl-pipeline-monthly.yml": 90}
WB_TAG = "nfl-workbook"
WB_ASSET = "NFL-Analysis.xlsx"
WB_URL = f"https://github.com/wes-blue/sports-analysis/releases/download/{WB_TAG}/{WB_ASSET}"
PG_ASSET = "NFL-PlayerGames.csv"
ST_ASSET = "NFL-SeasonTotals.csv"
RF_ASSET = "NFL-Analysis-Refresh.xlsx"
ALL_ASSETS = [WB_ASSET, PG_ASSET, ST_ASSET, RF_ASSET]
NEXT_NAMES = ["NFL-Analysis.next.xlsx", "NFL-PlayerGames.next.csv", "NFL-SeasonTotals.next.csv", "NFL-Analysis-Refresh.next.xlsx"]
DL_BASE = f"https://github.com/wes-blue/sports-analysis/releases/download/{WB_TAG}"
DECIDE = "Decide whether to build the workbook"
BUILD = "Build the workbook"
PUBLISH_WB = "Publish the workbook (release nfl-workbook)"
KEEP_WB = "Keep the workbook (run artifact, 7 days)"

NAMES = ["nfl-pipeline-weekly.yml", "nfl-pipeline-monthly.yml", "nfl-pipeline-watchdog.yml", "nfl-pipeline-ci.yml"]
SCHEDULED = NAMES[:3]
PUBLISHING = NAMES[:2]

# Every pin was checked against the upstream tag with `git ls-remote` (2026-11-20). A new pin must be
# checked the same way and added here.
KNOWN_PINS = {
    "actions/checkout": ("3d3c42e5aac5ba805825da76410c181273ba90b1", "v7.0.1"),
    "actions/setup-python": ("6d4fd22b20465ccc0f7354476588e8df7c9ca0e0", "v7.1.0"),
    "actions/upload-artifact": ("cf430e030ddbb5b0abf93d22962f4752f3646cd9", "v7.0.2"),
}


def load(name):
    text = (WORKFLOW_DIR / name).read_text(encoding="utf-8")
    return text, yaml.safe_load(text)


def triggers(doc):
    # YAML 1.1 reads the bare key `on` as boolean True.
    return doc.get("on", doc.get(True))


def steps(doc):
    for job_id, job in doc["jobs"].items():
        for step in job.get("steps", []):
            yield job_id, step


def step_named(doc, name):
    found = [s for _j, s in steps(doc) if s.get("name") == name]
    assert len(found) == 1, f"expected one step named {name!r}, found {len(found)}"
    return found[0]


def crons(doc):
    return [entry["cron"] for entry in (triggers(doc).get("schedule") or [])]


def glob_regex(pattern):
    """GitHub's path-filter glob: ** crosses folders, * and ? do not."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out + r"\Z")


def path_filter_matches(patterns, path):
    """GitHub semantics: patterns are applied in order; a later `!pattern` excludes again."""
    matched = False
    for p in patterns:
        if p.startswith("!"):
            if glob_regex(p[1:]).match(path):
                matched = False
        elif glob_regex(p).match(path):
            matched = True
    return matched


@pytest.fixture(params=NAMES)
def wf(request):
    text, doc = load(request.param)
    return request.param, text, doc


# ---- structure ------------------------------------------------------------------------------------

def test_all_files_present():
    present = sorted(p.name for p in WORKFLOW_DIR.glob("nfl-*.yml")) + sorted(p.name for p in WORKFLOW_DIR.glob("nfl-*.yaml"))
    assert present == sorted(NAMES)
    assert not (PIPELINE_DIR / "workflows").exists(), "the old inactive copies must be gone (only one source of truth)"


def test_parses_and_has_name_and_triggers(wf):
    name, _text, doc = wf
    assert doc["name"] == name.removesuffix(".yml")
    assert triggers(doc), "no triggers"
    assert "workflow_dispatch" in triggers(doc)


def test_only_safe_events_for_a_public_repository(wf):
    """No pull_request_target, workflow_run, issue_comment, issues...: nobody outside can start a write job."""
    _name, text, doc = wf
    assert set(triggers(doc)) <= ALLOWED_EVENTS, set(triggers(doc)) - ALLOWED_EVENTS
    code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    assert "pull_request_target" not in code
    for _j, step in steps(doc):      # continue-on-error hides a failure: only the convenience artifact copies may use it
        if "continue-on-error" in step:
            assert step.get("uses", "").startswith("actions/upload-artifact@"), step.get("name")


def test_each_workflow_has_exactly_its_events(wf):
    name, _text, doc = wf
    assert set(triggers(doc)) == EVENTS[name]


def test_scoped_to_the_nfl_folder(wf):
    """A future NBA/ folder and its nba-pipeline-*.yml files never start, or get confused with, these."""
    name, text, doc = wf
    assert doc["defaults"]["run"]["working-directory"] == WORKDIR
    # No absolute local path (Linux or macOS home folder, Windows drive path) in a public workflow file.
    assert not re.search(r"/home/|/Users/|(?<![\w])[A-Za-z]:[\\/]", text), f"{name} contains an absolute local path"
    for event in ("push", "pull_request"):
        spec = triggers(doc).get(event)
        if isinstance(spec, dict):
            for p in spec.get("paths", []):
                assert p.lstrip("!").startswith(("NFL/", ".github/workflows/nfl-pipeline-")), f"{name}: {p}"
            for other in ("NBA/02-config/leagues.csv", "NBA/03-pipeline/nbapipe/run.py",
                          ".github/workflows/nba-pipeline-weekly.yml", "README.md", "docs/notes.md"):
                assert not path_filter_matches(spec.get("paths", []), other), f"{name} {event} fires for {other}"
    groups = [doc.get("concurrency", {}).get("group", "")] + [j.get("concurrency", {}).get("group", "") for j in doc["jobs"].values()]
    assert all(g == "" or g.startswith("nfl-") for g in groups)
    env = doc.get("env", {})
    if "ALERT_LABEL" in env:
        assert env["ALERT_LABEL"].startswith("nfl-pipeline-alert-")


@pytest.mark.parametrize("name", SCHEDULED)
def test_cron_off_the_hour_and_valid(name):
    _text, doc = load(name)
    entries = crons(doc)
    assert entries, f"{name} has no schedule"
    for expr in entries:
        fields = expr.split()
        assert len(fields) == 5, expr
        minute = fields[0]
        assert minute.isdigit() and 1 <= int(minute) <= 59, f"minute must be a fixed non-zero value: {expr}"
        assert minute not in ("15", "30", "45"), f"avoid quarter-hour minutes too: {expr}"


def test_weekly_schedule():
    _text, doc = load("nfl-pipeline-weekly.yml")
    entries = [e.split() for e in crons(doc)]
    assert sorted(e[4] for e in entries) == ["2", "3", "4"]   # Tue, Wed, Thu
    assert all(e[3] == SEASON_MONTHS and e[2] == "*" for e in entries)


def test_watchdog_schedule():
    _text, doc = load("nfl-pipeline-watchdog.yml")
    entries = [e.split() for e in crons(doc)]
    assert entries and all(e[4] == "5" and e[3] == SEASON_MONTHS for e in entries)   # Friday, in season


def test_monthly_schedule_and_heartbeat_fire():
    _text, doc = load("nfl-pipeline-monthly.yml")
    entries = crons(doc)
    days = sorted(int(e.split()[2]) for e in entries)
    assert days == [1, 16], "full run on the 1st, heartbeat-only fire on the 16th"
    assert all(e.split()[3:] == ["*", "*"] for e in entries), "all year, not only in season"
    heartbeat = doc["env"]["HEARTBEAT_CRON"]
    assert heartbeat in entries and heartbeat.split()[2] == "16"
    # 60-day rule (public repository): the longest commit gap must stay under 60 days even when one fire
    # is dropped. Fires are at most 16 days apart; a dropped fire makes that 31.
    threshold = int(doc["env"]["HEARTBEAT_AFTER_DAYS"])
    assert threshold + 31 < 60 and threshold >= 14


def test_weekly_push_trigger_publishes_config_changes_without_a_loop():
    _text, doc = load("nfl-pipeline-weekly.yml")
    push = triggers(doc)["push"]
    assert push["branches"] == ["main"]
    paths = push["paths"]
    for p in ("NFL/02-config/scoring_weights.csv", "NFL/02-config/leagues.csv", "NFL/02-config/bonus_rules.csv",
              "NFL/02-config/pipeline_config.csv", "NFL/02-config/scoring_weights (1).csv"):
        assert path_filter_matches(paths, p), p
    assert not path_filter_matches(paths, "NFL/02-config/README.md"), "a README edit is not a config change"
    # A1 / R2-01: the merge of a pipeline or workflow change takes the normal path, so the workbook gets built.
    for p in ("NFL/03-pipeline/nflpipe/export_xlsx.py", "NFL/03-pipeline/nflpipe/run.py", ".github/workflows/nfl-pipeline-weekly.yml"):
        assert path_filter_matches(paths, p), p
    for p in ("NFL/03-pipeline/AUTOMATION.md", "NFL/03-pipeline/tests/test_workflows.py", ".github/workflows/nfl-pipeline-monthly.yml",
              "NFL/05-excel/README.md"):
        assert not path_filter_matches(paths, p), p
    # The workflow commits only NFL/04-data: those paths must never match its own trigger.
    for p in ("NFL/04-data/status.csv", "NFL/04-data/config/leagues.csv", "NFL/04-data/player_week/player_week_2026.csv"):
        assert not path_filter_matches(paths, p), p
    for other in ("monthly", "watchdog"):
        _t, d = load(f"nfl-pipeline-{other}.yml")
        assert "push" not in triggers(d)


def test_config_file_list_matches_the_pipeline():
    """The weekly stray-file check must know exactly the files the pipeline reads."""
    from nflpipe.config import CONFIG_FILES
    _text, doc = load("nfl-pipeline-weekly.yml")
    assert doc["env"]["CONFIG_FILES"].split() == list(CONFIG_FILES) + ["README.md"]
    present = sorted(p.name for p in (REPO_ROOT / "NFL" / "02-config").iterdir())
    assert set(present) <= set(doc["env"]["CONFIG_FILES"].split()), f"the real config folder would HOLD: {present}"


def test_ci_paths():
    _text, doc = load("nfl-pipeline-ci.yml")
    on = triggers(doc)
    assert "schedule" not in on
    for event in ("push", "pull_request"):
        paths = on[event]["paths"]
        for p in ("NFL/03-pipeline/nflpipe/run.py", "NFL/02-config/leagues.csv", "NFL/06-qa/fixtures/golden_sample.csv",
                  ".github/workflows/nfl-pipeline-weekly.yml"):
            assert path_filter_matches(paths, p), (event, p)
        for p in ("NFL/04-data/status.csv", "NFL/05-excel/build/x.py"):
            assert not path_filter_matches(paths, p), (event, p)
    assert on["push"]["branches"] == ["main"]


def test_weekly_dispatch_inputs():
    _text, doc = load("nfl-pipeline-weekly.yml")
    inputs = triggers(doc)["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"seasons", "dry_run", "force", "workbook_only"}
    assert inputs["seasons"]["default"] == "current"
    assert inputs["dry_run"]["type"] == inputs["force"]["type"] == inputs["workbook_only"]["type"] == "boolean"
    assert inputs["workbook_only"]["default"] is False


@pytest.mark.parametrize("name", PUBLISHING)
def test_shared_concurrency_group(name):
    _text, doc = load(name)
    assert doc["concurrency"]["group"] == PUBLISH_GROUP
    assert doc["concurrency"]["cancel-in-progress"] is False


def test_watchdog_cannot_displace_a_waiting_publish():
    """A newer queued run replaces the pending one in its group; the watchdog must not be in the publish group."""
    _text, doc = load("nfl-pipeline-watchdog.yml")
    assert doc["concurrency"]["group"] != PUBLISH_GROUP
    assert doc["concurrency"]["cancel-in-progress"] is False


def test_never_cancel_in_progress(wf):
    _name, _text, doc = wf
    blocks = [doc.get("concurrency")] + [job.get("concurrency") for job in doc["jobs"].values()]
    for block in blocks:
        if isinstance(block, dict):
            assert block.get("cancel-in-progress") is not True


def test_no_expressions_inside_run_blocks(wf):
    """Inputs, event data, secrets and step outputs reach shell only through env:."""
    _name, _text, doc = wf
    for job_id, step in steps(doc):
        script = step.get("run")
        if script is None:
            continue
        assert "${{" not in script, f"{job_id}/{step.get('name')}: expression spliced into run:"


def test_no_inputs_or_event_expressions_in_run_text(wf):
    # Belt and braces on the raw text, in case a run: block is written in an unusual YAML form.
    _name, text, _doc = wf
    for match in re.finditer(r"\$\{\{\s*(inputs|github\.event)\.", text):
        line = text[: match.start()].rsplit("\n", 1)[-1]
        assert re.match(r"\s+[A-Z_]+: $|\s+if: |\s+(python-version|cache-dependency-path): ", line), \
            f"input/event expression outside env:/if:: {line!r}"


def test_uses_pinned_to_verified_full_sha(wf):
    _name, text, doc = wf
    for _job, step in steps(doc):
        if "uses" in step:
            assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", step["uses"]), step["uses"]
            action, sha = step["uses"].split("@")
            assert KNOWN_PINS.get(action, (None,))[0] == sha, f"unverified pin {step['uses']}"
    for line in text.splitlines():
        if line.strip().startswith(("uses:", "- uses:")):
            m = re.search(r"([\w.-]+/[\w.-]+)@([0-9a-f]{40}) # (v\d+\.\d+\.\d+)$", line)
            assert m, f"SHA pin needs a version comment: {line}"
            assert KNOWN_PINS[m.group(1)] == (m.group(2), m.group(3)), line


def test_permissions_minimal(wf):
    name, _text, doc = wf
    assert doc["permissions"] == {"contents": "read"}
    for job in doc["jobs"].values():
        perms = job.get("permissions", {})
        for scope, level in perms.items():
            assert level in ALLOWED_JOB_PERMISSIONS.get(scope, set()), f"{name}: {scope}: {level}"
        if name not in PUBLISHING:
            assert perms.get("contents", "read") == "read", f"{name} must not write contents"
    if name == "nfl-pipeline-ci.yml":
        assert all(not job.get("permissions") for job in doc["jobs"].values()), "CI only reads"


def test_checkout_never_persists_the_token(wf):
    _name, _text, doc = wf
    for _j, step in steps(doc):
        if step.get("uses", "").startswith("actions/checkout@"):
            assert step["with"]["persist-credentials"] is False


def test_token_only_where_needed(wf):
    """The write token reaches only the commit, heartbeat and alert steps, never the pipeline steps."""
    name, text, doc = wf
    assert "secrets." not in text, "no secrets in a public repository's workflows"
    assert "NFL_DATA_REPO" not in text, "the second data repository is gone"
    allowed = {"Commit 04-data", "Heartbeat (keep the schedules alive)", "Update the rolling alert issue",
               DECIDE, PUBLISH_WB}
    for _j, step in steps(doc):
        if "github.token" in str(step.get("env", {})):
            assert step["name"] in allowed, f"{name}: {step['name']} gets the token"
        if step.get("name") in ("Commit 04-data", "Heartbeat (keep the schedules alive)"):
            assert "git config --local http" not in step["run"] and "extraheader" in step["run"]


def test_working_directory(wf):
    _name, _text, doc = wf
    assert doc["defaults"]["run"]["working-directory"] == WORKDIR
    assert doc["defaults"]["run"]["shell"] == "bash"
    for _job, step in steps(doc):
        if "working-directory" in step:
            assert step["working-directory"] == "${{ github.workspace }}"
    assert PIPELINE_DIR.as_posix().endswith(WORKDIR), "working directory no longer matches this folder"
    assert (REPO_ROOT / DATA_PATH).is_dir()


def test_artifact_path_is_the_report_dir():
    for name in PUBLISHING:
        _text, doc = load(name)
        step = step_named(doc, "Keep the gate report (run artifact, 30 days)")
        assert step["with"]["path"] == "NFL/.work/last-run/"


def test_no_pip_install_on_run_paths():
    for name in SCHEDULED:
        _text, doc = load(name)
        for _j, step in steps(doc):
            assert "pip install" not in step.get("run", ""), name
            assert "cache" not in step.get("with", {}), f"{name}: no pip cache needed on run paths"
    text, doc = load("nfl-pipeline-ci.yml")
    assert "pip install -r requirements-dev.txt" in text
    assert "python -m pytest" in text
    assert doc["jobs"]["config-check"]["if"] == "github.event_name == 'pull_request'"
    assert "--dry-run" in step_named(doc, "Dry run of the pipeline with this pull request's config (publishes nothing)")["run"]


@pytest.mark.parametrize("name", PUBLISHING)
def test_exit_code_branching(name):
    text, _doc = load(name)
    for fragment in ("0) outcome=PUBLISH", "3) outcome=SKIP", "4) outcome=HOLD", "*) outcome=ERROR", "set +e",
                     "rc=${PIPESTATUS[0]}"):
        assert fragment in text, f"{name}: missing {fragment!r}"
    assert "python -m nflpipe" in text


def test_weekly_uses_resolve_then_run_current():
    _text, doc = load("nfl-pipeline-weekly.yml")
    runs = "\n".join(step.get("run", "") for _j, step in steps(doc))
    assert "python -m nflpipe resolve" in runs
    assert '--seasons "${SEASONS:-current}"' in runs
    assert '3) out "decision=skip"' in runs


def test_monthly_runs_all_seasons():
    text, _doc = load("nfl-pipeline-monthly.yml")
    assert "run --seasons all" in text


def test_watchdog_branches_on_5():
    text, _doc = load("nfl-pipeline-watchdog.yml")
    assert "python -m nflpipe watchdog --max-age-hours" in text
    assert "5) outcome=STALE" in text


@pytest.mark.parametrize("name", PUBLISHING)
def test_commit_recipe(name):
    _text, doc = load(name)
    assert doc["env"]["DATA_PATH"] == DATA_PATH
    step = step_named(doc, "Commit 04-data")
    assert "always()" not in str(step.get("if", ""))
    for fragment in ("outcome == 'PUBLISH'", "dry_run != 'true'", "github.ref == 'refs/heads/main'"):
        assert fragment in step["if"], fragment
    script = step["run"]
    assert 'git add -- "$DATA_PATH"' in script
    assert "git add -A" not in script and "git add ." not in script
    assert "git diff --cached --quiet" in script
    assert "for attempt in 1 2 3" in script and "exit 1" in script
    assert "set -euo pipefail" in script


def test_no_second_data_repository_step():
    for name in PUBLISHING:
        _text, doc = load(name)
        assert not [s for _j, s in steps(doc) if "data repository" in s.get("name", "")]


@pytest.mark.parametrize("name", SCHEDULED)
def test_rolling_issue_and_red_exit(name):
    _text, doc = load(name)
    issue = step_named(doc, "Update the rolling alert issue")
    assert issue["if"] == "${{ !cancelled() }}"
    script = issue["run"]
    for fragment in ("gh label create", "--force", "gh issue list --label", "--author app/github-actions",
                     "gh issue comment", "gh issue create", "gh issue close", "${GUIDE_URL}#alert-issues", "ALERT_DETAILS"):
        assert fragment in script, fragment
    short = name.removeprefix("nfl-pipeline-").removesuffix(".yml")
    assert doc["env"]["ALERT_LABEL"] == f"nfl-pipeline-alert-{short}"      # one issue per workflow (M-04)
    assert doc["env"]["GUIDE_URL"].endswith("/wes-blue/sports-analysis/blob/main/NFL/03-pipeline/AUTOMATION.md")
    last = list(steps(doc))[-1][1]
    assert last["name"].startswith("Fail the run") and "exit 1" in last["run"]


def test_guide_exists_and_has_the_alert_anchor():
    text = GUIDE.read_text(encoding="utf-8")
    assert re.search(r"^## Alert issues$", text, re.M), "issue bodies link to #alert-issues"
    for label in ("nfl-pipeline-alert-weekly", "nfl-pipeline-alert-monthly", "nfl-pipeline-alert-watchdog"):
        assert label in text
    for word in ("terminal", "git clone", "python -m", "Git Bash", "GitHub Desktop"):
        assert word not in text, f"the guide must not assume a local clone or terminal: {word!r}"


def test_requirements_dev_pinned():
    lines = [ln.strip() for ln in (PIPELINE_DIR / "requirements-dev.txt").read_text().splitlines()
             if ln.strip() and not ln.startswith("#")]
    names = {ln.split("==")[0].lower() for ln in lines}
    assert {"pytest", "pyyaml"} <= names
    assert all(re.fullmatch(r"[A-Za-z0-9_.-]+==[0-9][0-9A-Za-z.]*", ln) for ln in lines), lines


# ---- executing the workflows' own shell steps ----------------------------------------------------

GH_STUB = r"""#!/usr/bin/env bash
# Fake GitHub CLI: open issues are files $GH_STATE/<label> holding the issue number.
set -u
echo "gh $*" >> "$GH_STATE/log"
case "$1 $2" in
  "label create") exit 0 ;;
  "issue list")
    label=""; while [[ $# -gt 0 ]]; do [[ "$1" == "--label" ]] && label="$2"; shift; done
    [[ -f "$GH_STATE/$label" ]] && cat "$GH_STATE/$label"; exit 0 ;;
  "issue create")
    label=""; while [[ $# -gt 0 ]]; do [[ "$1" == "--label" ]] && label="$2"; shift; done
    n=$(( $(cat "$GH_STATE/counter" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$GH_STATE/counter"
    echo "$n" > "$GH_STATE/$label"; exit 0 ;;
  "issue comment") exit 0 ;;
  "issue close")
    for f in "$GH_STATE"/nfl-pipeline-alert-*; do [[ -f "$f" && "$(cat "$f")" == "$3" ]] && rm "$f"; done
    exit 0 ;;
esac
echo "unexpected gh call: $*" >&2; exit 2
"""

FAKE_PYTHON = r"""#!/usr/bin/env bash
# Fake interpreter for `python -m nflpipe ...`: records the call, prints a line, exits $FAKE_RC.
echo "python $*" >> "$FAKE_LOG"
echo "fake nflpipe: $*"
exit "${FAKE_RC:-0}"
"""


def need_tools(*tools):
    for tool in ("bash",) + tools:
        if shutil.which(tool) is None:
            pytest.skip(f"{tool} not available")


def run_step(name, step_name, tmp_path, *, cwd, env, bin_dir=None, expect_rc=0):
    """Run one step's script as the runner does (bash -eo pipefail) with literal env values."""
    need_tools()
    _text, doc = load(name)
    step = step_named(doc, step_name)
    out = tmp_path / f"out-{time.monotonic_ns()}"
    out.write_text("")
    summary = tmp_path / "summary.md"
    full = dict(os.environ)
    full.update({k: str(v) for k, v in doc.get("env", {}).items()})
    full.update({k: str(v) for k, v in (step.get("env") or {}).items() if "${{" not in str(v)})
    full.update(GITHUB_OUTPUT=str(out), GITHUB_STEP_SUMMARY=str(summary), GITHUB_SERVER_URL="https://github.com",
                GITHUB_RUN_ID="42", GITHUB_RUN_ATTEMPT="1", RUNNER_TEMP=str(tmp_path))
    if bin_dir:
        full["PATH"] = f"{bin_dir}{os.pathsep}{full['PATH']}"
    full.update(env)
    done = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]], cwd=cwd,
                          env=full, capture_output=True, text=True, timeout=120)
    assert done.returncode == expect_rc, done.stdout + done.stderr
    outputs = dict(line.split("=", 1) for line in out.read_text().splitlines() if "=" in line)
    return outputs, done


def make_bin(tmp_path, python=None):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "gh").write_text(GH_STUB)
    (bin_dir / "sleep").write_text("#!/bin/sh\nexit 0\n")        # retries without waiting
    if python == "fake":
        (bin_dir / "python").write_text(FAKE_PYTHON)
    elif python == "real" and not (bin_dir / "python").exists():
        import sys
        (bin_dir / "python").symlink_to(sys.executable)
    for f in bin_dir.iterdir():
        if not f.is_symlink():
            f.chmod(0o755)
    return bin_dir


def project_tree(tmp_path, config_files=("leagues.csv", "scoring_weights.csv", "bonus_rules.csv",
                                         "pipeline_config.csv", "README.md")):
    root = tmp_path / "ws"
    (root / "NFL" / "03-pipeline").mkdir(parents=True)
    (root / "NFL" / "02-config").mkdir()
    for f in config_files:
        (root / "NFL" / "02-config" / f).write_text("x\n")
    return root


RESOLVE = "Resolve (is there work?)"


def resolve(tmp_path, root, event="schedule", ref="refs/heads/main", rc=0, **inputs):
    bin_dir = make_bin(tmp_path, python="fake")
    log = tmp_path / "python.log"
    log.write_text("")
    env = {"EVENT": event, "REF": ref, "SHA": "abcdef1234567890", "FAKE_LOG": str(log), "FAKE_RC": str(rc),
           "IN_SEASONS": inputs.get("seasons", ""), "IN_FORCE": inputs.get("force", ""), "IN_WORKBOOK_ONLY": inputs.get("workbook_only", ""),
           "IN_DRY_RUN": inputs.get("dry_run", "")}
    outputs, _done = run_step("nfl-pipeline-weekly.yml", RESOLVE, tmp_path, cwd=root / "NFL" / "03-pipeline",
                              env=env, bin_dir=bin_dir)
    return outputs, log.read_text()


def test_resolve_step_push_runs_without_force_and_skips_resolve(tmp_path):
    """Any push (config, pipeline code, this workflow) takes the normal path: `run` publishes if something differs,
    otherwise SKIPs and the workbook step repairs what is missing. No --force, so one rule covers every push."""
    outputs, calls = resolve(tmp_path, project_tree(tmp_path), event="push")
    assert outputs["decision"] == "run" and outputs["force"] == "false" and outputs["seasons"] == "current"
    assert outputs["dry_run"] == "false"
    assert "abcdef1" in outputs["reason"]
    assert calls == "", "a push must not depend on resolve's verdict"
    for event in ("push", "schedule", "workflow_dispatch"):      # --force is only ever the owner's checkbox
        outputs, _calls = resolve(tmp_path / event, project_tree(tmp_path / event), event=event)
        assert outputs.get("force", "false") == "false"


@pytest.mark.parametrize("rc,decision", [(0, "run"), (3, "skip"), (1, "error"), (2, "error")])
def test_resolve_step_schedule_follows_resolve(tmp_path, rc, decision):
    outputs, calls = resolve(tmp_path, project_tree(tmp_path), rc=rc)
    assert outputs["decision"] == decision
    assert outputs["force"] == "false"
    assert calls.strip() == "python -m nflpipe resolve"


def test_resolve_step_dispatch_force_bypasses_resolve(tmp_path):
    outputs, calls = resolve(tmp_path, project_tree(tmp_path), event="workflow_dispatch", force="true",
                             seasons="current", dry_run="false")
    assert outputs["decision"] == "run" and outputs["force"] == "true" and calls == ""
    outputs, calls = resolve(tmp_path, project_tree(tmp_path / "b"), event="workflow_dispatch", force="false",
                             seasons="2024", dry_run="false")
    assert outputs["decision"] == "run" and outputs["seasons"] == "2024" and calls == ""


def test_resolve_step_holds_on_a_stray_file_in_config(tmp_path):
    root = project_tree(tmp_path)
    (root / "NFL" / "02-config" / "scoring_weights (1).csv").write_text("x\n")
    for event in ("push", "schedule"):
        outputs, calls = resolve(tmp_path, root, event=event)
        assert outputs["decision"] == "hold"
        assert "scoring_weights (1).csv" in outputs["reason"]
        assert calls == ""


def test_resolve_step_holds_on_a_missing_config_file_folder(tmp_path):
    root = project_tree(tmp_path)
    (root / "NFL" / "02-config" / "sub").mkdir()
    outputs, _calls = resolve(tmp_path, root, event="push")
    assert outputs["decision"] == "hold" and "sub" in outputs["reason"]


@pytest.mark.parametrize("seasons", ["current\nforce=true", "all\n", "2025\r", "all; rm -rf /", "$(id)", "20255", "2017-2026-2030",
                                     "2025 ", "../../x", "CURRENT"])
def test_resolve_step_rejects_a_bad_seasons_input_without_echoing_it(tmp_path, seasons):
    """A2-12: the free-text input never reaches $GITHUB_OUTPUT or a command; the run is red (decision=error)."""
    outputs, calls = resolve(tmp_path, project_tree(tmp_path), event="workflow_dispatch", seasons=seasons)
    assert outputs["decision"] == "error" and outputs["seasons"] == "current" and outputs["dry_run"] == "true"
    assert outputs["force"] == "false" and calls == ""
    assert set(outputs) == {"decision", "seasons", "dry_run", "force", "reason"}, "no extra line reached the output file"
    assert "rm -rf" not in outputs["reason"] and "$(id)" not in outputs["reason"]


@pytest.mark.parametrize("seasons", ["", "current", "all", "2025", "2017-2026"])
def test_resolve_step_accepts_the_documented_seasons(tmp_path, seasons):
    outputs, _calls = resolve(tmp_path, project_tree(tmp_path), event="workflow_dispatch", seasons=seasons, force="false")
    assert outputs["seasons"] == (seasons or "current") and outputs["decision"] in ("run", "skip")


def test_resolve_step_off_main_is_always_a_dry_run(tmp_path):
    outputs, _calls = resolve(tmp_path, project_tree(tmp_path), event="workflow_dispatch",
                              ref="refs/heads/test", force="true", dry_run="false")
    assert outputs["dry_run"] == "true"


@pytest.mark.parametrize("rc,outcome", [(0, "PUBLISH"), (3, "SKIP"), (4, "HOLD"), (1, "ERROR"), (137, "ERROR")])
def test_run_step_maps_exit_codes_and_passes_flags(tmp_path, rc, outcome):
    root = project_tree(tmp_path)
    bin_dir = make_bin(tmp_path, python="fake")
    log = tmp_path / "python.log"
    outputs, done = run_step("nfl-pipeline-weekly.yml", "Run pipeline", tmp_path, cwd=root / "NFL" / "03-pipeline",
                             bin_dir=bin_dir, env={"SEASONS": "current", "DRY_RUN": "true", "FORCE": "true",
                                                   "TRIGGER": "push-weekly", "FAKE_LOG": str(log), "FAKE_RC": str(rc),
                                                   "RUN_LOG": str(tmp_path / "run.log")})
    assert outputs["outcome"] == outcome and outputs["rc"] == str(rc)
    assert log.read_text().strip() == "python -m nflpipe run --seasons current --trigger push-weekly --dry-run --force"
    assert "fake nflpipe" in (tmp_path / "run.log").read_text(), "the log is kept for the alert details"


def test_record_outcome_puts_the_failing_gate_in_the_details(tmp_path):
    root = project_tree(tmp_path)
    report = root / "NFL" / ".work" / "last-run"
    (report / "checks").mkdir(parents=True)
    (report / "run_summary.csv").write_text("key,value\noutcome,HOLD\ndetail,G-CONFIG: unknown metric 'pasing_yards'\n")
    (report / "checks" / "gates.csv").write_text(
        "gate_id,gate,severity,result,detail,checked_utc\n"
        "G-CONFIG,config,blocking,FAIL,scoring_weights.csv: metric 'pasing_yards' is not in the data,x\n"
        "G-GRAIN,grain,blocking,PASS,ok,x\n")
    details = tmp_path / "details.md"
    outputs, _done = run_step("nfl-pipeline-weekly.yml", "Record outcome", tmp_path, cwd=root / "NFL" / "03-pipeline",
                              bin_dir=make_bin(tmp_path, python="real"),
                              env={"DECISION": "run", "RUN_OUTCOME": "HOLD", "RUN_RC": "4", "DRY_RUN": "false",
                                   "EVENT": "push", "RESOLVE_REASON": "NFL/02-config changed on main (commit abcdef1)",
                                   "RUN_LOG": str(tmp_path / "none.log"), "ALERT_DETAILS": str(details)})
    assert outputs["outcome"] == "HOLD"
    text = details.read_text()
    assert "G-CONFIG FAIL (blocking): scoring_weights.csv: metric 'pasing_yards'" in text
    assert "G-GRAIN" not in text
    summary = (tmp_path / "summary.md").read_text()
    assert "### NFL pipeline weekly: HOLD" in summary and "pasing_yards" in summary


def test_record_outcome_error_quotes_the_log_and_hold_from_resolve(tmp_path):
    root = project_tree(tmp_path)
    log = tmp_path / "run.log"
    log.write_text("downloading...\nERROR: bonus_rules.csv is not UTF-8: 'utf-8' codec can't decode\n")
    details = tmp_path / "details.md"
    outputs, _ = run_step("nfl-pipeline-weekly.yml", "Record outcome", tmp_path, cwd=root / "NFL" / "03-pipeline",
                          bin_dir=make_bin(tmp_path, python="real"),
                          env={"DECISION": "run", "RUN_OUTCOME": "ERROR", "RUN_RC": "1", "DRY_RUN": "false",
                               "EVENT": "push", "RESOLVE_REASON": "", "RUN_LOG": str(log), "ALERT_DETAILS": str(details)})
    assert outputs["outcome"] == "ERROR" and "is not UTF-8" in details.read_text()
    outputs, _ = run_step("nfl-pipeline-weekly.yml", "Record outcome", tmp_path, cwd=root / "NFL" / "03-pipeline",
                          bin_dir=make_bin(tmp_path, python="real"),
                          env={"DECISION": "hold", "RUN_OUTCOME": "", "RUN_RC": "", "DRY_RUN": "false", "EVENT": "push",
                               "RESOLVE_REASON": "NFL/02-config holds file(s) the pipeline does not read: x.csv",
                               "RUN_LOG": str(log), "ALERT_DETAILS": str(details)})
    assert outputs["outcome"] == "HOLD" and "x.csv" in details.read_text()


def test_monthly_heartbeat_fire_does_not_run_the_pipeline(tmp_path):
    root = project_tree(tmp_path)
    bin_dir = make_bin(tmp_path, python="fake")
    log = tmp_path / "python.log"
    log.write_text("")
    _text, doc = load("nfl-pipeline-monthly.yml")
    common = {"IN_DRY_RUN": "", "REF": "refs/heads/main", "TRIGGER": "schedule-monthly", "FAKE_LOG": str(log),
              "RUN_LOG": str(tmp_path / "run.log"), "ALERT_DETAILS": str(tmp_path / "d.md")}
    outputs, _ = run_step("nfl-pipeline-monthly.yml", "Run pipeline (all seasons)", tmp_path,
                          cwd=root / "NFL" / "03-pipeline", bin_dir=bin_dir,
                          env=dict(common, EVENT_SCHEDULE=doc["env"]["HEARTBEAT_CRON"]))
    assert outputs == {"dry_run": "false", "outcome": "HEARTBEAT"} and log.read_text() == ""
    outputs, _ = run_step("nfl-pipeline-monthly.yml", "Run pipeline (all seasons)", tmp_path,
                          cwd=root / "NFL" / "03-pipeline", bin_dir=bin_dir,
                          env=dict(common, EVENT_SCHEDULE="23 11 1 * *", FAKE_RC="3"))
    assert outputs["outcome"] == "SKIP"
    assert log.read_text().strip() == "python -m nflpipe run --seasons all --trigger schedule-monthly"


# -- git: the commit step and the heartbeat against a throwaway remote --

def git(*args, cwd, env=None, date=None):
    e = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="t",
             GIT_COMMITTER_EMAIL="t@example.invalid", **(env or {}))
    if date:
        e.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    return subprocess.run(["git", *args], cwd=cwd, env=e, capture_output=True, text=True, check=True).stdout.strip()


def remote_and_clone(tmp_path, age_days=0):
    need_tools("git")
    remote = tmp_path / "remote.git"
    git("init", "-q", "--bare", "-b", "main", str(remote), cwd=tmp_path)
    seed = tmp_path / "seed"
    (seed / "NFL" / "04-data").mkdir(parents=True)
    (seed / "NFL" / "02-config").mkdir(parents=True)
    (seed / "NFL" / "04-data" / "status.csv").write_text("key,value\noutcome,PUBLISH\n")
    (seed / "NFL" / "02-config" / "leagues.csv").write_text("League\nA\n")
    git("init", "-q", "-b", "main", cwd=seed)
    git("add", "-A", cwd=seed)
    date = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - age_days * 86400))
    git("commit", "-q", "-m", "seed", cwd=seed, date=date)
    git("remote", "add", "origin", f"file://{remote}", cwd=seed)
    git("push", "-q", "origin", "main", cwd=seed)
    ws = tmp_path / "ws"
    git("clone", "-q", "--depth", "1", f"file://{remote}", str(ws), cwd=tmp_path)
    return remote, ws


def other_commit(tmp_path, remote, name="OTHER.txt"):
    work = tmp_path / f"other-{time.monotonic_ns()}"
    git("clone", "-q", f"file://{remote}", str(work), cwd=tmp_path)
    (work / name).write_text("someone else\n")
    git("add", "-A", cwd=work)
    git("commit", "-q", "-m", "concurrent", cwd=work)
    git("push", "-q", "origin", "main", cwd=work)


def commit_step(name, tmp_path, ws, expect_rc=0):
    return run_step(name, "Commit 04-data", tmp_path, cwd=ws, bin_dir=make_bin(tmp_path), expect_rc=expect_rc,
                    env={"BRANCH": "main", "GH_TOKEN": "dummy", "EVENT": "schedule", "RUN_URL": "https://example.invalid/run"})


@pytest.mark.parametrize("name", PUBLISHING)
def test_commit_step_commits_only_the_data_and_survives_a_concurrent_push(tmp_path, name):
    remote, ws = remote_and_clone(tmp_path)
    (ws / "NFL" / "04-data" / "status.csv").write_text("key,value\noutcome,PUBLISH\nrun_id,2\n")
    (ws / "NFL" / "02-config" / "leagues.csv").write_text("League\nCHANGED-IN-WORKSPACE\n")   # must not be committed
    (ws / "stray.txt").write_text("not data\n")
    other_commit(tmp_path, remote)                                       # main moved on during the run
    _out, done = commit_step(name, tmp_path, ws)
    assert "push rejected (attempt 1)" in done.stdout and "pushed on attempt 2" in done.stdout
    files = git("--git-dir", str(remote), "show", "--name-only", "--format=", "main", cwd=tmp_path).splitlines()
    assert files == ["NFL/04-data/status.csv"]
    assert git("--git-dir", str(remote), "show", "main:OTHER.txt", cwd=tmp_path) == "someone else"
    assert git("--git-dir", str(remote), "show", "main:NFL/02-config/leagues.csv", cwd=tmp_path) == "League\nA"
    assert "run_id,2" in git("--git-dir", str(remote), "show", "main:NFL/04-data/status.csv", cwd=tmp_path)
    assert "extraheader" not in (ws / ".git" / "config").read_text(), "token written to .git/config"


@pytest.mark.parametrize("name", PUBLISHING)
def test_commit_step_no_change_guard(tmp_path, name):
    remote, ws = remote_and_clone(tmp_path)
    head = git("--git-dir", str(remote), "rev-parse", "main", cwd=tmp_path)
    _out, done = commit_step(name, tmp_path, ws)
    assert "unchanged; nothing to commit" in done.stdout
    assert git("--git-dir", str(remote), "rev-parse", "main", cwd=tmp_path) == head


def test_commit_step_gives_up_after_three_rejections(tmp_path):
    remote, ws = remote_and_clone(tmp_path)
    hook = remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho no >&2\nexit 1\n")
    hook.chmod(0o755)
    (ws / "NFL" / "04-data" / "status.csv").write_text("key,value\nrun_id,3\n")
    _out, done = commit_step("nfl-pipeline-weekly.yml", tmp_path, ws, expect_rc=1)
    assert "could not push NFL/04-data after 3 attempts" in done.stdout


HEARTBEAT = "Heartbeat (keep the schedules alive)"


def heartbeat(tmp_path, ws, expect_rc=0):
    _text, doc = load("nfl-pipeline-monthly.yml")
    env = {k: v for k, v in step_named(doc, HEARTBEAT)["env"].items() if "${{" not in v}
    env.update(BRANCH="main", GH_TOKEN="dummy", RUN_URL="https://example.invalid/run")
    return run_step("nfl-pipeline-monthly.yml", HEARTBEAT, tmp_path, cwd=ws, bin_dir=make_bin(tmp_path),
                    env=env, expect_rc=expect_rc)


def test_heartbeat_pushes_an_empty_commit_after_three_quiet_weeks(tmp_path):
    remote, ws = remote_and_clone(tmp_path, age_days=22)
    before = git("--git-dir", str(remote), "rev-parse", "main", cwd=tmp_path)
    (ws / "NFL" / "04-data" / "status.csv").write_text("left over from a failed publish\n")   # dirty tree
    (ws / "NFL" / "stray.txt").write_text("untracked\n")
    _out, done = heartbeat(tmp_path, ws)
    assert "pushed empty commit" in done.stdout
    assert git("--git-dir", str(remote), "rev-parse", "main~1", cwd=tmp_path) == before
    assert git("--git-dir", str(remote), "diff", "--stat", "main~1", "main", cwd=tmp_path) == ""   # no file changed
    assert "heartbeat" in git("--git-dir", str(remote), "log", "-1", "--format=%s", "main", cwd=tmp_path)
    assert "github-actions[bot]" in git("--git-dir", str(remote), "log", "-1", "--format=%an", "main", cwd=tmp_path)


def test_heartbeat_not_needed_when_main_is_recent(tmp_path):
    remote, ws = remote_and_clone(tmp_path, age_days=20)
    before = git("--git-dir", str(remote), "rev-parse", "main", cwd=tmp_path)
    _out, done = heartbeat(tmp_path, ws)
    assert "Heartbeat not needed" in done.stdout
    assert git("--git-dir", str(remote), "rev-parse", "main", cwd=tmp_path) == before


def test_heartbeat_retries_a_rejected_push(tmp_path):
    remote, ws = remote_and_clone(tmp_path, age_days=40)
    flag = tmp_path / "rejected"
    hook = remote / "hooks" / "pre-receive"
    hook.write_text(f"#!/bin/sh\nif [ ! -f '{flag}' ]; then touch '{flag}'; exit 1; fi\nexit 0\n")
    hook.chmod(0o755)
    _out, done = heartbeat(tmp_path, ws)
    assert flag.exists() and "rejected (attempt 1)" in done.stdout and "pushed empty commit" in done.stdout


def test_heartbeat_stops_when_someone_else_committed_meanwhile(tmp_path):
    remote, ws = remote_and_clone(tmp_path, age_days=40)
    other_commit(tmp_path, remote)        # the fetch inside the step sees a fresh commit
    head = git("--git-dir", str(remote), "rev-parse", "main", cwd=tmp_path)
    _out, done = heartbeat(tmp_path, ws)
    assert "Heartbeat not needed" in done.stdout
    assert git("--git-dir", str(remote), "rev-parse", "main", cwd=tmp_path) == head


def test_heartbeat_runs_even_after_a_red_pipeline():
    _text, doc = load("nfl-pipeline-monthly.yml")
    step = step_named(doc, HEARTBEAT)
    assert step["if"].startswith("${{ !cancelled()") and "github.ref == 'refs/heads/main'" in step["if"]
    names = [s["name"] for _j, s in steps(doc)]
    assert names.index("Commit 04-data") < names.index(HEARTBEAT) < names.index("Update the rolling alert issue")


# ---- M-04: an alert is closed only by a run that proves the problem is gone -----------------------

def alert_step(name):
    _text, doc = load(name)
    return step_named(doc, "Update the rolling alert issue"), doc


def run_alert(tmp_path, name, outcome, job_status="success", dry_run="", details="", **extra_env):
    """Run the workflow's real alert script with a fake gh; returns the open issues by label."""
    need_tools()
    step, doc = alert_step(name)
    state = tmp_path / "gh-state"
    state.mkdir(exist_ok=True)
    bin_dir = make_bin(tmp_path)
    detail_file = tmp_path / "details.md"
    detail_file.write_text(details)
    env = {k: v for k, v in step["env"].items() if not str(v).startswith("${{")}
    env.update(os.environ.copy())
    env.update(PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}", GH_STATE=str(state),
               ALERT_LABEL=doc["env"]["ALERT_LABEL"], GUIDE_URL=doc["env"]["GUIDE_URL"], JOB_STATUS=job_status,
               OUTCOME=outcome, DRY_RUN=dry_run, WORKFLOW_NAME=doc["name"], RUN_URL="https://example.invalid/run",
               EVENT="schedule", SHA="abcdef1234", ALERT_DETAILS=str(detail_file), **extra_env)
    done = subprocess.run(["bash", "-c", step["run"]], env=env, capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    return {f.name: f.read_text().strip() for f in state.glob("nfl-pipeline-alert-*")}


def test_alert_sequence_from_qa_finding_m04(tmp_path):
    """nflverse is late: weekly SKIPs, the watchdog goes STALE. No SKIP may close the alert."""
    weekly, monthly, watchdog = "nfl-pipeline-weekly.yml", "nfl-pipeline-monthly.yml", "nfl-pipeline-watchdog.yml"
    assert run_alert(tmp_path, weekly, "SKIP") == {}
    assert run_alert(tmp_path, watchdog, "STALE") == {"nfl-pipeline-alert-watchdog": "1"}
    assert run_alert(tmp_path, weekly, "SKIP") == {"nfl-pipeline-alert-watchdog": "1"}      # QA: closed it here
    assert run_alert(tmp_path, monthly, "SKIP") == {"nfl-pipeline-alert-watchdog": "1"}
    assert run_alert(tmp_path, weekly, "HOLD") == {"nfl-pipeline-alert-watchdog": "1", "nfl-pipeline-alert-weekly": "2"}
    assert run_alert(tmp_path, weekly, "SKIP")["nfl-pipeline-alert-weekly"] == "2"
    assert run_alert(tmp_path, weekly, "PUBLISH", dry_run="true")["nfl-pipeline-alert-weekly"] == "2"
    assert run_alert(tmp_path, weekly, "PUBLISH", job_status="failure")["nfl-pipeline-alert-weekly"] == "2"
    assert run_alert(tmp_path, weekly, "PUBLISH") == {"nfl-pipeline-alert-watchdog": "1"}
    assert run_alert(tmp_path, watchdog, "HEALTHY") == {}
    log = (tmp_path / "gh-state" / "log").read_text()
    assert log.count("issue close") == 2 and log.count("issue create") == 2


def test_red_runs_comment_on_the_open_issue(tmp_path):
    run_alert(tmp_path, "nfl-pipeline-monthly.yml", "ERROR")
    assert run_alert(tmp_path, "nfl-pipeline-monthly.yml", "HOLD") == {"nfl-pipeline-alert-monthly": "1"}
    assert "issue comment 1" in (tmp_path / "gh-state" / "log").read_text()
    assert run_alert(tmp_path, "nfl-pipeline-monthly.yml", "SKIP") == {"nfl-pipeline-alert-monthly": "1"}
    assert run_alert(tmp_path, "nfl-pipeline-monthly.yml", "PUBLISH") == {}


def test_heartbeat_outcome_is_green_but_never_closes(tmp_path):
    assert run_alert(tmp_path, "nfl-pipeline-monthly.yml", "HEARTBEAT") == {}, "a heartbeat run is green"
    assert not (tmp_path / "gh-state" / "log").exists(), "a green non-closing run does not touch issues"
    run_alert(tmp_path, "nfl-pipeline-monthly.yml", "HOLD")
    assert run_alert(tmp_path, "nfl-pipeline-monthly.yml", "HEARTBEAT") == {"nfl-pipeline-alert-monthly": "1"}
    assert run_alert(tmp_path, "nfl-pipeline-monthly.yml", "HEARTBEAT", job_status="failure") == {"nfl-pipeline-alert-monthly": "1"}
    assert "issue comment 1" in (tmp_path / "gh-state" / "log").read_text()   # a failed heartbeat is red


def test_alert_body_carries_details_and_guide_link(tmp_path):
    run_alert(tmp_path, "nfl-pipeline-weekly.yml", "HOLD", details="G-CONFIG FAIL (blocking): metric 'pasing_yards'")
    log = (tmp_path / "gh-state" / "log").read_text()
    assert "pasing_yards" in log and "AUTOMATION.md#alert-issues" in log and "abcdef1" in log


@pytest.mark.parametrize("name,closing", [("nfl-pipeline-weekly.yml", "PUBLISH"),
                                          ("nfl-pipeline-monthly.yml", "PUBLISH"),
                                          ("nfl-pipeline-watchdog.yml", "HEALTHY")])
def test_only_proof_closes(name, closing):
    step, _doc = alert_step(name)
    assert step["env"]["CLOSING_OUTCOMES"] == closing
    assert "SKIP" not in step["env"]["CLOSING_OUTCOMES"]


def test_dry_run_summary_says_nothing_was_committed():
    text, _doc = load("nfl-pipeline-weekly.yml")
    assert "PUBLISH (dry run: checked only, nothing was committed)" in text
    text, _doc = load("nfl-pipeline-monthly.yml")
    assert "PUBLISH (dry run)" in text


# ---- the workbook release (CONTRACTS.md section 13.5, decision D-042; reviews A2 and R2 of 3.001) ---------

def dry_step_id(name):
    return "resolve" if name == "nfl-pipeline-weekly.yml" else "outcome"


def script_of(name, step_name):
    return step_named(load(name)[1], step_name)["run"]


@pytest.mark.parametrize("name", PUBLISHING)
def test_workbook_steps_exist_in_order_and_after_the_data_commit(name):
    _text, doc = load(name)
    names = [s.get("name") for _j, s in steps(doc)]
    order = ["Commit 04-data", DECIDE, BUILD, PUBLISH_WB, KEEP_WB, "Update the rolling alert issue"]
    assert [names.index(n) for n in order] == sorted(names.index(n) for n in order)
    assert doc["env"]["WORKBOOK_TAG"] == WB_TAG and doc["env"]["WORKBOOK_ASSET"] == WB_ASSET
    assert [doc["env"][k] for k in ("WORKBOOK_ASSET", "TABLE_PLAYERS_ASSET", "TABLE_SEASONS_ASSET", "REFRESH_ASSET")] == ALL_ASSETS


@pytest.mark.parametrize("name", PUBLISHING)
def test_workbook_runs_only_after_publish_skip_or_by_hand_never_on_dry_runs(name):
    """A failed data commit blocks it (no always()); HOLD, ERROR and HEARTBEAT never reach it."""
    _text, doc = load(name)
    cond = step_named(doc, DECIDE)["if"]
    assert "always()" not in cond and "cancelled()" not in cond, "a failed commit must stop the workbook"
    for outcome in ("PUBLISH", "SKIP", "WORKBOOK"):
        assert f"steps.outcome.outputs.outcome == '{outcome}'" in cond
    for outcome in ("HOLD", "ERROR", "HEARTBEAT"):
        assert outcome not in cond
    assert f"steps.{dry_step_id(name)}.outputs.dry_run != 'true'" in cond
    assert "github.ref == 'refs/heads/main'" in cond
    for step_name in (BUILD, PUBLISH_WB):
        step = step_named(doc, step_name)
        assert step["if"] == "steps.wbcheck.outputs.build == 'true'", "SKIP with a current workbook builds nothing"
    keep = step_named(doc, KEEP_WB)
    assert "steps.wbbuild.outcome == 'success'" in keep["if"] and "!cancelled()" in keep["if"]
    assert keep["with"]["retention-days"] == 7
    assert keep["with"]["path"].split() == [f"NFL/.work/workbook/{a}" for a in ALL_ASSETS], "the run artifact keeps the CSV files too"


@pytest.mark.parametrize("name", PUBLISHING)
def test_run_artifacts_cannot_fail_the_run_or_collide_on_a_rerun(name):
    """A2-03: artifacts belong to the run, not the attempt. 'Re-run failed jobs' keeps the run id, so the attempt is
    in the name, and a convenience copy must never turn a good run red."""
    _text, doc = load(name)
    for step_name in (KEEP_WB, "Keep the gate report (run artifact, 30 days)"):
        step = step_named(doc, step_name)
        assert step["continue-on-error"] is True, step_name
        assert step["with"]["name"].endswith("-${{ github.run_id }}-${{ github.run_attempt }}"), step_name
    assert step_named(doc, KEEP_WB)["with"]["name"] == "workbook-${{ github.run_id }}-${{ github.run_attempt }}"
    assert step_named(doc, KEEP_WB)["with"]["compression-level"] == 6, "the 38 MB CSV compresses to about an eighth; the workbooks are zip data already"


@pytest.mark.parametrize("name", PUBLISHING)
def test_every_workbook_step_has_a_timeout_and_the_job_keeps_its_own(name):
    _text, doc = load(name)
    for step_name in (DECIDE, BUILD, PUBLISH_WB):
        assert 0 < step_named(doc, step_name)["timeout-minutes"] <= 30, step_name
    job = next(iter(doc["jobs"].values()))
    assert job["timeout-minutes"] == JOB_TIMEOUT[name], "the all-seasons run plus the export must not be cut short"


@pytest.mark.parametrize("name", PUBLISHING)
def test_workbook_export_command_and_token_scope(name):
    _text, doc = load(name)
    build = step_named(doc, BUILD)
    assert 'python -m nflpipe export --data-dir ../04-data --out "$file" --tables-dir "$WORKBOOK_DIR"' in build["run"], "one pass writes workbook and tables"
    assert 'python -m nflpipe refresh-workbook --out "$refresh"' in build["run"]
    assert "github.token" not in str(build.get("env", {})), "the export step needs no token"
    assert "gh " not in build["run"]
    for step_name in (DECIDE, PUBLISH_WB):
        assert step_named(doc, step_name)["env"]["GH_TOKEN"] == "${{ github.token }}"
    assert step_named(doc, KEEP_WB).get("env") is None


@pytest.mark.parametrize("name", PUBLISHING)
def test_the_zip_is_fully_checked_before_anything_is_uploaded(name):
    """A2-13 #25 and #34: testzip (every member's checksum), the member name and a size floor."""
    build = step_named(load(name)[1], BUILD)
    assert "z.testzip() is not None" in build["run"] and '"xl/workbook.xml" not in z.namelist()' in build["run"]
    assert "python -I -" in build["run"], "the check runs in isolated mode"
    assert int(build["env"]["WORKBOOK_MIN_BYTES"]) >= 1_000_000
    assert '"$size" -ge "$WORKBOOK_MIN_BYTES"' in build["run"]
    assert "built, ${size} bytes" in build["run"]
    # the refresh workbook is a zip too; the two CSV files get a header, size and line-count check (design 2.2)
    assert 'readable_xlsx "$file"' in build["run"] and 'readable_xlsx "$refresh"' in build["run"]
    env = build["env"]
    assert int(env["PLAYERS_MIN_BYTES"]) >= 1_000_000 and int(env["PLAYERS_MIN_LINES"]) >= 1000
    assert int(env["SEASONS_MIN_BYTES"]) >= 100_000 and int(env["SEASONS_MIN_LINES"]) >= 100
    assert int(env["REFRESH_MIN_BYTES"]) >= 1000
    assert '== "season," ]]' in build["run"] and "wc -l" in build["run"]
    assert 'check_table "$players"' in build["run"] and 'check_table "$seasons"' in build["run"]


@pytest.mark.parametrize("name", PUBLISHING)
def test_release_is_a_prerelease_never_latest_and_needs_no_extra_permission(name):
    text, doc = load(name)
    script = step_named(doc, PUBLISH_WB)["run"]
    for fragment in ('gh release create "$WORKBOOK_TAG"', '--target "$(git rev-parse HEAD)"', "--prerelease",
                     "--latest=false", 'gh release edit "$WORKBOOK_TAG" --notes-file', "for attempt in 1 2 3"):
        assert fragment in script, fragment
    # Releases and assets need `contents: write`, which the job already has: no new permission scope.
    job = next(iter(doc["jobs"].values()))
    assert job["permissions"] == {"contents": "write", "issues": "write"}
    assert doc["permissions"] == {"contents": "read"}
    # Creating a tag or release must not start anything: no release/create/tag trigger, and `push` is branch-filtered.
    assert not {"release", "create", "registry_package"} & set(triggers(doc))
    push = triggers(doc).get("push")
    assert push is None or push.get("branches") == ["main"]
    assert doc["concurrency"]["group"] == PUBLISH_GROUP, "uploads wait for data commits and for each other"


@pytest.mark.parametrize("name", PUBLISHING)
def test_publish_swaps_all_four_assets_and_never_deletes_a_live_one_first(name):
    """A2-02 generalised (D-054): gh `release upload --clobber` deletes the old asset BEFORE uploading. Every new file is
    uploaded under a temporary name and verified, and only then do the delete and rename pairs run, back to back."""
    s = script_of(name, PUBLISH_WB)
    assert 'assets=("$WORKBOOK_ASSET" "$TABLE_PLAYERS_ASSET" "$TABLE_SEASONS_ASSET" "$REFRESH_ASSET")' in s
    assert """nextname() { printf '%s.next.%s' "${1%.*}" "${1##*.}"; }""" in s
    order = ['gh release upload "$WORKBOOK_TAG" "$stage/$1"',        # 3 upload every file under its temporary name
             'newid[$a]="$id"',                                       # 4 verify EVERY upload (finished, right size)
             'drop_assets "$a"',                                      # 5 the first old asset goes ...
             "gh api -X PATCH",                                       #   ... and its new file takes the stable name
             "curl ",                                                 # 6 every public address answers
             'gh release edit "$WORKBOOK_TAG" --notes-file']          # 7 only now do the notes carry the new key
    positions = [s.index(x) for x in order]
    assert positions == sorted(positions) and len(set(positions)) == len(positions), order
    assert '-f name="$a"' in s
    # one loop uploads, a separate loop verifies, and the delete/rename loop comes after both: no delete before the last verification
    code = "\n".join(ln for ln in s.splitlines() if not ln.lstrip().startswith("#"))
    assert code.count('for a in "${assets[@]}"; do') >= 5
    assert code.index('newid[$a]="$id"') < code.index('drop_assets "$a"')
    assert code.count('drop_assets "$a"') == 1, "the only delete of a live asset is inside the swap loop"
    # --clobber appears once, as the fallback after a rename failed, when no live asset is left to overwrite.
    assert code.count("--clobber") == 1 and code.index("--clobber") > code.index("gh api -X PATCH")
    assert 'gh release upload "$WORKBOOK_TAG" "$WORKBOOK_DIR/$a" --clobber' in code
    # a leftover temporary asset from a dead run is removed before the upload
    assert s.index('drop_assets "$1" || return 1') < s.index('gh release upload "$WORKBOOK_TAG" "$stage/$1"')
    assert "state==\\\"uploaded\\\" and .size==${size[$a]}" in s
    # a failed upload or verification removes every temporary asset and says no live asset was touched
    assert code.count("drop_all_next\n") >= 2 and "no asset already on the release was touched" in s


@pytest.mark.parametrize("name", PUBLISHING)
def test_publish_checks_every_public_address_and_retries_the_cdn(name):
    """A2-06: ask for each stable address the way a browser does; 200 or 206 or the run is red."""
    s = script_of(name, PUBLISH_WB)
    assert "curl -sL --max-time 60 -r 0-0 -o /dev/null -w '%{http_code}' \"${base}/${a}\"" in s
    assert '"$code" == "200" || "$code" == "206"' in s and "for attempt in 1 2 3 4 5" in s
    assert "sleep $((attempt * 5))" in s
    assert 'answers ${code:-nothing}' in s
    for fragment in ("sleep $((attempt * 10))", "sleep $((attempt * 5))", "sleep 2"):   # backoff on every retried write
        assert fragment in s, fragment
    # the link check runs inside a loop over all four assets, and the notes are written after the failures are checked
    curl_at = s.index("curl -sL")
    assert s.rindex('for a in "${assets[@]}"; do', 0, curl_at) > s.index('gh api -X PATCH')
    assert s.index('[[ -z "$bad" ]]', curl_at) < s.index('gh release edit "$WORKBOOK_TAG" --notes-file')


@pytest.mark.parametrize("name", PUBLISHING)
def test_release_detection_is_structured_fails_closed_and_treats_a_draft_as_unpublished(name):
    """A2-05, A2-06: no parsing of gh's English error text; a failed read is a stop, never 'missing'."""
    for step_name in (DECIDE, PUBLISH_WB):
        s = script_of(name, step_name)
        assert "release not found" not in s.lower()
        assert 'gh api --paginate "' in s and "select(.tag_name==" in s and '(.draft)' in s
        assert "is a draft" in s
        assert 'stop "could not list the releases' in s
    decide = script_of(name, DECIDE)
    assert "gh release create" not in decide and "gh release view" not in decide
    assert "retry gh api" in decide and "for n in 1 2 3; do" in decide and "sleep $((n * 5))" in decide
    assert '.state=="uploaded" and .size>0' in decide, "an empty 'starter' asset does not count as present"


@pytest.mark.parametrize("name", PUBLISHING)
def test_freshness_key_has_four_fields_and_missing_means_any_asset(name):
    """A2-07 and D-054: a change to the workbook's or the tables' design republishes although the data did not change;
    a release with the workbook but not the three new assets counts as missing."""
    s = script_of(name, DECIDE)
    assert 'key="${run_id}|${version}|${design}|${tables}"' in s
    assert "WORKBOOK_VERSION" in s and "TABLES_VERSION" in s and "nflpipe/export_xlsx.py" in s
    assert "import" not in s.split("design=")[1].split("\n")[0], "the version is read from the source, not imported"
    assert "import" not in s.split("tables=")[1].split("\n")[0]
    assert 'for v in "$run_id" "$version" "$design" "$tables"; do' in s
    for stable in ("$WORKBOOK_ASSET", "$TABLE_PLAYERS_ASSET", "$TABLE_SEASONS_ASSET", "$REFRESH_ASSET"):
        assert stable in s.split("# All four must be there")[1].split("if [[ -z \"$missing\" ]]")[0], stable
    assert "have_asset=true" in s.split('if [[ -z "$missing" ]]')[1][:30], "current only when none of the four is missing"
    real = (PIPELINE_DIR / "nflpipe" / "export_xlsx.py").read_text(encoding="utf-8")
    for const in ("WORKBOOK_VERSION", "TABLES_VERSION"):
        assert re.search(rf'^{const} = "[0-9A-Za-z._-]+"', real, re.M), f"the workflow's sed no longer finds {const}"
    assert 'grep -qF "nfl-workbook-key: ${key} " <<< "$body"' in s, "trailing space: 1.2.1 is not a prefix match of 1.2.10"


def test_the_workflow_reads_the_real_exporter_constants():
    """The decide step's own sed, run against the real exporter source (no export is run)."""
    need_tools("sed")
    src = PIPELINE_DIR / "nflpipe" / "export_xlsx.py"
    for const in ("WORKBOOK_VERSION", "TABLES_VERSION"):
        out = subprocess.run(["sed", "-n", f's/^{const} = "\\([0-9A-Za-z._-]*\\)".*/\\1/p', str(src)],
                             capture_output=True, text=True).stdout.split()
        assert len(out) == 1 and out[0], const


@pytest.mark.parametrize("name", PUBLISHING)
def test_notes_name_every_asset_and_the_key(name):
    s = script_of(name, PUBLISH_WB)
    notes = s.split("cat > \"$NOTES_FILE\" <<NOTES")[1].split("\nNOTES\n")[0]
    for var in ("WORKBOOK_ASSET", "TABLE_PLAYERS_ASSET", "TABLE_SEASONS_ASSET", "REFRESH_ASSET"):
        assert "${base}/${" + var + "}" in notes, var
    assert "nfl-workbook-key: ${WORKBOOK_KEY}" in notes and "CC BY 4.0" in notes


@pytest.mark.parametrize("name", PUBLISHING)
def test_dry_runs_and_the_heartbeat_never_publish_the_tables(name):
    """The tables ride on the same three steps as the workbook, so the same guards apply to all four assets."""
    _text, doc = load(name)
    for step_name in (DECIDE, BUILD, PUBLISH_WB, KEEP_WB):
        step = step_named(doc, step_name)
        cond = str(step.get("if"))
        assert "HEARTBEAT" not in cond
        if step_name == DECIDE:
            assert f"steps.{dry_step_id(name)}.outputs.dry_run != 'true'" in cond and "refs/heads/main" in cond
        elif step_name != KEEP_WB:
            assert cond == "steps.wbcheck.outputs.build == 'true'"
    # no other step uploads to a release
    for _j, s in steps(doc):
        if s.get("name") != PUBLISH_WB:
            assert "gh release" not in s.get("run", ""), s.get("name")


@pytest.mark.parametrize("name", PUBLISHING)
def test_workbook_is_built_from_the_latest_data_on_main(name):
    """A2-09: a queued run was started from an older commit."""
    s = script_of(name, DECIDE)
    assert "git fetch -q --no-tags --depth=1 origin main" in s
    assert "git checkout -q FETCH_HEAD -- ../04-data" in s
    assert s.index("git checkout -q FETCH_HEAD") < s.index("run_id=")


def test_notes_are_updated_only_after_the_upload():
    """If the notes (which carry the build key) changed first, a failed upload would look 'current' to the next run."""
    for name in PUBLISHING:
        script = script_of(name, PUBLISH_WB)
        assert script.index("gh release upload") < script.index("gh release edit")
        assert "--notes \"The workbook is being uploaded" in script, "first creation holds a placeholder, not the key"
        assert "nfl-workbook-key: ${WORKBOOK_KEY}" in script


def test_workbook_only_dispatch_is_wired_in_both_workflows():
    for name in PUBLISHING:
        _text, doc = load(name)
        inputs = triggers(doc)["workflow_dispatch"]["inputs"]
        assert inputs["workbook_only"]["type"] == "boolean" and inputs["workbook_only"]["default"] is False
    _t, weekly = load("nfl-pipeline-weekly.yml")
    assert step_named(weekly, RESOLVE)["env"]["IN_WORKBOOK_ONLY"] == "${{ inputs.workbook_only }}"
    assert "workbook) outcome=WORKBOOK" in step_named(weekly, "Record outcome")["run"]
    _t, monthly = load("nfl-pipeline-monthly.yml")
    assert step_named(monthly, "Run pipeline (all seasons)")["env"]["IN_WORKBOOK_ONLY"] == "${{ inputs.workbook_only }}"


@pytest.mark.parametrize("name", PUBLISHING)
def test_workbook_outcome_is_green_never_closes_and_does_not_fail_the_run(name):
    _text, doc = load(name)
    alert = step_named(doc, "Update the rolling alert issue")
    assert "WORKBOOK" in alert["env"]["GREEN_OUTCOMES"].split()
    assert "WORKBOOK" not in alert["env"]["CLOSING_OUTCOMES"].split()
    assert "outcome != 'WORKBOOK'" in list(steps(doc))[-1][1]["if"]


# -- stand-ins: a release store that behaves like GitHub (and like gh, which deletes before it uploads), and curl --

GH_RELEASE_STUB = r'''#!/usr/bin/env python3
"""Stand-in for the GitHub CLI: the release and REST calls the workbook steps use, on a JSON store $GH_STATE/state.json.
Modelled on cli/cli v2.89.0 (review A2): `release upload --clobber` DELETES the asset with that name FIRST, then
uploads; without --clobber an existing name is refused; a duplicate asset name on rename is refused (422).
Knobs (env): GH_<KIND>_FAILS = how many calls of that kind fail (kinds: list get create upload delete patch edit),
GH_<KIND>_FAIL_NAME = only for calls about this asset name, GH_LIST_ERROR = the error text, GH_CREATE_PHANTOM = a failed
create has still created the release, GH_UPLOAD_LEAVES_STARTER = a failed upload leaves an empty asset, GH_UPLOAD_SHORT =
the upload 'succeeds' but the asset stays empty. Invariant checks write $GH_STATE/violations."""
import json, os, subprocess, sys
S = os.environ["GH_STATE"]; P = os.path.join(S, "state.json")
LIVES = ["NFL-Analysis.xlsx", "NFL-PlayerGames.csv", "NFL-SeasonTotals.csv", "NFL-Analysis-Refresh.xlsx"]
def next_of(n):
    return n.rsplit(".", 1)[0] + ".next." + n.rsplit(".", 1)[1]
a = sys.argv[1:]
with open(os.path.join(S, "log"), "a") as f:
    f.write("gh " + " ".join(a) + "\n")
def die(msg, rc=1):
    sys.stderr.write(msg + "\n"); sys.exit(rc)
if not os.environ.get("GH_TOKEN") or not os.environ.get("GH_REPO"):
    die("gh: no token or repo", 4)
s = json.load(open(P)) if os.path.exists(P) else {"releases": [], "next_id": 100, "n": {}}
def save():
    json.dump(s, open(P, "w"), indent=1)
def violation(text):
    open(os.path.join(S, "violations"), "a").write(text + "\n")
def fails(kind, name=None):
    only = os.environ.get(f"GH_{kind.upper()}_FAIL_NAME")
    if only and name != only:
        return False
    s["n"][kind] = s["n"].get(kind, 0) + 1; save()
    return s["n"][kind] <= int(os.environ.get(f"GH_{kind.upper()}_FAILS", "0"))
def opt(flag, default=None):
    return a[a.index(flag) + 1] if flag in a else default
def jq(obj, expr):
    r = subprocess.run(["jq", "-r", expr], input=json.dumps(obj), capture_output=True, text=True)
    sys.stdout.write(r.stdout); sys.stderr.write(r.stderr); sys.exit(r.returncode)
def find(tag):
    return next((r for r in s["releases"] if r["tag_name"] == tag), None)
def new_release(tag, body, prerelease):
    s["next_id"] += 1
    r = {"id": s["next_id"], "tag_name": tag, "draft": False, "prerelease": prerelease, "body": body, "assets": []}
    s["releases"].append(r); return r
def new_asset(r, name, size, state="uploaded"):
    s["next_id"] += 1
    r["assets"].append({"id": s["next_id"], "name": name, "size": size, "state": state})
if a[:2] == ["release", "create"]:
    if fails("create"):
        if os.environ.get("GH_CREATE_PHANTOM"):
            new_release(a[2], opt("--notes", ""), "--prerelease" in a); save()
        die("HTTP 500: Server Error")
    if find(a[2]):
        die("HTTP 422: Validation Failed (already_exists)")
    new_release(a[2], opt("--notes", ""), "--prerelease" in a); save()
elif a[:2] == ["release", "upload"]:
    r = find(a[2])
    if not r:
        die("release not found")
    name = os.path.basename(a[3]); clobber = "--clobber" in a
    existing = [x for x in r["assets"] if x["name"] == name]
    if existing and not clobber:
        die(f"HTTP 422: asset under the same name already exists: [{name}]")
    if existing:
        if name in LIVES and not r["draft"]:
            violation("--clobber on a live asset (gh deletes it before it uploads)")
        r["assets"] = [x for x in r["assets"] if x["name"] != name]; save()
    if fails("upload", name):
        if os.environ.get("GH_UPLOAD_LEAVES_STARTER"):
            new_asset(r, name, 0, "starter")
        save(); die("HTTP 502: Bad Gateway (https://uploads.github.com/...)")
    if name in LIVES:
        s.setdefault("renamed", []).append(name)
    elif name != name.replace(".next.", "."):
        s["renamed"] = []          # a new publish begins
    if os.environ.get("GH_UPLOAD_SHORT") and os.environ.get("GH_UPLOAD_SHORT_NAME", name) == name:
        new_asset(r, name, 0, "starter")
    else:
        new_asset(r, name, os.path.getsize(a[3]))
    save()
elif a[:2] == ["release", "edit"]:
    if fails("edit"):
        die("HTTP 500: Server Error")
    find(a[2])["body"] = open(opt("--notes-file")).read(); save()
elif a[0] == "api":
    method = opt("-X", "GET")
    endpoint = next(x for x in a[1:] if x.startswith("repos/"))
    tail = endpoint.split("?")[0].split("/")[3:]
    if tail == ["releases"]:
        if fails("list"):
            die(os.environ.get("GH_LIST_ERROR", "HTTP 502: Bad Gateway"))
        jq(s["releases"], opt("--jq", "."))
    elif len(tail) == 2 and tail[0] == "releases":
        if fails("get"):
            die("HTTP 502: Bad Gateway")
        rel = next((x for x in s["releases"] if str(x["id"]) == tail[1]), None)
        if not rel:
            die("gh: Not Found (HTTP 404)")
        jq(rel, opt("--jq", "."))
    elif tail[:2] == ["releases", "assets"]:
        hit = [(r, x) for r in s["releases"] for x in r["assets"] if str(x["id"]) == tail[2]]
        if not hit:
            die("gh: Not Found (HTTP 404)")
        r, asset = hit[0]
        if method == "DELETE":
            if fails("delete", asset["name"]):
                die("HTTP 502: Bad Gateway")
            if asset["name"] in LIVES:
                # a live asset may go only when EVERY new file of this publish is on the release (or already took its stable name)
                gone = [n for n in LIVES if not any(x["name"] == next_of(n) and x["state"] == "uploaded" and x["size"] > 0 for x in r["assets"])
                        and n not in s.get("renamed", [])]
                if gone:
                    violation("a live asset was deleted before every new file was on the release: missing " + ", ".join(gone))
            r["assets"].remove(asset); save()
        elif method == "PATCH":
            if fails("patch"):
                die("HTTP 502: Bad Gateway")
            new = a[a.index("-f") + 1].split("=", 1)[1]
            if any(x["name"] == new for x in r["assets"]):
                die("gh: Validation Failed (HTTP 422) already_exists")
            asset["name"] = new; s.setdefault("renamed", []).append(new); save()
        else:
            die("unexpected method " + method, 2)
    else:
        die("unexpected api call " + endpoint, 2)
else:
    die("unexpected gh call: " + " ".join(a), 2)
'''

CURL_STUB = r'''#!/usr/bin/env python3
"""Stand-in for the ranged GET on the public download address. Serves what GitHub would: a published (not draft)
release with a finished, non-empty asset of that name answers 206, anything else 404. Knobs: CURL_404_FIRST = this many
calls answer 404 first (the CDN catching up), CURL_CODE = always this code, CURL_BAD_NAME = this asset always answers 404."""
import json, os, sys
S = os.environ["GH_STATE"]; args = sys.argv[1:]
open(os.path.join(S, "curl.log"), "a").write(" ".join(args) + "\n")
if "-sL" not in args or args[args.index("-r") + 1] != "0-0" or "--max-time" not in args:
    sys.stderr.write("curl: not a ranged, redirect-following, time-limited GET\n"); sys.exit(2)
url = args[-1]; count_file = os.path.join(S, "curl.count")
n = int(open(count_file).read()) + 1 if os.path.exists(count_file) else 1
open(count_file, "w").write(str(n))
if os.environ.get("CURL_CODE"):
    sys.stdout.write(os.environ["CURL_CODE"]); sys.exit(0)
if os.environ.get("CURL_BAD_NAME") and url.endswith("/" + os.environ["CURL_BAD_NAME"]):
    sys.stdout.write("404"); sys.exit(0)
if n <= int(os.environ.get("CURL_404_FIRST", "0")):
    sys.stdout.write("404"); sys.exit(0)
state = json.load(open(os.path.join(S, "state.json"))) if os.path.exists(os.path.join(S, "state.json")) else {"releases": []}
tag, name = url.split("/")[-2], url.split("/")[-1]
ok = any(r["tag_name"] == tag and not r["draft"] and any(x["name"] == name and x["state"] == "uploaded" and x["size"] > 0 for x in r["assets"])
         for r in state["releases"])
sys.stdout.write("206" if ok else "404")
'''

EXPORT_PYTHON = r"""#!/usr/bin/env bash
# Stand-in for `python -m nflpipe export` and `refresh-workbook`: FAKE_EXPORT=ok writes a tiny valid package, notxlsx a zip
# without a workbook, badcrc a zip whose workbook member fails its checksum, garbage a non-zip file, fail exits 1.
# With --tables-dir the two CSV files are written too: FAKE_TABLES=ok, bom (a byte-order mark), empty (players is empty),
# short (too few lines), nofile (players is not written). FAKE_REFRESH=ok|fail|garbage for the refresh workbook.
# Every other call goes to the real interpreter.
if [[ "$1 $2 $3" == "-m nflpipe refresh-workbook" ]]; then
  echo "python $*" >> "$FAKE_LOG"
  out=""; while [[ $# -gt 0 ]]; do [[ "$1" == "--out" ]] && out="$2"; shift; done
  case "${FAKE_REFRESH:-ok}" in
    fail) echo "refresh-workbook: ERROR: boom"; exit 1 ;;
    garbage) mkdir -p "$(dirname "$out")"; echo "not a zip" > "$out"; exit 0 ;;
    *) mkdir -p "$(dirname "$out")"
       "$REAL_PY" -c 'import sys, zipfile
z = zipfile.ZipFile(sys.argv[1], "w"); z.writestr("xl/workbook.xml", "<workbook>" + "r" * 200 + "</workbook>"); z.close()' "$out"; exit 0 ;;
  esac
fi
if [[ "$1 $2 $3" == "-m nflpipe export" ]]; then
  echo "python $*" >> "$FAKE_LOG"
  out=""; tdir=""; while [[ $# -gt 0 ]]; do [[ "$1" == "--out" ]] && out="$2"; [[ "$1" == "--tables-dir" ]] && tdir="$2"; shift; done
  if [[ -n "$tdir" && "${FAKE_EXPORT:-ok}" != "fail" ]]; then
    mkdir -p "$tdir"
    hdr="season,week,x"; [[ "${FAKE_TABLES:-ok}" == "bom" ]] && hdr=$'\xef\xbb\xbf'"season,week,x"
    n=40; [[ "${FAKE_TABLES:-ok}" == "short" ]] && n=2
    if [[ "${FAKE_TABLES:-ok}" == "empty" ]]; then : > "$tdir/NFL-PlayerGames.csv"
    elif [[ "${FAKE_TABLES:-ok}" != "nofile" ]]; then
      { echo "$hdr"; for i in $(seq 1 $n); do echo "2026,$i,1.5"; done; } > "$tdir/NFL-PlayerGames.csv"
    fi
    { echo "season,games,x"; for i in $(seq 1 20); do echo "2026,$i,1.5"; done; } > "$tdir/NFL-SeasonTotals.csv"
  fi
  case "${FAKE_EXPORT:-ok}" in
    fail) echo "export: ERROR: cannot read status.csv"; exit 1 ;;
    garbage) mkdir -p "$(dirname "$out")"; echo "not a zip" > "$out"; exit 0 ;;
    notxlsx) mkdir -p "$(dirname "$out")"
       "$REAL_PY" -c 'import sys, zipfile
z = zipfile.ZipFile(sys.argv[1], "w"); z.writestr("readme.txt", "hello"); z.close()' "$out"; exit 0 ;;
    badcrc) mkdir -p "$(dirname "$out")"
       "$REAL_PY" -c 'import sys, zipfile
z = zipfile.ZipFile(sys.argv[1], "w", zipfile.ZIP_STORED); z.writestr("xl/workbook.xml", "<workbook>" * 20); z.close()
data = bytearray(open(sys.argv[1], "rb").read()); i = data.index(b"<workbook>"); data[i + 1] ^= 1
open(sys.argv[1], "wb").write(bytes(data))' "$out"; exit 0 ;;
    *) mkdir -p "$(dirname "$out")"
       "$REAL_PY" -c 'import sys, zipfile
z = zipfile.ZipFile(sys.argv[1], "w"); z.writestr("xl/workbook.xml", "<workbook/>"); z.close()' "$out"; exit 0 ;;
  esac
fi
exec "$REAL_PY" "$@"
"""

STATUS = ("key,value\nrun_id,20261120T233201Z-gh1\ngenerated_utc,2026-11-20T23:32:09Z\npipeline_version,1.2.1\n"
          "latest_season,2026\nlatest_week,11\nlatest_season_type,REG\ngates_pass,13\ngates_warn,1\ngates_fail,0\n"
          'data_source,"nflverse, https://github.com/nflverse/nflverse-data"\n')
DESIGN = "3.001"
TABLES = "1"
KEY = f"20261120T233201Z-gh1|1.2.1|{DESIGN}|{TABLES}"
OLD_KEY = f"20260101T000000Z-gh0|1.2.1|{DESIGN}|{TABLES}"
OLD_SIZE = 1000          # the 'old workbook' on the release; the new test workbook is a few hundred bytes


class WB:
    """A throwaway workspace (git clone of a bare 'origin' with NFL/04-data/status.csv and the exporter source),
    a release store, and stand-in gh, curl, sleep and export."""

    def __init__(self, tmp_path, name):
        import sys
        need_tools("git", "jq")
        self.name, self.tmp = name, tmp_path
        self.remote = tmp_path / "origin.git"
        git("init", "-q", "--bare", "-b", "main", str(self.remote), cwd=tmp_path)
        seed = tmp_path / "seed"
        (seed / "NFL" / "03-pipeline" / "nflpipe").mkdir(parents=True)
        (seed / "NFL" / "04-data").mkdir(parents=True)
        (seed / "NFL" / "04-data" / "status.csv").write_text(STATUS)
        (seed / "NFL" / "04-data" / "old_file.csv").write_text("a\n")
        (seed / "NFL" / "03-pipeline" / "nflpipe" / "export_xlsx.py").write_text(f'"""x"""\nWORKBOOK_VERSION = "{DESIGN}"\nTABLES_VERSION = "{TABLES}"\nOTHER = 1\n')
        git("init", "-q", "-b", "main", cwd=seed)
        git("add", "-A", cwd=seed)
        git("commit", "-q", "-m", "seed", cwd=seed)
        git("remote", "add", "origin", f"file://{self.remote}", cwd=seed)
        git("push", "-q", "origin", "main", cwd=seed)
        self.ws = tmp_path / "ws"
        git("clone", "-q", "--depth", "1", f"file://{self.remote}", str(self.ws), cwd=tmp_path)
        self.sha = git("rev-parse", "HEAD", cwd=self.ws)
        self.state = tmp_path / "gh-state"
        self.state.mkdir()
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        (self.bin / "gh").write_text(GH_RELEASE_STUB)
        (self.bin / "curl").write_text(CURL_STUB)
        (self.bin / "python").write_text(EXPORT_PYTHON)
        (self.bin / "sleep").write_text('#!/bin/sh\necho "$1" >> "$GH_STATE/sleeps"\n')       # retries without waiting
        for f in self.bin.iterdir():
            f.chmod(0o755)
        self.real_py = sys.executable
        self.log = tmp_path / "python.log"
        self.log.write_text("")
        self.details = tmp_path / "details.md"
        self.details.write_text("")

    # -- the release store
    def load_state(self):
        import json
        f = self.state / "state.json"
        return json.loads(f.read_text()) if f.exists() else {"releases": [], "next_id": 100, "n": {}}

    def save_state(self, st):
        import json
        (self.state / "state.json").write_text(json.dumps(st))

    def release(self, assets=(), body="", draft=False, tag=WB_TAG):
        st = self.load_state()
        rel = {"id": 50 + len(st["releases"]), "tag_name": tag, "draft": draft, "prerelease": True, "body": body, "assets": []}
        for i, a in enumerate(assets):
            spec = a if isinstance(a, dict) else {"name": a}
            rel["assets"].append({"id": 70 + 10 * len(st["releases"]) + i, "size": OLD_SIZE, "state": "uploaded", **spec})
        st["releases"].append(rel)
        self.save_state(st)

    @property
    def rel(self):
        return next(r for r in self.load_state()["releases"] if r["tag_name"] == WB_TAG)

    def asset_names(self):
        return sorted(a["name"] for a in self.rel["assets"])

    def served(self, name=WB_ASSET):
        """What the stable address of this asset answers: the size of the file it serves, or None for 'not found'."""
        st = self.load_state()
        for r in st["releases"]:
            if r["tag_name"] == WB_TAG and not r["draft"]:
                for a in r["assets"]:
                    if a["name"] == name and a["state"] == "uploaded" and a["size"] > 0:
                        return a["size"]
        return None

    @property
    def violations(self):
        f = self.state / "violations"
        return f.read_text().splitlines() if f.exists() else []

    @property
    def gh_calls(self):
        f = self.state / "log"
        return f.read_text().splitlines() if f.exists() else []

    def writes(self):
        """The gh calls that change anything."""
        return [c for c in self.gh_calls if c.startswith(("gh release create", "gh release upload", "gh release edit"))
                or "-X DELETE" in c or "-X PATCH" in c]

    @property
    def sleeps(self):
        f = self.state / "sleeps"
        return f.read_text().split() if f.exists() else []

    def advance_remote(self, status=None, delete=()):
        work = self.tmp / f"adv-{time.monotonic_ns()}"
        git("clone", "-q", f"file://{self.remote}", str(work), cwd=self.tmp)
        if status is not None:
            (work / "NFL" / "04-data" / "status.csv").write_text(status)
        for d in delete:
            (work / "NFL" / "04-data" / d).unlink()
        git("add", "-A", cwd=work)
        git("commit", "-q", "-m", "newer data", cwd=work)
        git("push", "-q", "origin", "main", cwd=work)

    # -- running the steps
    def env(self, **extra):
        env = {"GH_STATE": str(self.state), "GH_TOKEN": "t", "GH_REPO": "wes-blue/sports-analysis", "FAKE_LOG": str(self.log),
               "REAL_PY": self.real_py, "ALERT_DETAILS": str(self.details), "EXPORT_LOG": str(self.tmp / "export.log"),
               "WORKBOOK_MIN_BYTES": "100", "PLAYERS_MIN_BYTES": "100", "PLAYERS_MIN_LINES": "10",
               "SEASONS_MIN_BYTES": "50", "SEASONS_MIN_LINES": "5", "REFRESH_MIN_BYTES": "100"}
        env.update(extra)
        return env

    def step(self, step_name, expect_rc=0, cwd=None, **env):
        cwd = cwd or self.ws / "NFL" / "03-pipeline"
        return run_step(self.name, step_name, self.tmp, cwd=cwd, bin_dir=self.bin, expect_rc=expect_rc, env=self.env(**env))

    def decide(self, outcome, **kw):
        return self.step(DECIDE, OUTCOME=outcome, **kw)

    def build(self, **kw):
        return self.step(BUILD, **kw)

    def publish(self, release_exists, **kw):
        return self.step(PUBLISH_WB, cwd=self.ws, RELEASE_EXISTS=str(release_exists).lower(), WORKBOOK_KEY=KEY,
                         RUN_URL="https://github.com/wes-blue/sports-analysis/actions/runs/42",
                         NOTES_FILE=str(self.tmp / "notes.md"), **kw)

    def sizes(self):
        """The size of each of the four built files in the workspace."""
        d = self.ws / "NFL" / ".work" / "workbook"
        return {a: (d / a).stat().st_size for a in ALL_ASSETS}

    @property
    def body(self):
        return self.rel["body"]

    @property
    def summary(self):
        return (self.tmp / "summary.md").read_text()


@pytest.fixture
def wb(tmp_path, request):
    return WB(tmp_path, request.param if hasattr(request, "param") else "nfl-pipeline-weekly.yml")


def both(fn):
    return pytest.mark.parametrize("wb", PUBLISHING, indirect=True)(fn)


def live_release(wb, key=OLD_KEY, assets=ALL_ASSETS):
    """A release that already serves the four files (OLD_SIZE bytes each) built from older data."""
    wb.release(list(assets), body=f"old notes\n<!-- nfl-workbook-key: {key} -->\n")


# ---- Decide ---------------------------------------------------------------------------------------------

@both
def test_decide_first_run_after_the_merge_finds_no_release_and_builds(wb):
    out, _ = wb.decide("SKIP")                       # the merge push: `run` skipped, nothing is published yet
    assert out["build"] == "true" and out["release_exists"] == "false" and out["key"] == KEY
    assert wb.writes() == [] and "there is no nfl-workbook release" in wb.summary


@both
def test_decide_skip_with_a_current_workbook_only_reads(wb):
    wb.release(ALL_ASSETS, body=f"x\n<!-- nfl-workbook-key: {KEY} -->\n")
    out, _ = wb.decide("SKIP")
    assert out["build"] == "false" and out["release_exists"] == "true"
    assert wb.writes() == [] and wb.log.read_text() == "", "reads only: no export, no upload"
    assert all(c.startswith("gh api") for c in wb.gh_calls) and len(wb.gh_calls) == 3, wb.gh_calls


@both
@pytest.mark.parametrize("assets,body,why", [
    ([], f"<!-- nfl-workbook-key: {KEY} -->", "no finished"),                                   # an upload did not finish
    ([{"name": WB_ASSET, "state": "starter", "size": 0}, PG_ASSET, ST_ASSET, RF_ASSET], f"<!-- nfl-workbook-key: {KEY} -->", "no finished"),   # A2-02: empty asset
    (ALL_ASSETS, f"<!-- nfl-workbook-key: {OLD_KEY} -->", "not built from"),                    # an earlier build failed
    (ALL_ASSETS, "<!-- nfl-workbook-key: 20261120T233201Z-gh1|1.2.1 -->", "not built from"),    # the old two-part key
    (ALL_ASSETS, f"<!-- nfl-workbook-key: 20261120T233201Z-gh1|1.2.1|{DESIGN} -->", "not built from"),   # the three-part key of 3.002
    (ALL_ASSETS, "a hand-written note", "not built from"),
    (["something-else.xlsx"], f"<!-- nfl-workbook-key: {KEY} -->", "no finished")])
def test_decide_skip_repairs_a_missing_empty_or_stale_workbook(wb, assets, body, why):
    wb.release(assets, body=body)
    out, _ = wb.decide("SKIP")
    assert out["build"] == "true" and out["release_exists"] == "true" and why in wb.summary


@both
@pytest.mark.parametrize("missing", ALL_ASSETS)
def test_decide_any_one_missing_asset_triggers_a_build_and_is_named(wb, missing):
    """D-054: 'missing' means any of the four; the summary says which."""
    wb.release([a for a in ALL_ASSETS if a != missing], body=f"<!-- nfl-workbook-key: {KEY} -->")
    out, _ = wb.decide("SKIP")
    assert out["build"] == "true" and f"no finished {missing} " in wb.summary


@both
def test_decide_the_first_run_after_the_tables_merge_finds_only_the_workbook_and_republishes_all_four(wb):
    """The release has the 3.002 workbook under the old three-part key and none of the new assets."""
    wb.release([WB_ASSET], body=f"<!-- nfl-workbook-key: 20261120T233201Z-gh1|1.2.1|{DESIGN} -->")
    out, _ = wb.decide("SKIP")
    assert out["build"] == "true" and out["release_exists"] == "true" and out["key"] == KEY
    assert f"no finished {PG_ASSET}, {ST_ASSET}, {RF_ASSET}" in wb.summary and wb.writes() == []


@both
def test_decide_a_new_workbook_design_republishes_although_the_data_did_not_change(wb):
    """A2-07: the key carries the exporter's WORKBOOK_VERSION."""
    wb.release(ALL_ASSETS, body=f"<!-- nfl-workbook-key: {KEY} -->")
    assert wb.decide("SKIP")[0]["build"] == "false"
    exporter = wb.ws / "NFL" / "03-pipeline" / "nflpipe" / "export_xlsx.py"
    exporter.write_text(exporter.read_text().replace(f'"{DESIGN}"', '"3.002"'))
    out, _ = wb.decide("SKIP")
    assert out["build"] == "true" and out["key"] == f"20261120T233201Z-gh1|1.2.1|3.002|{TABLES}"
    exporter.write_text("OTHER = 1\n")
    wb.decide("SKIP", expect_rc=1)
    assert "WORKBOOK_VERSION" in wb.details.read_text()


@both
def test_decide_a_new_tables_design_republishes_although_the_data_did_not_change(wb):
    wb.release(ALL_ASSETS, body=f"<!-- nfl-workbook-key: {KEY} -->")
    assert wb.decide("SKIP")[0]["build"] == "false"
    exporter = wb.ws / "NFL" / "03-pipeline" / "nflpipe" / "export_xlsx.py"
    exporter.write_text(exporter.read_text().replace(f'TABLES_VERSION = "{TABLES}"', 'TABLES_VERSION = "2"'))
    out, _ = wb.decide("SKIP")
    assert out["build"] == "true" and out["key"] == f"20261120T233201Z-gh1|1.2.1|{DESIGN}|2"
    exporter.write_text(f'WORKBOOK_VERSION = "{DESIGN}"\n')
    wb.details.write_text("")
    wb.decide("SKIP", expect_rc=1)
    assert "TABLES_VERSION" in wb.details.read_text()
    exporter.write_text(f'WORKBOOK_VERSION = "{DESIGN}"\nTABLES_VERSION = "1 2"\n')
    wb.decide("SKIP", expect_rc=1)


@both
def test_decide_manual_rebuild_builds_even_when_the_release_is_current(wb):
    wb.release([WB_ASSET], body=f"<!-- nfl-workbook-key: {KEY} -->")
    out, _ = wb.decide("WORKBOOK")
    assert out["build"] == "true" and "requested by hand" in wb.summary


@both
def test_decide_a_draft_release_is_not_published_and_never_gets_a_duplicate(wb):
    """A2-06: a hand-made draft with a current key must not pass as the live workbook."""
    wb.release([WB_ASSET], body=f"<!-- nfl-workbook-key: {KEY} -->", draft=True)
    wb.decide("SKIP", expect_rc=1)
    assert "is a draft" in wb.details.read_text()
    assert wb.writes() == [] and wb.served() is None


@both
@pytest.mark.parametrize("error", ["HTTP 401: Bad credentials", "release not found", "gh: Not Found (HTTP 404)",
                                   "HTTP 403: API rate limit exceeded", "Release introuvable"])
def test_decide_unknown_is_never_treated_as_missing(wb, error):
    """A2-05: whatever the error text says (even 'release not found', or a reworded one), a failed read stops the run;
    the decision never depends on gh's wording, so no duplicate release can be created."""
    wb.decide("SKIP", expect_rc=1, GH_LIST_FAILS="99", GH_LIST_ERROR=error)
    assert "could not list the releases" in wb.details.read_text()
    assert wb.writes() == []
    assert wb.sleeps == ["5", "10"], "three tries, 5 s and 10 s apart"


@both
def test_decide_retries_its_reads(wb):
    wb.release(ALL_ASSETS, body=f"<!-- nfl-workbook-key: {KEY} -->")
    out, _ = wb.decide("SKIP", GH_LIST_FAILS="1", GH_GET_FAILS="2")
    assert out["build"] == "false", "transient 502s on the reads do not turn the run red"
    wb.decide("SKIP", expect_rc=1, GH_GET_FAILS="99")
    assert "could not read the assets" in wb.details.read_text()


@both
def test_decide_stops_on_two_releases_with_the_tag(wb):
    wb.release([WB_ASSET])
    wb.release([])
    wb.decide("SKIP", expect_rc=1)
    assert "more than one release" in wb.details.read_text()


@both
def test_decide_fails_loudly_when_status_is_missing_or_carries_odd_characters(wb):
    status = wb.ws / "NFL" / "04-data" / "status.csv"
    wb.advance_remote(status="key,value\npipeline_version,1.2.1\n")
    wb.decide("PUBLISH", expect_rc=1)
    assert "no run_id" in wb.details.read_text()
    for bad in ("x$(id)", "a b", "x\r"):          # nothing from status.csv reaches a command or the output file raw
        wb.details.write_text("")
        wb.advance_remote(status=f"key,value\nrun_id,{bad}\npipeline_version,1.2.1\n")
        wb.decide("PUBLISH", expect_rc=1)
        assert "unexpected characters" in wb.details.read_text()
    assert status.exists()


@both
def test_decide_builds_from_the_newest_data_on_main(wb):
    """A2-09: this run was queued behind another publish, so its checkout is older than main."""
    wb.release(ALL_ASSETS, body=f"<!-- nfl-workbook-key: {KEY} -->")
    newer = STATUS.replace("20261120T233201Z-gh1", "20261121T120000Z-gh2")
    wb.advance_remote(status=newer, delete=["old_file.csv"])
    data = wb.ws / "NFL" / "04-data"
    assert "gh1" in (data / "status.csv").read_text() and (data / "old_file.csv").exists()
    out, _ = wb.decide("SKIP")
    assert out["key"] == f"20261121T120000Z-gh2|1.2.1|{DESIGN}|{TABLES}" and out["build"] == "true"
    assert "gh2" in (data / "status.csv").read_text() and not (data / "old_file.csv").exists()


@both
def test_decide_stops_when_main_cannot_be_fetched(wb):
    wb.remote.rename(wb.tmp / "gone.git")
    wb.decide("SKIP", expect_rc=1)
    assert "could not fetch the latest NFL/04-data" in wb.details.read_text()
    assert wb.sleeps == ["5", "10"]


# ---- Build ----------------------------------------------------------------------------------------------

@both
def test_build_writes_the_file_and_reports_its_size(wb):
    wb.build()
    d = wb.ws / "NFL" / ".work" / "workbook"
    f = d / WB_ASSET
    assert f.is_file() and f"built, {f.stat().st_size} bytes" in wb.summary
    assert sorted(x.name for x in d.iterdir()) == sorted(ALL_ASSETS), "workbook, two tables and the refresh workbook"
    log = wb.log.read_text()
    assert "export --data-dir ../04-data" in log and "--tables-dir ../.work/workbook" in log and "refresh-workbook --out" in log
    assert f"built {PG_ASSET}" in wb.summary and f"built {ST_ASSET}" in wb.summary


def no_built_files(wb):
    d = wb.ws / "NFL" / ".work" / "workbook"
    return not d.exists() or not any(d.iterdir())


@both
@pytest.mark.parametrize("knob,words", [
    ({"FAKE_TABLES": "bom"}, "does not start with the header season,"),
    ({"FAKE_TABLES": "empty"}, "NFL-PlayerGames.csv is missing or empty"),
    ({"FAKE_TABLES": "nofile"}, "NFL-PlayerGames.csv is missing or empty"),
    ({"FAKE_TABLES": "short", "PLAYERS_MIN_BYTES": "10"}, "NFL-PlayerGames.csv has only 3 lines"),
    ({"PLAYERS_MIN_BYTES": "1000000"}, "NFL-PlayerGames.csv is only"),
    ({"SEASONS_MIN_BYTES": "1000000"}, "NFL-SeasonTotals.csv is only"),
    ({"SEASONS_MIN_LINES": "1000"}, "NFL-SeasonTotals.csv has only 21 lines"),
    ({"REFRESH_MIN_BYTES": "1000000"}, "the refresh workbook is only"),
    ({"FAKE_REFRESH": "garbage"}, "the refresh workbook is not a readable Excel workbook"),
    ({"FAKE_REFRESH": "fail"}, "refresh-workbook exited 1")])
def test_build_a_bad_table_or_refresh_workbook_is_red_and_nothing_is_kept(wb, knob, words):
    """D-054: header, size and line sanity checks on both CSV files, and the refresh workbook is a checked zip."""
    wb.build(expect_rc=1, **knob)
    assert words in wb.details.read_text()
    assert no_built_files(wb), "no file of a failed build stays for the publish step"
    assert wb.gh_calls == [] and "FAILED to build" in wb.summary


@both
def test_build_an_export_failure_writes_no_tables_and_never_reaches_the_refresh_workbook(wb):
    wb.build(expect_rc=1, FAKE_EXPORT="fail")
    assert "refresh-workbook" not in wb.log.read_text() and no_built_files(wb)


@both
def test_build_export_failure_is_red_leaves_no_file_and_names_the_cause(wb):
    wb.build(expect_rc=1, FAKE_EXPORT="fail")
    assert not (wb.ws / "NFL" / ".work" / "workbook" / WB_ASSET).exists()
    text = wb.details.read_text()
    assert "export exited 1" in text and "cannot read status.csv" in text
    assert "FAILED to build" in wb.summary
    assert wb.gh_calls == [], "nothing is uploaded after a failed build"


@both
@pytest.mark.parametrize("kind", ["garbage", "notxlsx", "badcrc"])
def test_build_a_file_that_is_not_a_workbook_is_never_kept(wb, kind):
    """A2-13 #25: not a zip, a zip without the workbook, and a zip whose member fails its checksum (testzip)."""
    wb.build(expect_rc=1, FAKE_EXPORT=kind)
    assert not (wb.ws / "NFL" / ".work" / "workbook" / WB_ASSET).exists()
    assert "not a readable Excel workbook" in wb.details.read_text()


@both
def test_build_a_truncated_file_is_never_kept(wb):
    wb.build(expect_rc=1, WORKBOOK_MIN_BYTES="1000000")          # the workflow's own floor, against the tiny stand-in file
    assert "bytes (at least 1000000 expected)" in wb.details.read_text()
    assert not (wb.ws / "NFL" / ".work" / "workbook" / WB_ASSET).exists()


# ---- Publish: the swap of four assets ----------------------------------------------------------------------

def stage(wb, *, old=True, key=OLD_KEY):
    """Release serving four old files (or none) and four freshly built ones (a few hundred bytes each). Returns their sizes."""
    if old:
        live_release(wb, key)
    wb.build()
    return wb.sizes()


def kinds(wb):
    out = []
    for c in wb.gh_calls:
        if "-X DELETE" in c:
            out.append("delete")
        elif "-X PATCH" in c:
            out.append("patch")
        elif c.startswith("gh release "):
            out.append(c.split()[2])
    return out


def served_all(wb):
    return {a: wb.served(a) for a in ALL_ASSETS}


def old_all():
    return {a: OLD_SIZE for a in ALL_ASSETS}


@both
def test_publish_first_run_creates_the_release_and_the_links_work(wb):
    """The very first publish: no release. Afterwards the four stable addresses serve the new files."""
    sizes = stage(wb, old=False)
    wb.publish(False)
    calls = wb.gh_calls
    create = next(c for c in calls if c.startswith("gh release create"))
    assert WB_TAG in create and f"--target {wb.sha}" in create and "--prerelease" in create and "--latest=false" in create
    assert kinds(wb) == ["create"] + ["upload"] * 4 + ["patch"] * 4 + ["edit"], kinds(wb)
    assert wb.asset_names() == sorted(ALL_ASSETS) and served_all(wb) == sizes and wb.violations == []
    assert wb.rel["prerelease"] is True
    body = wb.body
    assert "season 2026, week 11 (REG)" in body and "20261120T233201Z-gh1" in body and "13 passed, 1 warned, 0 failed" in body
    for a in ALL_ASSETS:
        assert f"{DL_BASE}/{a}" in body, a
    assert WB_URL in body and f"<!-- nfl-workbook-key: {KEY} -->" in body and "CC BY 4.0" in body
    assert "wes-blue" not in body.replace("wes-blue/sports-analysis", "")
    for a in ALL_ASSETS:
        assert f"published at {DL_BASE}/{a}" in wb.summary
    assert len((wb.state / "curl.log").read_text().splitlines()) == 4, "one ranged request per public link"


@both
def test_publish_replaces_all_four_live_assets_without_deleting_one_before_all_are_uploaded(wb):
    sizes = stage(wb)
    wb.publish(True)
    # every new file is on the release before the first old one goes; then delete+rename pairs back to back
    assert kinds(wb) == ["upload"] * 4 + ["delete", "patch"] * 4 + ["edit"], kinds(wb)
    assert not any("--clobber" in c for c in wb.gh_calls) and not any(c.startswith("gh release create") for c in wb.gh_calls)
    assert wb.violations == [] and wb.asset_names() == sorted(ALL_ASSETS) and served_all(wb) == sizes
    assert f"nfl-workbook-key: {KEY} " in wb.body and "OLD" not in wb.body and OLD_KEY not in wb.body
    assert len(wb.state.joinpath("curl.log").read_text().splitlines()) == 4


@both
def test_publish_the_first_run_after_the_merge_has_the_workbook_but_not_the_three_new_assets(wb):
    """The live release holds the workbook only. The three new assets have no old file to delete; all four end up served."""
    wb.release([WB_ASSET], body=f"old notes\n<!-- nfl-workbook-key: 20261120T233201Z-gh1|1.2.1|{DESIGN} -->\n")
    out, _ = wb.decide("SKIP")
    assert out["build"] == "true" and out["key"] == KEY
    wb.build()
    sizes = wb.sizes()
    wb.publish(True)
    assert kinds(wb) == ["upload"] * 4 + ["delete", "patch"] + ["patch"] * 3 + ["edit"], kinds(wb)
    assert wb.violations == [] and wb.asset_names() == sorted(ALL_ASSETS) and served_all(wb) == sizes
    assert f"nfl-workbook-key: {KEY} " in wb.body
    assert wb.decide("SKIP")[0]["build"] == "false", "the next scheduled run finds everything current"


@both
def test_publish_upload_failure_leaves_the_old_files_serving(wb):
    """A2-02: the stand-in deletes before it uploads (like gh --clobber would); the swap never gets there."""
    stage(wb)
    wb.publish(True, expect_rc=1, GH_UPLOAD_FAILS="99", GH_UPLOAD_LEAVES_STARTER="1")
    assert sum(c.startswith("gh release upload") for c in wb.gh_calls) == 3
    assert "10" in wb.sleeps and "20" in wb.sleeps, "backoff between the upload attempts"
    assert wb.asset_names() == sorted(ALL_ASSETS), "the half-uploaded temporary asset was cleaned up, the old files are untouched"
    assert served_all(wb) == old_all() and wb.violations == []
    assert OLD_KEY in wb.body, "notes must not claim the new data until the upload worked"
    text = wb.details.read_text()
    assert "could not upload the new NFL-Analysis.xlsx" in text and "no asset already on the release was touched" in text and "workbook-42-1" in text


@both
def test_publish_a_failed_upload_of_a_later_asset_removes_the_earlier_temporary_files_and_deletes_nothing(wb):
    stage(wb)
    wb.publish(True, expect_rc=1, GH_UPLOAD_FAILS="99", GH_UPLOAD_FAIL_NAME="NFL-SeasonTotals.next.csv")
    assert wb.asset_names() == sorted(ALL_ASSETS), "the two temporary files that did upload were removed again"
    assert served_all(wb) == old_all() and wb.violations == [], "no live asset was deleted, so none was ever missing"
    assert "could not upload the new NFL-SeasonTotals.csv" in wb.details.read_text()
    assert OLD_KEY in wb.body


@both
def test_publish_upload_is_retried_and_a_second_attempt_succeeds(wb):
    sizes = stage(wb)
    wb.publish(True, GH_UPLOAD_FAILS="1", GH_UPLOAD_LEAVES_STARTER="1")          # the failed first try leaves an empty asset
    assert sum(c.startswith("gh release upload") for c in wb.gh_calls) == 5
    assert wb.asset_names() == sorted(ALL_ASSETS) and served_all(wb) == sizes and wb.violations == []


@both
@pytest.mark.parametrize("leftover_name", NEXT_NAMES)
@pytest.mark.parametrize("leftover", [{"state": "uploaded", "size": 7}, {"state": "starter", "size": 0}])
def test_publish_removes_a_temporary_asset_left_by_a_dead_run(wb, leftover, leftover_name):
    sizes = stage(wb, old=False)
    wb.release(ALL_ASSETS + [{"name": leftover_name, **leftover}], body=f"<!-- nfl-workbook-key: {OLD_KEY} -->")
    wb.publish(True)
    assert wb.asset_names() == sorted(ALL_ASSETS) and served_all(wb) == sizes and wb.violations == []


@both
@pytest.mark.parametrize("short", [None, "NFL-PlayerGames.next.csv", "NFL-Analysis-Refresh.next.xlsx"])
def test_publish_an_incomplete_upload_is_not_swapped_in_and_blocks_every_delete(wb, short):
    """Verification covers EVERY upload before the first delete: a bad last file stops the swap of the good first ones."""
    stage(wb)
    extra = {"GH_UPLOAD_SHORT_NAME": short} if short else {}
    wb.publish(True, expect_rc=1, GH_UPLOAD_SHORT="1", **extra)       # 'succeeds' but the asset stays empty (state starter)
    assert "not on the release as one complete asset" in wb.details.read_text()
    assert wb.asset_names() == sorted(ALL_ASSETS) and served_all(wb) == old_all() and wb.violations == []
    assert OLD_KEY in wb.body


@both
def test_publish_failing_delete_of_one_old_asset_keeps_it_and_still_swaps_the_others(wb):
    sizes = stage(wb)
    wb.publish(True, expect_rc=1, GH_DELETE_FAILS="99", GH_DELETE_FAIL_NAME=PG_ASSET)
    assert wb.served(PG_ASSET) == OLD_SIZE and "NFL-PlayerGames.next.csv" in wb.asset_names()
    for a in (WB_ASSET, ST_ASSET, RF_ASSET):
        assert wb.served(a) == sizes[a], a
    text = wb.details.read_text()
    assert f"could not remove the old {PG_ASSET}" in text and "left in place" in text and OLD_KEY in wb.body
    assert not any(c.startswith("gh release edit") for c in wb.gh_calls) and not (wb.state / "curl.log").exists()
    # the next run repairs it: the key in the notes is still the old one
    assert wb.decide("SKIP")[0]["build"] == "true"
    wb.build()
    wb.publish(True)
    assert wb.asset_names() == sorted(ALL_ASSETS) and served_all(wb) == wb.sizes() and f"nfl-workbook-key: {KEY} " in wb.body


@both
def test_publish_rename_retried_then_succeeds(wb):
    sizes = stage(wb)
    wb.publish(True, GH_PATCH_FAILS="2")
    assert sum("-X PATCH" in c for c in wb.gh_calls) == 6
    assert wb.asset_names() == sorted(ALL_ASSETS) and served_all(wb) == sizes


@both
def test_publish_when_the_rename_is_refused_each_new_file_is_uploaded_again_under_its_stable_name(wb):
    """The one step GitHub alone can confirm (PATCH on an asset of a pre-release). If it fails, the dark window is an upload."""
    sizes = stage(wb)
    wb.publish(True, GH_PATCH_FAILS="99")
    assert sum("-X PATCH" in c for c in wb.gh_calls) == 20
    clobber = [c for c in wb.gh_calls if "--clobber" in c]
    assert len(clobber) == 4 and all(c.endswith(f"{a} --clobber") for c, a in zip(clobber, ALL_ASSETS))
    assert wb.asset_names() == sorted(ALL_ASSETS), "the temporary assets are gone"
    assert served_all(wb) == sizes and wb.violations == []


@both
def test_publish_when_even_the_fallback_fails_that_link_is_dark_until_the_next_run_repairs_it(wb):
    stage(wb)
    wb.publish(True, expect_rc=1, GH_PATCH_FAILS="99", GH_UPLOAD_FAILS="99", GH_UPLOAD_FAIL_NAME=WB_ASSET)
    assert wb.served() is None, "worst case: the old file was already removed and the rename never worked"
    assert wb.served(PG_ASSET) == wb.sizes()[PG_ASSET], "the other assets were still swapped"
    assert "NFL-Analysis.next.xlsx" in wb.asset_names()
    text = wb.details.read_text()
    assert "could not be renamed" in text and "not found until the next run puts it back" in text
    assert OLD_KEY in wb.body
    # the next scheduled run: SKIP sees no finished workbook, builds, removes the leftover and swaps
    out, _ = wb.decide("SKIP")
    assert out["build"] == "true" and f"no finished {WB_ASSET} " in wb.summary
    wb.build()
    wb.publish(True)
    assert wb.asset_names() == sorted(ALL_ASSETS) and served_all(wb) == wb.sizes() and f"nfl-workbook-key: {KEY} " in wb.body


@both
def test_publish_asks_for_every_public_address_and_waits_for_the_cdn(wb):
    sizes = stage(wb)
    wb.publish(True, CURL_404_FIRST="2")
    assert wb.sleeps.count("5") >= 1 and "10" in wb.sleeps
    assert len((wb.state / "curl.log").read_text().splitlines()) == 6 and served_all(wb) == sizes
    urls = [ln.split()[-1] for ln in (wb.state / "curl.log").read_text().splitlines()]
    assert sorted(set(urls)) == sorted(f"{DL_BASE}/{a}" for a in ALL_ASSETS)
    assert f"nfl-workbook-key: {KEY} " in wb.body


@both
def test_publish_a_dead_public_address_is_red_and_leaves_the_old_key_in_the_notes(wb):
    """A2-06: the API said fine, the address says 404 (an immutable-release rule, a wrong name): never report success."""
    stage(wb)
    wb.publish(True, expect_rc=1, CURL_CODE="404")
    assert len((wb.state / "curl.log").read_text().splitlines()) == 20, "five tries for each of the four links"
    text = wb.details.read_text()
    assert "answers 404" in text and all(f"{DL_BASE}/{a}" in text for a in ALL_ASSETS)
    assert OLD_KEY in wb.body and not any(c.startswith("gh release edit") for c in wb.gh_calls)
    assert wb.decide("SKIP")[0]["build"] == "true", "the next run builds and publishes it again"


@both
@pytest.mark.parametrize("bad", [PG_ASSET, ST_ASSET, RF_ASSET])
def test_publish_one_dead_link_alone_turns_the_run_red_and_keeps_the_old_notes(wb, bad):
    stage(wb)
    wb.publish(True, expect_rc=1, CURL_BAD_NAME=bad)
    text = wb.details.read_text()
    assert f"{bad} is on the release but {DL_BASE}/{bad} answers 404" in text
    assert text.count("answers 404") == 1
    assert OLD_KEY in wb.body and not any(c.startswith("gh release edit") for c in wb.gh_calls)


@both
def test_publish_notes_update_is_retried_and_a_persistent_failure_self_repairs(wb):
    stage(wb)
    wb.publish(True, GH_EDIT_FAILS="2")
    assert sum(c.startswith("gh release edit") for c in wb.gh_calls) == 3 and f"nfl-workbook-key: {KEY} " in wb.body


@both
def test_publish_notes_failure_after_the_swap_is_red_but_the_links_work(wb):
    sizes = stage(wb)
    wb.publish(True, expect_rc=1, GH_EDIT_FAILS="99")
    assert "links work" in wb.details.read_text() and "notes could not be updated" in wb.details.read_text()
    assert served_all(wb) == sizes
    assert wb.decide("SKIP")[0]["build"] == "true", "the old key is still in the notes: the next run rebuilds once"


@both
def test_publish_release_creation_is_retried_and_never_duplicated(wb):
    stage(wb, old=False)
    wb.publish(False, GH_CREATE_FAILS="1", GH_CREATE_PHANTOM="1")      # the call failed but the release exists
    assert sum(c.startswith("gh release create") for c in wb.gh_calls) == 1
    assert len(wb.load_state()["releases"]) == 1 and wb.asset_names() == sorted(ALL_ASSETS)


@both
def test_publish_release_creation_failure_uploads_nothing(wb):
    stage(wb, old=False)
    wb.publish(False, expect_rc=1, GH_CREATE_FAILS="3")
    assert sum(c.startswith("gh release create") for c in wb.gh_calls) == 3
    assert not any(c.startswith("gh release upload") for c in wb.gh_calls)
    assert "could not create the release" in wb.details.read_text() and wb.served() is None


@both
def test_publish_a_failed_read_of_the_release_touches_nothing(wb):
    stage(wb)
    wb.publish(True, expect_rc=1, GH_LIST_FAILS="99")
    assert wb.writes() == [] and served_all(wb) == old_all()


@both
def test_publish_a_draft_release_is_not_built_on(wb):
    wb.release(ALL_ASSETS, body="x", draft=True)
    wb.build()
    wb.publish(True, expect_rc=1)
    assert "is a draft" in wb.details.read_text() and wb.writes() == [] and wb.served() is None


@both
def test_publish_the_stand_in_would_catch_a_delete_before_all_uploads(wb):
    """Self-check of the release stand-in: deleting a live asset while a new file is missing is recorded as a violation."""
    live_release(wb)
    wb.release(["NFL-Analysis.next.xlsx"], tag="other")      # an unrelated release must not matter
    st = wb.load_state()
    rel = next(r for r in st["releases"] if r["tag_name"] == WB_TAG)
    rid = next(a["id"] for a in rel["assets"] if a["name"] == WB_ASSET)
    done = subprocess.run([str(wb.bin / "gh"), "api", "-X", "DELETE", f"repos/wes-blue/sports-analysis/releases/assets/{rid}"],
                          env={**os.environ, **wb.env()}, capture_output=True, text=True)
    assert done.returncode == 0 and any("deleted before every new file" in v for v in wb.violations)


# ---- the other steps of the weekly and monthly workflows --------------------------------------------------

def test_resolve_workbook_only_skips_resolve_and_the_stray_file_check(tmp_path):
    root = project_tree(tmp_path)
    (root / "NFL" / "02-config" / "scoring_weights (1).csv").write_text("x\n")
    outputs, calls = resolve(tmp_path, root, event="workflow_dispatch", workbook_only="true", force="true", seasons="all")
    assert outputs["decision"] == "workbook" and outputs["force"] == "false" and calls == ""
    assert "pipeline did not run" in outputs["reason"]


def test_resolve_workbook_only_off_main_says_plainly_that_it_did_nothing(tmp_path):
    """A2-10: it used to end green and claim a rebuild."""
    outputs, calls = resolve(tmp_path, project_tree(tmp_path), event="workflow_dispatch", ref="refs/heads/test", workbook_only="true")
    assert outputs["decision"] == "error" and outputs["dry_run"] == "true" and calls == ""
    assert "NOTHING was rebuilt" in outputs["reason"] and "test" in outputs["reason"] and "main" in outputs["reason"]
    _o, done = run_step("nfl-pipeline-weekly.yml", RESOLVE, tmp_path / "x", cwd=project_tree(tmp_path / "x") / "NFL" / "03-pipeline",
                        env={"EVENT": "workflow_dispatch", "REF": "refs/heads/test", "SHA": "abc", "IN_WORKBOOK_ONLY": "true",
                             "IN_SEASONS": "", "IN_FORCE": "", "IN_DRY_RUN": ""}, bin_dir=make_bin(tmp_path / "x", python="fake"))
    assert "::error title=Workbook only: nothing done::" in done.stdout and "rebuilt from the data on main" not in done.stdout


def test_record_outcome_maps_workbook_only_to_a_green_outcome_and_a_refused_one_to_red(tmp_path):
    root = project_tree(tmp_path)
    common = {"RUN_OUTCOME": "", "RUN_RC": "", "DRY_RUN": "false", "EVENT": "workflow_dispatch",
              "RUN_LOG": str(tmp_path / "none.log"), "ALERT_DETAILS": str(tmp_path / "d.md")}
    outputs, _ = run_step("nfl-pipeline-weekly.yml", "Record outcome", tmp_path, cwd=root / "NFL" / "03-pipeline",
                          bin_dir=make_bin(tmp_path, python="real"),
                          env=dict(common, DECISION="workbook", RESOLVE_REASON="workbook rebuild requested by hand"))
    assert outputs["outcome"] == "WORKBOOK"
    outputs, _ = run_step("nfl-pipeline-weekly.yml", "Record outcome", tmp_path, cwd=root / "NFL" / "03-pipeline",
                          bin_dir=make_bin(tmp_path, python="real"),
                          env=dict(common, DECISION="error", RESOLVE_REASON="workbook_only was started on test, not main, so NOTHING was rebuilt"))
    assert outputs["outcome"] == "ERROR" and "NOTHING was rebuilt" in (tmp_path / "d.md").read_text()


def test_record_outcome_skip_after_a_push_says_the_pipeline_ran(tmp_path):
    root = project_tree(tmp_path)
    _o, done = run_step("nfl-pipeline-weekly.yml", "Record outcome", tmp_path, cwd=root / "NFL" / "03-pipeline",
                        bin_dir=make_bin(tmp_path, python="real"),
                        env={"DECISION": "run", "RUN_OUTCOME": "SKIP", "RUN_RC": "3", "DRY_RUN": "false", "EVENT": "push",
                             "RESOLVE_REASON": "a push to main changed the pipeline code", "RUN_LOG": str(tmp_path / "none.log"),
                             "ALERT_DETAILS": str(tmp_path / "d.md")})
    assert "the pipeline ran and found nothing to publish" in done.stdout


def test_monthly_workbook_only_does_not_run_the_pipeline(tmp_path):
    root = project_tree(tmp_path)
    bin_dir = make_bin(tmp_path, python="fake")
    log = tmp_path / "python.log"
    log.write_text("")
    env = {"IN_DRY_RUN": "", "IN_WORKBOOK_ONLY": "true", "REF": "refs/heads/main", "EVENT_SCHEDULE": "",
           "TRIGGER": "workflow_dispatch-monthly", "FAKE_LOG": str(log),
           "RUN_LOG": str(tmp_path / "run.log"), "ALERT_DETAILS": str(tmp_path / "d.md")}
    outputs, _ = run_step("nfl-pipeline-monthly.yml", "Run pipeline (all seasons)", tmp_path,
                          cwd=root / "NFL" / "03-pipeline", bin_dir=bin_dir, env=env)
    assert outputs == {"dry_run": "false", "outcome": "WORKBOOK"} and log.read_text() == ""
    # A2-10: off main it cannot publish, so it says so (red) instead of reporting a rebuild
    outputs, done = run_step("nfl-pipeline-monthly.yml", "Run pipeline (all seasons)", tmp_path,
                             cwd=root / "NFL" / "03-pipeline", bin_dir=bin_dir, env=dict(env, REF="refs/heads/test"))
    assert outputs == {"dry_run": "true", "outcome": "ERROR"} and log.read_text() == ""
    assert "NOTHING was rebuilt" in (tmp_path / "d.md").read_text() and "rebuilt from the data on main" not in done.stdout


@pytest.mark.parametrize("name", PUBLISHING)
def test_workbook_outcome_alert_is_green_and_leaves_an_open_issue(tmp_path, name):
    assert run_alert(tmp_path, name, "WORKBOOK") == {}
    run_alert(tmp_path, name, "HOLD")
    assert run_alert(tmp_path, name, "WORKBOOK") == {doc_label(name): "1"}
    assert run_alert(tmp_path, name, "PUBLISH", job_status="failure") == {doc_label(name): "1"}   # workbook step failed: red


@pytest.mark.parametrize("name", PUBLISHING)
@pytest.mark.parametrize("failed,words", [
    ({"WBCHECK_OUTCOME": "failure"}, "the workbook check failed"),
    ({"WBBUILD_OUTCOME": "failure"}, "the workbook could not be built"),
    ({"WBPUBLISH_OUTCOME": "failure"}, "the workbook could not be published"),
    ({"COMMIT_OUTCOME": "failure"}, "the data could not be committed to main"),
    ({}, "a step after the pipeline failed")])
def test_alert_heading_says_what_failed_not_ended_skip(tmp_path, name, failed, words):
    """A2-04: a green pipeline result with a red job used to read 'ended SKIP (job status: failure)'."""
    run_alert(tmp_path, name, "SKIP", job_status="failure", **failed)
    log = (tmp_path / "gh-state" / "log").read_text()
    assert words in log and "pipeline result SKIP" in log and "ended **SKIP**" not in log
    (tmp_path / "b").mkdir()
    run_alert(tmp_path / "b", name, "HOLD", job_status="failure")
    assert "**HOLD**" in (tmp_path / "b" / "gh-state" / "log").read_text()


def doc_label(name):
    return load(name)[1]["env"]["ALERT_LABEL"]


def test_monthly_alert_names_a_failed_heartbeat(tmp_path):
    run_alert(tmp_path, "nfl-pipeline-monthly.yml", "SKIP", job_status="failure", HEARTBEAT_OUTCOME="failure")
    assert "the heartbeat commit could not be saved" in (tmp_path / "gh-state" / "log").read_text()


def test_guide_tells_the_owner_where_the_workbook_is():
    text = GUIDE.read_text(encoding="utf-8")
    assert WB_URL in text
    assert "workbook_only" in text
    for stale in ("Refresh All", "Power Query", "Refresh the workbook"):
        assert stale not in text, f"the guide must not tell the owner to refresh: {stale!r}"


def test_guide_first_time_steps_describe_this_merge_and_the_failure_behaviour():
    """R2-01, R2-02, R2-03, R2-17 and A2-02: the guide says what the merge starts, when the link works, what the swap does."""
    text = GUIDE.read_text(encoding="utf-8")
    sec2 = text.split("## 2. ")[1].split("## 3. ")[0]
    assert sec2.index("Watch the workbook get built") < sec2.index("Check that Actions is allowed"), "the step that makes the link work comes first"
    assert "actions/workflows/nfl-pipeline-weekly.yml" in text, "points at the run on the Actions tab"
    assert "there is no nfl-workbook release yet" in sec2 and "When the run has a green tick, the link works" in sec2
    assert "counts as a config change, so two runs" not in text and "a newer commit by **github-actions[bot]** named" not in sec2.split("4. ")[0]
    assert "**If the link says not found.**" in text and "Rebuild only the workbook" in text.split("**If the link says not found.**")[1][:900]
    assert "20 MB" not in text and "about 8 MB" in text, "the guide states the size of the 3.002 file"
    assert "uploaded first under a temporary name" in text and "never leaves the link empty" in text
    assert "deleted only after the new one is safely on the release" in text and "the link keeps giving the old workbook" in text
    assert "Re-run failed jobs" in text and "workbook-RUN-ATTEMPT" in text
    assert "NOTHING was rebuilt" in text, "workbook_only from a branch is red, and the guide says so"
    assert "right-hand side" not in text, "R2-17: the sidebar claim is unverified"
    for stale in ("the link above gives the new workbook. During the few seconds", "only the download link still gives the previous workbook",
                  "--clobber"):
        assert stale not in text, stale


def test_guide_describes_the_four_assets_the_key_and_how_to_find_a_missing_one():
    """D-054: the maintainer guide names every asset and address, the four-field key, workbook_only and the missing-asset line."""
    text = GUIDE.read_text(encoding="utf-8")
    for a in ALL_ASSETS:
        assert f"{DL_BASE}/{a}" in text, a
    assert "nfl-workbook-key: <run id>|<pipeline version>|<workbook design>|<tables design>" in text
    assert "WORKBOOK_VERSION" in text and "TABLES_VERSION" in text
    assert "Which asset is missing?" in text and "the release has no finished NFL-PlayerGames.csv" in text
    assert "workbook_only" in text and "also rebuilds" not in text.split("workbook_only**:")[0] and "rebuilds and republishes all four files" in text
    assert "All four uploads are checked" in text and "before anything old is touched" in text
    assert "The merge that added the two CSV files" in text and "three fields instead of four" in text
