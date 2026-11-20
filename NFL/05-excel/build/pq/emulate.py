"""Python emulation of the 2.001 Power Query logic (D1 desk check; not part of the product).

Mirrors, step by step, the M in NFL/05-excel/powerquery:
  Stats_Raw / Pipeline_Scored / Published_Seasons (window + typing), Scoring_Weights, Bonus_Rules, Stats_Scored,
  Check_Parity, Check_Rules_Drift, Check_RowCounts, Check_Integrity, Pipeline_Status (league contract rows),
  Check_Reconciliation and Check_Golden (2.001: widened tolerance and NOT APPLICABLE, QA finding N-1).
It reads a local copy of the published data; the web path (Web.Contents) cannot run outside Excel.
"Workbook tables" are given as a folder of CSVs named like the config files (tblConfig = pipeline_config.csv + DataLocation).
tblGolden and tblGoldenRules are golden_sample.csv and fixture_contracts.csv from that folder if present, else from
NFL/06-qa/fixtures.
Usage: python emulate.py <data_dir> <workbook_tables_dir>
"""
import csv, sys, os, re
from decimal import Decimal, ROUND_HALF_UP

TOL_PARITY = 0.000001


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def num(t):  # en-US number, blank -> None, non-numeric -> None (Table.ReplaceErrorValues)
    if t is None:
        return None
    if isinstance(t, (int, float)):
        return t
    t = t.strip()
    if t == "":
        return None
    try:
        return float(t)
    except ValueError:
        return None


# ---------- season window (W_* snippet) ----------
def resolve_window(cfg, index):
    published = sorted({int(r["season"]) for r in index if r["season"] != ""})
    if not published:
        raise ValueError("seasons.csv lists no season")
    latest = max(published)

    def resolve(name):
        raw = (cfg.get(name) or "").strip()
        if raw == "":
            raise ValueError(f"Config.Error {name} blank")
        u = raw.replace(" ", "").replace("\xa0", "").upper()
        if u == "LATEST":
            v = latest
        elif u.startswith("LATEST-"):
            off = u[7:]
            if off.isdigit() and int(off) <= 30:
                v = latest - int(off)
            else:
                raise ValueError(f"Config.Error {name} bad")
        elif u.isdigit():
            v = int(u)
        else:
            raise ValueError(f"Config.Error {name} bad")
        if v < 1999:
            raise ValueError("before 1999")
        return v

    start, end = resolve("StartSeason"), resolve("EndSeason")
    st = cfg["SeasonTypes"].replace(" ", "").replace("\xa0", "").upper()
    types = {"REG": ["REG"], "POST": ["POST"], "REG+POST": ["REG", "POST"]}[st]
    if start > end:
        raise ValueError("start after end")
    seasons = [s for s in published if start <= s <= end]
    if not seasons:
        raise ValueError("no published season in window")
    return start, end, types, seasons, published


TEXT_ID = ["season_type", "player_id", "player_display_name", "position", "position_group", "team", "opponent_team"]
EXTRA_TEXT = ["player_name", "headshot_url", "game_id", "fg_made_list", "fg_missed_list", "fg_blocked_list"]


def load_rows(data, prefix, seasons, types, text_cols):
    rows, cols = [], []
    for s in seasons:
        part = read_csv(os.path.join(data, f"{prefix}_{s}.csv"))
        for c in (part[0].keys() if part else []):
            if c not in cols:
                cols.append(c)  # Table.Combine unions columns by name
        rows.extend(part)
    out = []
    for r in rows:
        if r.get("season_type") not in types:
            continue
        t = {}
        for c in cols:
            v = r.get(c)
            v = None if v in ("", None) else v  # BlankToNull
            if c in ("season", "week"):
                t[c] = int(v)
            elif c in text_cols:
                t[c] = v
            else:
                t[c] = num(v)
        out.append(t)
    return out, cols


def stats_raw(data, cfg):
    index = read_csv(os.path.join(data, "seasons.csv"))
    start, end, types, seasons, published = resolve_window(cfg, index)
    rows, cols = load_rows(data, "player_week/player_week", seasons, types, TEXT_ID + EXTRA_TEXT)
    missing = [c for c in ["season", "week"] + TEXT_ID if c not in cols]
    if missing:
        raise ValueError(f"missing identity {missing}")
    return rows, cols


