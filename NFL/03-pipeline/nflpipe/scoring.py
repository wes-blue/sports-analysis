"""League scoring (CONTRACTS.md section 4), ported unchanged from the verified scoring engine of
the earlier, Excel-based version of this project.

For one row and one league:
1. linear part: sum of weight x value over the league's non-zero weights, in
   scoring_weights.csv order, where the metric's position gate allows the row (null = 0);
2. bands: + Points for each of the league's bonus rows whose value is not null, lies in
   [Lower, Upper] (a blank bound is open) and whose gate allows the row;
3. round the sum to 9 decimals, which removes binary floating-point noise, then round half
   away from zero to RoundDecimals (CONTRACTS.md 4; pipeline 1.1.0, QA finding m-02).
The order of the additions is the engine's, so the floating-point sum is identical. The first
rounding step is new in 1.1.0: the earlier engine rounded ``Decimal(repr(x))`` directly, so a sum that is
exactly 13.5 but stored as 13.499999999999998 rounded down at 0 decimals. No published value
changes at 2 decimals.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .config import Config


def gate_codes(text: str | None) -> frozenset[str]:
    """Position gate as a set of upper-case codes; empty set means 'every row'."""
    return frozenset(c for c in (text or "").upper().replace(" ", "").split(",") if c)


def allowed(gate: frozenset[str], position: str, position_group: str) -> bool:
    """True when the gate is empty or lists the row's position or position group."""
    return not gate or (position or "").upper() in gate or (position_group or "").upper() in gate


NOISE_DECIMALS = 9      # step 1 of the rounding rule (CONTRACTS.md 4)


def round_half_away(x: float, decimals: int) -> float:
    """Round to 9 decimals (removes float noise), then half away from zero to ``decimals``.

    Decimal ROUND_HALF_UP is away from zero for negatives too.
    """
    clean = Decimal(repr(round(x, NOISE_DECIMALS)))
    return float(clean.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP))


@dataclass
class LeagueRules:
    """Everything needed to score one league, prepared once per run."""
    name: str
    weights: list[tuple[str, float, frozenset[str]]]                       # (metric, weight, gate)
    bands: list[tuple[str, float | None, float | None, float, frozenset[str]]]  # (metric, lo, hi, points, gate)

    @property
    def column(self) -> str:
        return "FF_" + self.name


def build_rules(config: Config) -> list[LeagueRules]:
    """Scoring rules for every Active league, in leagues.csv order.

    As in the earlier engine, zero weights are dropped and the gate of a weight comes from the
    metric's Applies_To; a metric listed twice keeps its first position (G-CONFIG fails
    such a config anyway).
    """
    rules = []
    for league in config.active_leagues:
        weights: dict[str, tuple[float, frozenset[str]]] = {}
        for w in config.weights:
            value = w.weights.get(league.name, 0.0)
            if value:
                weights[w.metric] = (value, gate_codes(w.applies_to))
        bands = [(b.metric, b.lower, b.upper, b.points, gate_codes(b.applies_to))
                 for b in config.bands if b.league == league.name]
        rules.append(LeagueRules(league.name, [(m, v, g) for m, (v, g) in weights.items()], bands))
    return rules


def score_row(row: dict, league: LeagueRules, decimals: int) -> float:
    """FF_<League> for one row: linear part plus bands, rounded half away from zero."""
    position, group = row.get("position") or "", row.get("position_group") or ""
    linear = sum((row.get(metric) if row.get(metric) is not None else 0.0) * weight
                 for metric, weight, gate in league.weights if allowed(gate, position, group))
    bonus = 0.0
    for metric, lower, upper, points, gate in league.bands:
        value = row.get(metric)
        if value is None or (lower is not None and value < lower) or (upper is not None and value > upper):
            continue
        if not allowed(gate, position, group):
            continue
        bonus += points
    return round_half_away(linear + bonus, decimals)
