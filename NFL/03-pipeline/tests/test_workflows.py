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
WB_TAG = "nfl-workbook"
WB_ASSET = "NFL-Analysis.xlsx"
WB_URL = f"https://github.com/wes-blue/sports-analysis/releases/download/{WB_TAG}/{WB_ASSET}"
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
    assert "continue-on-error" not in code


def test_scoped_to_the_nfl_folder(wf):
    """A future NBA/ folder and its nba-pipeline-*.yml files never start, or get confused with, these."""
    name, text, doc = wf
    assert doc["defaults"]["run"]["working-directory"] == WORKDIR
    for event in ("push", "pull_request"):
        spec = triggers(doc).get(event)
        if isinstance(spec, dict):
            for p in spec.get("paths", []):
                assert p.lstrip("!").startswith(("NFL/", ".github/workflows/nfl-pipeline-")), f"{name}: {p}"
            for other in ("NBA/02-config/leagues.csv", "NBA/03-pipeline/nbapipe/run.py",
                          ".github/workflows/nba-pipeline-weekly.yml", "README.md", "00-Governance/MEMORY.md"):
                assert not path_filter_matches(spec.get("paths", []), other), f"{name} {event} fires for {other}"
    groups = [doc.get("concurrency", {}).get("group", "")] + [j.get("concurrency", {}).get("group", "") for j in doc["jobs"].values()]
    assert all(g == "" or g.startswith("nfl-") for g in groups)
    env = doc.get("env", {})
    if "ALERT_LABEL" in env:
        assert env["ALERT_LABEL"].startswith("nfl-pipeline-alert-")
    assert "Personal/" not in text and "20-Projects" not in text, "path from the old private repository"


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
                GITHUB_RUN_ID="42", RUNNER_TEMP=str(tmp_path))
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


def test_resolve_step_push_runs_with_force_and_skips_resolve(tmp_path):
    outputs, calls = resolve(tmp_path, project_tree(tmp_path), event="push")
    assert outputs["decision"] == "run" and outputs["force"] == "true" and outputs["seasons"] == "current"
    assert outputs["dry_run"] == "false"
    assert "abcdef1" in outputs["reason"]
    assert calls == "", "a config push must not depend on resolve's verdict"


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


def run_alert(tmp_path, name, outcome, job_status="success", dry_run="", details=""):
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
               EVENT="schedule", SHA="abcdef1234", ALERT_DETAILS=str(detail_file))
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


# ---- the workbook release (CONTRACTS.md section 13.5, decision D-042) -------------------------------

def dry_step_id(name):
    return "resolve" if name == "nfl-pipeline-weekly.yml" else "outcome"


@pytest.mark.parametrize("name", PUBLISHING)
def test_workbook_steps_exist_in_order_and_after_the_data_commit(name):
    _text, doc = load(name)
    names = [s.get("name") for _j, s in steps(doc)]
    order = ["Commit 04-data", DECIDE, BUILD, PUBLISH_WB, KEEP_WB, "Update the rolling alert issue"]
    assert [names.index(n) for n in order] == sorted(names.index(n) for n in order)
    assert doc["env"]["WORKBOOK_TAG"] == WB_TAG and doc["env"]["WORKBOOK_ASSET"] == WB_ASSET


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
    assert keep["with"]["retention-days"] == 7 and keep["with"]["name"] == "workbook-${{ github.run_id }}"
    assert keep["with"]["path"] == "NFL/.work/workbook/NFL-Analysis.xlsx"


@pytest.mark.parametrize("name", PUBLISHING)
def test_workbook_export_command_and_token_scope(name):
    _text, doc = load(name)
    build = step_named(doc, BUILD)
    assert "python -m nflpipe export --data-dir ../04-data --out" in build["run"]
    assert "github.token" not in str(build.get("env", {})), "the export step needs no token"
    assert "gh " not in build["run"]
    for step_name in (DECIDE, PUBLISH_WB):
        assert step_named(doc, step_name)["env"]["GH_TOKEN"] == "${{ github.token }}"
    assert step_named(doc, KEEP_WB).get("env") is None