def pipeline_scored(data, cfg):
    index = read_csv(os.path.join(data, "seasons.csv"))
    start, end, types, seasons, published = resolve_window(cfg, index)
    rows, cols = load_rows(data, "scored/scored", seasons, types, ["season_type", "player_id", "player_display_name", "position", "team"])
    return rows, cols


def published_seasons(data, cfg):
    index = read_csv(os.path.join(data, "seasons.csv"))
    start, end, types, seasons, published = resolve_window(cfg, index)
    out = [dict(season=int(r["season"]), season_type=r["season_type"], player_rows=int(r["player_rows"]), dst_rows=int(r["dst_rows"]),
                max_week=int(r["max_week"]), season_status=r["season_status"]) for r in index
           if int(r["season"]) in seasons and r["season_type"] in types]
    for s in range(start, end + 1):
        if s not in published:
            for t in types:
                out.append(dict(season=s, season_type=t, player_rows=None, dst_rows=None, max_week=None, season_status="not published"))
    return out


# ---------- Scoring_Weights / Bonus_Rules (from workbook tables) ----------
def parse_gate(v):
    if v is None:
        return None
    parts = [p for p in str(v).replace(" ", "").replace("\xa0", "").upper().split(",") if p != ""]
    return parts or None


def scoring_weights(wb):
    leagues = [r for r in wb["leagues"] if (r["League"] or "").strip() and (r["Active"] or "").strip().upper() == "YES"]
    scoring = [r for r in wb["scoring"] if (r["Metric"] or "").strip()]
    metrics = [r["Metric"].strip() for r in scoring]
    gates = {r["Metric"].strip(): parse_gate(r.get("Applies_To") or None) for r in scoring}
    rd = int(round(float(wb["config"]["RoundDecimals"])))
    out = []
    for lg in leagues:
        name = lg["League"].strip()
        w = {}
        for r in scoring:
            v = r[name]
            x = 0.0 if v is None or v.strip() == "" else float(v)
            if x != 0:
                w[r["Metric"].strip()] = x
        out.append(dict(League=name, RoundDecimals=rd, Weights=w, Gates={m: gates[m] for m in w if gates.get(m)}))
    return out


def bonus_rules(wb):
    out = []
    for r in wb["bonus"]:
        if not ((r["League"] or "").strip() or (r["Metric"] or "").strip()):
            continue
        out.append(dict(League=r["League"].strip(), Metric=r["Metric"].strip(), Lower=num(r["Lower"]), Upper=num(r["Upper"]),
                        Points=num(r["Points"]), Gate=parse_gate(r.get("Applies_To") or None)))
    return out


def round_away(x, d):  # Number.Round(x, d, RoundingMode.AwayFromZero)
    q = Decimal(1).scaleb(-d)
    return float(Decimal(repr(x)).quantize(q, rounding=ROUND_HALF_UP))  # ROUND_HALF_UP in decimal = half away from zero


def round_it(x, d):  # RoundIt in Stats_Scored: 9 decimals first (removes float noise, CONTRACTS 4 step 4), then d
    return round_away(round_away(x, 9), d)


# ---------- Stats_Scored (ScoreRow / BonusRow / RoundIt, as in the M) ----------
def stats_scored(raw, weights, rules):
    decimals = 2 if not weights else weights[0]["RoundDecimals"]
    out = []
    for row in raw:
        pos = (row.get("position") or "").upper()
        grp = (row.get("position_group") or "").upper()
        r2 = dict(row)
        for lg in weights:
            terms = []
            for m, w in lg["Weights"].items():
                gate = lg["Gates"].get(m)
                allowed = gate is None or pos in gate or grp in gate
                stat = row.get(m)
                value = 0 if stat is None or not allowed else stat
                terms.append(value * w)
            score = sum(terms) if terms else 0
            lr = [b for b in rules if b["League"] == lg["League"]]
            if lr:
                bonus = 0
                for b in lr:
                    stat = row.get(b["Metric"])
                    inband = stat is not None and (b["Lower"] is None or stat >= b["Lower"]) and (b["Upper"] is None or stat <= b["Upper"])
                    ingate = b["Gate"] is None or pos in b["Gate"] or grp in b["Gate"]
                    bonus += b["Points"] if inband and ingate else 0
                score = score + bonus
            r2["FF_" + lg["League"]] = round_it(score, decimals)
        out.append(r2)
    return out


# ---------- Check_Parity ----------
def check_parity(scored, scored_cols_leagues, pipe, pipe_cols):
    keys = ("season", "week", "season_type", "player_id")
    wl = scored_cols_leagues
    pl = [c[3:] for c in pipe_cols if c.startswith("FF_")]
    common = [l for l in wl if l in pl]
    left = {tuple(r[k] for k in keys): r for r in scored}
    right = {tuple(r[k] for k in keys): r for r in pipe}
    only_wb = sum(1 for k in left if k not in right)
    only_pipe = sum(1 for k in right if k not in left)
    both = [k for k in left if k in right]
    res = []
    for l in common:
        diffs = []
        for k in both:
            a, b = left[k]["FF_" + l], right[k]["FF_" + l]
            diffs.append(0 if a is None and b is None else (None if a is None or b is None else abs(a - b)))
        blank = sum(1 for d in diffs if d is None)
        different = blank + sum(1 for d in diffs if d is not None and d > TOL_PARITY)
        numeric = [d for d in diffs if d is not None]
        largest = max(numeric) if numeric else None
        ex = ""
        pos = diffs.index(largest) if largest is not None and largest > TOL_PARITY else (diffs.index(None) if blank else -1)
        if pos >= 0:
            k = both[pos]
            ex = f"{k[0]} wk{k[1]} {k[2]} {left[k]['player_display_name']} ({k[3]}): workbook {left[k]['FF_'+l]} vs pipeline {right[k]['FF_'+l]}"
        if not both:
            st = "no rows to compare"
        elif different > blank:
            st = "differs: workbook rules changed? (see Check_Rules_Drift)"
        elif blank > 0:
            st = "differs: blank scores on one side: refresh again"
        elif only_wb + only_pipe > 0:
            st = "same scores, but the row sets differ: refresh again"
        else:
            st = "matches pipeline"
        res.append(dict(League=l, Rows_Compared=len(both), Rows_Equal=len(both) - different, Rows_Different=different,
                        Largest_Difference=largest, Only_In_Workbook=only_wb, Only_In_Pipeline=only_pipe, Status=st, Example=ex))
    for l in wl:
        if l not in pl:
            res.append(dict(League=l, Rows_Compared=0, Status="not in pipeline: league added or renamed in the workbook? (see Check_Rules_Drift)"))
    for l in pl:
        if l not in wl:
            res.append(dict(League=l, Rows_Compared=0, Status="not scored in workbook: league inactive or renamed here? (see Check_Rules_Drift)"))
    return res