@pytest.mark.parametrize("name", PUBLISHING)
def test_release_is_a_prerelease_never_latest_and_needs_no_extra_permission(name):
    text, doc = load(name)
    script = step_named(doc, PUBLISH_WB)["run"]
    for fragment in ('gh release create "$WORKBOOK_TAG"', '--target "$(git rev-parse HEAD)"', "--prerelease",
                     "--latest=false", 'gh release upload "$WORKBOOK_TAG" "$WORKBOOK_FILE" --clobber',
                     'gh release edit "$WORKBOOK_TAG" --notes-file', "for attempt in 1 2 3"):
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
def test_notes_are_updated_only_after_the_upload(name):
    """If the notes (which carry the build key) changed first, a failed upload would look 'current' to the next run."""
    script = step_named(load(name)[1], PUBLISH_WB)["run"]
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


# -- executing the workbook steps against a stand-in gh (a small release store) and a stand-in export --

GH_RELEASE_STUB = r"""#!/usr/bin/env bash
# Fake GitHub CLI for releases. State dir $GH_STATE: `release` exists when the release does, `assets` lists asset
# names, `body` holds the notes, `files/` the uploaded files. Knobs: GH_VIEW_ERROR, GH_CREATE_FAILS,
# GH_UPLOAD_FAILS (number of failing calls), GH_EDIT_FAILS.
set -u
printf 'gh' >> "$GH_STATE/log"; printf ' %q' "$@" >> "$GH_STATE/log"; echo >> "$GH_STATE/log"
[[ -n "${GH_TOKEN:-}" && -n "${GH_REPO:-}" ]] || { echo "gh: no token or repo" >&2; exit 4; }
n_fail() { local f="$GH_STATE/fails-$1" n; n=$(cat "$f" 2>/dev/null || echo 0); n=$((n+1)); echo "$n" > "$f"; echo "$n"; }
case "$1 $2" in
  "release view")
    [[ -n "${GH_VIEW_ERROR:-}" ]] && { echo "$GH_VIEW_ERROR" >&2; exit 1; }
    [[ -f "$GH_STATE/release" ]] || { echo "release not found" >&2; exit 1; }
    case "$*" in
      *"--json assets"*) cat "$GH_STATE/assets" 2>/dev/null; exit 0 ;;
      *"--json body"*)   cat "$GH_STATE/body" 2>/dev/null; exit 0 ;;
    esac ;;
  "release create")
    [[ "$(n_fail create)" -le "${GH_CREATE_FAILS:-0}" ]] && { echo "HTTP 500" >&2; exit 1; }
    : > "$GH_STATE/release"; : > "$GH_STATE/assets"; mkdir -p "$GH_STATE/files"
    while [[ $# -gt 0 ]]; do [[ "$1" == "--notes" ]] && echo "$2" > "$GH_STATE/body"; shift; done; exit 0 ;;
  "release upload")
    [[ -f "$GH_STATE/release" ]] || { echo "release not found" >&2; exit 1; }
    [[ "$(n_fail upload)" -le "${GH_UPLOAD_FAILS:-0}" ]] && { echo "HTTP 502" >&2; exit 1; }
    name="$(basename "$4")"; [[ "$*" == *"--clobber"* ]] || { echo "already exists" >&2; exit 1; }
    grep -qxF "$name" "$GH_STATE/assets" || echo "$name" >> "$GH_STATE/assets"
    mkdir -p "$GH_STATE/files"; cp "$4" "$GH_STATE/files/$name"; exit 0 ;;
  "release edit")
    [[ "$(n_fail edit)" -le "${GH_EDIT_FAILS:-0}" ]] && { echo "HTTP 500" >&2; exit 1; }
    while [[ $# -gt 0 ]]; do [[ "$1" == "--notes-file" ]] && cp "$2" "$GH_STATE/body"; shift; done; exit 0 ;;
esac
echo "unexpected gh call: $*" >&2; exit 2
"""