# ---------- Check_Rules_Drift ----------
def clean(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return repr(v)
    return str(v).strip()


def to_num(v):
    t = clean(v)
    if t == "":
        return None
    try:
        return float(t)
    except ValueError:
        return None


def show(v, blank):
    t = clean(v)
    if t == "":
        return blank
    n = to_num(v)
    return t if n is None else (str(int(n)) if n == int(n) else repr(n))


def same(a, b, blank_zero):
    na = 0.0 if blank_zero and clean(a) == "" else to_num(a)
    nb = 0.0 if blank_zero and clean(b) == "" else to_num(b)
    if na is not None and nb is not None:
        return abs(na - nb) <= 1e-9
    return clean(a) == clean(b)


def norm_gate(v):
    return ",".join(sorted({p for p in clean(v).replace(" ", "").replace("\xa0", "").upper().split(",") if p}))


def rules_drift(wb, pipe):
    rows = []
    R = lambda *a: rows.append(dict(zip(("League", "Kind", "Item", "Workbook", "Pipeline", "Status"), a)))
    pcfg = {r["Setting"].strip(): r["Value"] for r in pipe["config_rows"] if clean(r["Setting"])}
    if not same(wb["config"].get("RoundDecimals"), pcfg.get("RoundDecimals"), False):
        R("(all leagues)", "Setting", "RoundDecimals", show(wb["config"].get("RoundDecimals"), "(blank)"), show(pcfg.get("RoundDecimals"), "(blank)"), "changed")
    act = lambda t: [clean(r["League"]) for r in t if clean(r["League"]) and clean(r["Active"]).upper() == "YES"]
    allL = lambda t: [clean(r["League"]) for r in t if clean(r["League"])]
    wa, pa, wall, pall = act(wb["leagues"]), act(pipe["leagues"]), allL(wb["leagues"]), allL(pipe["leagues"])
    leagues = list(dict.fromkeys(wa + pa))
    state = lambda n, al, ac: "active" if n in ac else ("inactive" if n in al else "(absent)")
    for l in leagues:
        if state(l, wall, wa) != state(l, pall, pa):
            R(l, "League", "Active", state(l, wall, wa), state(l, pall, pa), "changed")
    wbm = {clean(r["Metric"]): r for r in wb["scoring"] if clean(r["Metric"])}
    pm = {clean(r["Metric"]): r for r in pipe["scoring"] if clean(r["Metric"])}
    allm = list(dict.fromkeys(list(wbm) + list(pm)))
    wcols, pcols = set(wb["scoring"][0].keys()), set(pipe["scoring"][0].keys())
    cell = lambda bm, m, c: None if m not in bm else bm[m].get(c)
    desc = lambda bm, m, c, has: "(no row)" if m not in bm else ("(no league column)" if not has else show(cell(bm, m, c), "0"))
    for l in leagues:
        wh, ph = l in wcols, l in pcols
        for m in allm:
            if not same(cell(wbm, m, l), cell(pm, m, l), True):
                st = "only in workbook" if (m not in pm or not ph) else ("only in pipeline" if (m not in wbm or not wh) else "changed")
                R(l, "Weight", m, desc(wbm, m, l, wh), desc(pm, m, l, ph), st)
    for m in allm:
        if m in wbm and m in pm and norm_gate(wbm[m].get("Applies_To")) != norm_gate(pm[m].get("Applies_To")):
            R("(all leagues)", "Gate", m, norm_gate(wbm[m].get("Applies_To")) or "(all players)", norm_gate(pm[m].get("Applies_To")) or "(all players)", "changed")

    def bands(rules):
        g = {}
        for r in rules:
            if not (clean(r["League"]) or clean(r["Metric"])):
                continue
            k = "|".join([clean(r["League"]), clean(r["Metric"]), show(r.get("Lower"), ""), show(r.get("Upper"), ""), norm_gate(r.get("Applies_To"))])
            p = to_num(r.get("Points"))
            if k in g:
                g[k] = None if g[k] is None or p is None else g[k] + p
            else:
                g[k] = p
        return g

    wbb, pb = bands(wb["bonus"]), bands(pipe["bonus"])
    for k in list(dict.fromkeys(list(wbb) + list(pb))):
        a, b = wbb.get(k, "X"), pb.get(k, "X")
        if a == "X" or b == "X" or a is None or b is None or abs(a - b) > 1e-9:
            p = k.split("|")
            label = f"{p[1]} {p[2] or '(no min)'} to {p[3] or '(no max)'}" + (f" [{p[4]}]" if p[4] else "")
            sh = lambda x: "(no band)" if x == "X" else f"{x:g} pts"
            R(p[0], "Band", label, sh(a), sh(b), "only in workbook" if b == "X" else ("only in pipeline" if a == "X" else "changed"))
    if not rows:
        R("(all leagues)", "Summary", "Workbook rules equal the rules of the published data", "", "", "same")
    return rows


def check_rowcounts(raw, pubs):
    cnt = {}
    for r in raw:
        k = (r["season"], r["season_type"])
        c = cnt.setdefault(k, [0, 0])
        c[1 if r["position"] == "DST" else 0] += 1
    out = []
    for p in pubs:
        k = (p["season"], p["season_type"])
        w = cnt.get(k, [0, 0])
        if p["season_status"] == "not published":
            st = "NOT PUBLISHED"
        elif (p["player_rows"] or 0) == w[0] and (p["dst_rows"] or 0) == w[1]:
            st = "PASS"
        else:
            st = "FAIL"
        out.append((p["season"], p["season_type"], p["season_status"], p["player_rows"], w[0], p["dst_rows"], w[1], st))
    pk = {(p["season"], p["season_type"]) for p in pubs}
    for k, w in cnt.items():
        if k not in pk:
            out.append((k[0], k[1], None, None, w[0], None, w[1], "NOT IN seasons.csv"))
    return sorted(out, key=lambda t: (t[0], t[1] != "REG"))


def load_workbook_tables(d):
    cfg = {r["Setting"].strip(): r["Value"] for r in read_csv(os.path.join(d, "pipeline_config.csv")) if (r["Setting"] or "").strip()}
    return dict(config=cfg, leagues=read_csv(os.path.join(d, "leagues.csv")), scoring=read_csv(os.path.join(d, "scoring_weights.csv")),
                bonus=read_csv(os.path.join(d, "bonus_rules.csv")))


# ---------- Pipeline_Status league contract rows, Check_Reconciliation, Check_Golden (2.001) ----------
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "06-qa", "fixtures")


def pipeline_contracts(data, golden_rules):
    status = {r["key"].strip(): (r["value"] or "").strip() for r in read_csv(os.path.join(data, "status.csv")) if (r["key"] or "").strip()}
    pcfg = {r["Setting"].strip(): r["Value"] for r in read_csv(os.path.join(data, "config/pipeline_config.csv")) if (r["Setting"] or "").strip()}
    pipe_round = to_num(pcfg.get("RoundDecimals"))
    exp = {r["League"].strip(): r for r in golden_rules if (r.get("League") or "").strip()} if golden_rules is not None else None
    out = []
    for k, v in status.items():
        if not k.startswith("contract_"):
            continue
        lg = k[9:]
        if exp is None:
            res = "OK"
        elif lg not in exp:
            res = "NO TEST VALUES"
        elif (exp[lg].get("Rules_SHA256") or "").strip().lower() != v.lower():
            res = "RULES CHANGED"
        elif to_num(exp[lg].get("RoundDecimals")) is None or pipe_round is None or to_num(exp[lg].get("RoundDecimals")) != pipe_round:
            res = "DECIMALS CHANGED"
        else:
            res = "OK"
        out.append(dict(Item=lg, Value=v, Result=res))
    return out


def recon_tolerance(wb):
    t = (wb["config"].get("ReconcileTolerance") or "").strip()
    base = 0.005 if t == "" else float(t)
    d = int(round(float(wb["config"]["RoundDecimals"])))
    return (max(base, 0.5 * 10 ** -d) if d < 2 else base), base, d


def check_reconciliation(scored, wb, contracts, drift):
    tol, base, d = recon_tolerance(wb)
    leagues = [r for r in wb["leagues"] if clean(r["League"]) and clean(r["Active"]).upper() == "YES" and clean(r["Reconcile_To"])]
    out = []
    for lg in leagues:
        name, target = clean(lg["League"]), clean(lg["Reconcile_To"])
        comp = [r for r in scored if r.get("position") != "DST" and r.get(target) is not None]
        mism = [r for r in comp if abs((r.get("FF_" + name) or 0) - r[target]) > tol]
        pipe = [c for c in contracts if c["Item"] == name and c["Result"] == "RULES CHANGED"]
        edits = [x for x in drift if x["Status"] != "same" and x["Kind"] != "Setting" and x["League"] in (name, "(all leagues)")]
        na = "pipeline rules changed" if pipe else ("workbook rules edited (%d)" % len(edits) if edits else "")
        st = "NO ROWS" if not comp else ("NOT APPLICABLE" if na else ("PASS" if not mism else "FAIL"))
        out.append(dict(League=name, Reconcile_To=target, Rows_Compared=len(comp), Rows_Mismatched=len(mism),
                        Match_Pct=round(1 - len(mism) / len(comp), 6) if comp else None, Status=st, Tolerance=tol, Reason=na))
    return out