EXPORT_PYTHON = r"""#!/usr/bin/env bash
# Stand-in for the colleague's `python -m nflpipe export`: FAKE_EXPORT=ok writes a tiny valid package, notxlsx a zip without a workbook,
# garbage writes a non-zip file, fail exits 1. Every other call goes to the real interpreter.
if [[ "$1 $2 $3" == "-m nflpipe export" ]]; then
  echo "python $*" >> "$FAKE_LOG"
  out=""; while [[ $# -gt 0 ]]; do [[ "$1" == "--out" ]] && out="$2"; shift; done
  case "${FAKE_EXPORT:-ok}" in
    fail) echo "export: ERROR: cannot read status.csv"; exit 1 ;;
    garbage) mkdir -p "$(dirname "$out")"; echo "not a zip" > "$out"; exit 0 ;;
    notxlsx) mkdir -p "$(dirname "$out")"
       "$REAL_PY" -c 'import sys, zipfile
z = zipfile.ZipFile(sys.argv[1], "w"); z.writestr("readme.txt", "hello"); z.close()' "$out"; exit 0 ;;
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
KEY = "20261120T233201Z-gh1|1.2.1"


class WB:
    """A throwaway workspace (git repo with NFL/04-data/status.csv), a release store and stand-in tools."""

    def __init__(self, tmp_path, name):
        import sys
        self.name, self.tmp = name, tmp_path
        self.ws = tmp_path / "ws"
        (self.ws / "NFL" / "03-pipeline").mkdir(parents=True)
        (self.ws / "NFL" / "04-data").mkdir(parents=True)
        (self.ws / "NFL" / "04-data" / "status.csv").write_text(STATUS)
        for args in (("init", "-q"), ("add", "-A"), ("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "x")):
            subprocess.run(["git", *args], cwd=self.ws, check=True, capture_output=True)
        self.sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.ws, capture_output=True, text=True).stdout.strip()
        self.state = tmp_path / "gh-state"
        self.state.mkdir()
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        (self.bin / "gh").write_text(GH_RELEASE_STUB)
        (self.bin / "python").write_text(EXPORT_PYTHON)
        (self.bin / "sleep").write_text("#!/bin/sh\nexit 0\n")
        for f in self.bin.iterdir():
            f.chmod(0o755)
        self.real_py = sys.executable
        self.log = tmp_path / "python.log"
        self.log.write_text("")
        self.details = tmp_path / "details.md"
        self.details.write_text("")

    def release(self, assets=(), body=""):
        (self.state / "release").write_text("")
        (self.state / "assets").write_text("".join(f"{a}\n" for a in assets))
        (self.state / "body").write_text(body)

    @property
    def gh_calls(self):
        f = self.state / "log"
        return f.read_text().splitlines() if f.exists() else []

    def env(self, **extra):
        env = {"GH_STATE": str(self.state), "GH_TOKEN": "t", "GH_REPO": "wes-blue/sports-analysis", "FAKE_LOG": str(self.log),
               "REAL_PY": self.real_py, "ALERT_DETAILS": str(self.details), "EXPORT_LOG": str(self.tmp / "export.log")}
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

    @property
    def body(self):
        return (self.state / "body").read_text()


@pytest.fixture
def wb(tmp_path, request):
    need_tools("git")
    return WB(tmp_path, request.param if hasattr(request, "param") else "nfl-pipeline-weekly.yml")


def both(fn):
    return pytest.mark.parametrize("wb", PUBLISHING, indirect=True)(fn)


@both
def test_first_run_no_release_builds_and_creates_it(wb):
    out, _ = wb.decide("SKIP")                       # the very first run after the merge finds nothing to publish
    assert out["build"] == "true" and out["release_exists"] == "false" and out["key"] == KEY
    wb.build()
    assert (wb.ws / "NFL" / ".work" / "workbook" / WB_ASSET).is_file()
    wb.publish(False)
    calls = wb.gh_calls
    create = next(c for c in calls if c.startswith("gh release create"))
    assert WB_TAG in create and f"--target {wb.sha}" in create and "--prerelease" in create and "--latest=false" in create
    assert [c.split()[2] for c in calls if c.startswith("gh release ")][-3:] == ["create", "upload", "edit"]
    assert "--clobber" in next(c for c in calls if c.startswith("gh release upload"))
    assert (wb.state / "assets").read_text().split() == [WB_ASSET]
    body = wb.body
    assert "season 2026, week 11 (REG)" in body and "20261120T233201Z-gh1" in body and "13 passed, 1 warned, 0 failed" in body
    assert WB_URL in body and f"<!-- nfl-workbook-key: {KEY} -->" in body and "CC BY 4.0" in body
    assert "wes-blue" not in body.replace("wes-blue/sports-analysis", "")


@both
def test_normal_publish_replaces_the_asset_on_the_existing_release(wb):
    wb.release([WB_ASSET], body="old notes <!-- nfl-workbook-key: OLD|1.0.0 -->")
    out, _ = wb.decide("PUBLISH")
    assert out["build"] == "true" and out["release_exists"] == "true"
    wb.build()
    wb.publish(True)
    calls = " ".join(wb.gh_calls)
    assert "release create" not in calls
    assert wb.gh_calls[-2].startswith("gh release upload") and "--clobber" in wb.gh_calls[-2]
    assert f"nfl-workbook-key: {KEY} " in wb.body and "OLD" not in wb.body


@both
def test_skip_with_a_current_workbook_does_nothing_but_look(wb):
    wb.release([WB_ASSET], body=f"x\n<!-- nfl-workbook-key: {KEY} -->\n")
    out, _ = wb.decide("SKIP")
    assert out["build"] == "false"
    assert [c.split()[2] for c in wb.gh_calls] == ["view", "view"], wb.gh_calls   # reads only: no export, no upload
    assert wb.log.read_text() == ""


@both
@pytest.mark.parametrize("assets,body", [
    ([], f"<!-- nfl-workbook-key: {KEY} -->"),                                  # an upload did not finish
    ([WB_ASSET], "<!-- nfl-workbook-key: 20260101T000000Z-gh0|1.2.1 -->"),     # an earlier build failed after the data commit
    ([WB_ASSET], "a hand-written note"),
    (["something-else.xlsx"], f"<!-- nfl-workbook-key: {KEY} -->")])
def test_skip_repairs_a_missing_or_stale_workbook(wb, assets, body):
    wb.release(assets, body=body)
    out, _ = wb.decide("SKIP")
    assert out["build"] == "true" and out["release_exists"] == "true"


@both
def test_manual_rebuild_builds_even_when_the_release_is_current(wb):
    wb.release([WB_ASSET], body=f"<!-- nfl-workbook-key: {KEY} -->")
    out, _ = wb.decide("WORKBOOK")
    assert out["build"] == "true"
    assert "requested by hand" in (wb.tmp / "summary.md").read_text()


@both
def test_decide_fails_loudly_when_github_cannot_be_read_or_status_is_missing(wb):
    wb.decide("SKIP", expect_rc=1, GH_VIEW_ERROR="HTTP 401: Bad credentials")
    assert "could not look at the release" in wb.details.read_text()
    wb.details.write_text("")
    (wb.ws / "NFL" / "04-data" / "status.csv").unlink()
    wb.decide("PUBLISH", expect_rc=1)
    assert "no run_id" in wb.details.read_text()


@both
def test_export_failure_is_red_leaves_no_file_and_names_the_cause(wb):
    wb.build(expect_rc=1, FAKE_EXPORT="fail")
    assert not (wb.ws / "NFL" / ".work" / "workbook" / WB_ASSET).exists()
    text = wb.details.read_text()
    assert "export exited 1" in text and "cannot read status.csv" in text
    assert "FAILED to build" in (wb.tmp / "summary.md").read_text()
    assert wb.gh_calls == [], "nothing is uploaded after a failed build"


@both
def test_a_file_that_is_not_a_workbook_is_never_uploaded(wb):
    for kind in ("garbage", "notxlsx"):          # not a zip at all / a zip that holds no workbook
        wb.details.write_text("")
        wb.build(expect_rc=1, FAKE_EXPORT=kind)
        assert not (wb.ws / "NFL" / ".work" / "workbook" / WB_ASSET).exists()
        assert "not a readable Excel workbook" in wb.details.read_text()


@both
def test_upload_failure_is_red_keeps_the_old_notes_and_points_at_the_artifact(wb):
    wb.release([WB_ASSET], body="<!-- nfl-workbook-key: OLD|1.0.0 -->")
    wb.build()
    wb.publish(True, expect_rc=1, GH_UPLOAD_FAILS="3")
    assert sum(c.startswith("gh release upload") for c in wb.gh_calls) == 3
    assert not any(c.startswith("gh release edit") for c in wb.gh_calls)
    assert "OLD|1.0.0" in wb.body, "notes must not claim the new data until the upload worked"
    text = wb.details.read_text()
    assert "could not upload" in text and "workbook-42" in text


@both
def test_upload_is_retried_and_a_second_attempt_succeeds(wb):
    wb.release([], body="")
    wb.build()
    wb.publish(True, GH_UPLOAD_FAILS="1")
    assert sum(c.startswith("gh release upload") for c in wb.gh_calls) == 2
    assert f"nfl-workbook-key: {KEY} " in wb.body


@both
def test_release_creation_failure_uploads_nothing(wb):
    wb.build()
    wb.publish(False, expect_rc=1, GH_CREATE_FAILS="1")
    assert not any(c.startswith("gh release upload") for c in wb.gh_calls)
    assert "could not create the release" in wb.details.read_text()


@both
def test_notes_update_failure_after_upload_is_red_and_self_repairs(wb):
    wb.release([], body="")
    wb.build()
    wb.publish(True, expect_rc=1, GH_EDIT_FAILS="1")
    assert "notes could not be updated" in wb.details.read_text()
    out, _ = wb.decide("SKIP")                       # the old notes carry no matching key: the next run rebuilds
    assert out["build"] == "true"


def test_resolve_workbook_only_skips_resolve_and_the_stray_file_check(tmp_path):
    root = project_tree(tmp_path)
    (root / "NFL" / "02-config" / "scoring_weights (1).csv").write_text("x\n")
    outputs, calls = resolve(tmp_path, root, event="workflow_dispatch", workbook_only="true", force="true", seasons="all")
    assert outputs["decision"] == "workbook" and outputs["force"] == "false" and calls == ""
    assert "pipeline did not run" in outputs["reason"]
    outputs, _calls = resolve(tmp_path, project_tree(tmp_path / "b"), event="workflow_dispatch", ref="refs/heads/test",
                              workbook_only="true")
    assert outputs["dry_run"] == "true", "off main it is a trial run, so nothing is published"


def test_record_outcome_maps_workbook_only_to_a_green_outcome(tmp_path):
    root = project_tree(tmp_path)
    outputs, _ = run_step("nfl-pipeline-weekly.yml", "Record outcome", tmp_path, cwd=root / "NFL" / "03-pipeline",
                          bin_dir=make_bin(tmp_path, python="real"),
                          env={"DECISION": "workbook", "RUN_OUTCOME": "", "RUN_RC": "", "DRY_RUN": "false",
                               "EVENT": "workflow_dispatch", "RESOLVE_REASON": "workbook rebuild requested by hand",
                               "RUN_LOG": str(tmp_path / "none.log"), "ALERT_DETAILS": str(tmp_path / "d.md")})
    assert outputs["outcome"] == "WORKBOOK"


def test_monthly_workbook_only_does_not_run_the_pipeline(tmp_path):
    root = project_tree(tmp_path)
    bin_dir = make_bin(tmp_path, python="fake")
    log = tmp_path / "python.log"
    log.write_text("")
    outputs, _ = run_step("nfl-pipeline-monthly.yml", "Run pipeline (all seasons)", tmp_path,
                          cwd=root / "NFL" / "03-pipeline", bin_dir=bin_dir,
                          env={"IN_DRY_RUN": "", "IN_WORKBOOK_ONLY": "true", "REF": "refs/heads/main", "EVENT_SCHEDULE": "",
                               "TRIGGER": "workflow_dispatch-monthly", "FAKE_LOG": str(log),
                               "RUN_LOG": str(tmp_path / "run.log"), "ALERT_DETAILS": str(tmp_path / "d.md")})
    assert outputs == {"dry_run": "false", "outcome": "WORKBOOK"} and log.read_text() == ""


@pytest.mark.parametrize("name", PUBLISHING)
def test_workbook_outcome_alert_is_green_and_leaves_an_open_issue(tmp_path, name):
    assert run_alert(tmp_path, name, "WORKBOOK") == {}
    run_alert(tmp_path, name, "HOLD")
    assert run_alert(tmp_path, name, "WORKBOOK") == {doc_label(name): "1"}
    assert run_alert(tmp_path, name, "PUBLISH", job_status="failure") == {doc_label(name): "1"}   # workbook step failed: red


def doc_label(name):
    return load(name)[1]["env"]["ALERT_LABEL"]


def test_guide_tells_the_owner_where_the_workbook_is():
    text = GUIDE.read_text(encoding="utf-8")
    assert WB_URL in text
    assert "workbook_only" in text
    for stale in ("Refresh All", "Power Query", "Refresh the workbook"):
        assert stale not in text, f"the guide must not tell the owner to refresh: {stale!r}"