def check_golden(scored, golden, contracts, drift):
    keys = ("season", "week", "season_type", "player_id")
    idx = {tuple(r[k] for k in keys): r for r in scored}
    cols = [c for c in golden[0].keys() if c.startswith("FF_")] if golden else []
    out = []
    for c in cols:
        lg = c[3:]
        bad = 0
        total = 0
        for g in golden:
            total += 1
            k = (int(g["season"]), int(g["week"]), g["season_type"], g["player_id"])
            act = idx.get(k, {}).get(c) if k in idx else None
            exp = num(g[c])
            if act is None or exp is None or abs(act - exp) > 0.011:
                bad += 1
        if scored and c not in scored[0]:
            out.append(dict(League=lg, Status="SKIPPED (column not in Stats_Scored)"))
            continue
        pipe = [x for x in contracts if x["Item"] == lg and x["Result"] in ("RULES CHANGED", "DECIMALS CHANGED")]
        edits = [x for x in drift if x["Status"] != "same" and x["League"] in (lg, "(all leagues)")]
        na = "pipeline " + pipe[0]["Result"] if pipe else ("workbook rules edited (%d)" % len(edits) if edits else "")
        st = "NO ROWS" if total == 0 else ("NOT APPLICABLE" if na else ("PASS" if bad == 0 else "FAIL"))
        out.append(dict(League=lg, Golden_Rows=total, Matched=total - bad, Mismatched=bad, Status=st, Reason=na))
    return out


def run(data, wbdir, show_rows=True):
    wb = load_workbook_tables(wbdir)
    raw, cols = stats_raw(data, wb["config"])
    weights = scoring_weights(wb)
    rules = bonus_rules(wb)
    scored = stats_scored(raw, weights, rules)
    pipe, pcols = pipeline_scored(data, wb["config"])
    pubs = published_seasons(data, wb["config"])
    pc = dict(leagues=read_csv(os.path.join(data, "config/leagues.csv")), scoring=read_csv(os.path.join(data, "config/scoring_weights.csv")),
              bonus=read_csv(os.path.join(data, "config/bonus_rules.csv")), config_rows=read_csv(os.path.join(data, "config/pipeline_config.csv")))
    keys = {(r["season"], r["week"], r["season_type"], r["player_id"]) for r in raw}
    out = dict(
        stats_raw_rows=len(raw), stats_raw_cols=len(cols),
        integrity=[("Rows Stats_Scored = Stats_Raw", len(raw), len(scored)), ("Unique key", len(raw), len(keys)),
                   ("DST rows", None, sum(1 for r in raw if r["position"] == "DST"))],
        rowcounts=check_rowcounts(raw, pubs),
        parity=check_parity(scored, [w["League"] for w in weights], pipe, pcols),
        drift=rules_drift(wb, pc),
    )
    gpath = os.path.join(wbdir, "golden_sample.csv") if os.path.exists(os.path.join(wbdir, "golden_sample.csv")) else os.path.join(FIXTURES, "golden_sample.csv")
    rpath = os.path.join(wbdir, "fixture_contracts.csv") if os.path.exists(os.path.join(wbdir, "fixture_contracts.csv")) else os.path.join(FIXTURES, "fixture_contracts.csv")
    golden_rules = [dict(League=r["league"], Rules_SHA256=r["rules_sha256"], RoundDecimals=r["round_decimals"]) for r in read_csv(rpath)]
    out["contracts"] = pipeline_contracts(data, golden_rules)
    out["reconciliation"] = check_reconciliation(scored, wb, out["contracts"], out["drift"])
    out["golden"] = check_golden(scored, read_csv(gpath), out["contracts"], out["drift"])
    return out


if __name__ == "__main__":
    o = run(sys.argv[1], sys.argv[2])
    print("Stats_Raw rows", o["stats_raw_rows"], "columns", o["stats_raw_cols"])
    print("Check_Integrity", o["integrity"])
    print("Check_RowCounts"); [print("  ", r) for r in o["rowcounts"]]
    print("Check_Parity"); [print("  ", r) for r in o["parity"]]
    print("Check_Rules_Drift"); [print("  ", r) for r in o["drift"]]
    print("Pipeline_Status league contracts"); [print("  ", r) for r in o["contracts"]]
    print("Check_Reconciliation"); [print("  ", r) for r in o["reconciliation"]]
    print("Check_Golden"); [print("  ", r) for r in o["golden"]]
