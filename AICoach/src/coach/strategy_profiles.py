"""
Strategy expectations per bot type and risk profile.
Used by coaches to evaluate variant performance relative to intent.
"""

STRATEGY_EXPECTATIONS = {
    "rule": {
        "ultra_conservative": {
            "expected_trades_per_day": (1, 3),
            "min_acceptable_win_rate": 55,
            "max_acceptable_drawdown_pct": 5,
            "target_profit_factor": 1.8,
            "focus": "Kapitalbeskyttelse. Få trades, høj præcision. Kun de stærkeste signaler.",
        },
        "conservative": {
            "expected_trades_per_day": (2, 5),
            "min_acceptable_win_rate": 50,
            "max_acceptable_drawdown_pct": 8,
            "target_profit_factor": 1.5,
            "focus": "Stabil vækst. Moderat selektivitet, undgå store tab.",
        },
        "balanced": {
            "expected_trades_per_day": (3, 8),
            "min_acceptable_win_rate": 45,
            "max_acceptable_drawdown_pct": 10,
            "target_profit_factor": 1.3,
            "focus": "Balance mellem frekvens og kvalitet.",
        },
        "moderate": {
            "expected_trades_per_day": (4, 10),
            "min_acceptable_win_rate": 42,
            "max_acceptable_drawdown_pct": 12,
            "target_profit_factor": 1.2,
            "focus": "Standard drift. Bred eksponering, acceptabel risiko.",
        },
        "moderate_aggressive": {
            "expected_trades_per_day": (5, 12),
            "min_acceptable_win_rate": 40,
            "max_acceptable_drawdown_pct": 15,
            "target_profit_factor": 1.1,
            "focus": "Offensiv. Flere muligheder, lavere tærskel.",
        },
        "aggressive": {
            "expected_trades_per_day": (5, 15),
            "min_acceptable_win_rate": 38,
            "max_acceptable_drawdown_pct": 18,
            "target_profit_factor": 1.0,
            "focus": "Volumen. Mange trades, positiv forventningsværdi over tid.",
        },
        "ultra_aggressive": {
            "expected_trades_per_day": (8, 25),
            "min_acceptable_win_rate": 35,
            "max_acceptable_drawdown_pct": 25,
            "target_profit_factor": 0.9,
            "focus": "Maksimal eksponering. Kræver stort sample for statistisk signifikans.",
        },
    },
    "scalper": {
        "ultra_conservative": {
            "expected_trades_per_day": (3, 8),
            "min_acceptable_win_rate": 55,
            "max_acceptable_drawdown_pct": 5,
            "target_profit_factor": 1.5,
            "focus": "Stram scalping. Kun de reneste zone-signals.",
        },
        "conservative": {
            "expected_trades_per_day": (5, 12),
            "min_acceptable_win_rate": 50,
            "max_acceptable_drawdown_pct": 8,
            "target_profit_factor": 1.3,
            "focus": "Selektiv scalping. Højkvalitets range-bounce.",
        },
        "balanced": {
            "expected_trades_per_day": (8, 18),
            "min_acceptable_win_rate": 47,
            "max_acceptable_drawdown_pct": 10,
            "target_profit_factor": 1.2,
            "focus": "Balanceret scalping. God zone-discipline.",
        },
        "moderate": {
            "expected_trades_per_day": (10, 25),
            "min_acceptable_win_rate": 44,
            "max_acceptable_drawdown_pct": 12,
            "target_profit_factor": 1.1,
            "focus": "Standard scalping. Bred zone-tolerance.",
        },
        "moderate_aggressive": {
            "expected_trades_per_day": (12, 30),
            "min_acceptable_win_rate": 42,
            "max_acceptable_drawdown_pct": 15,
            "target_profit_factor": 1.0,
            "focus": "Offensiv scalping. Høj frekvens.",
        },
        "aggressive": {
            "expected_trades_per_day": (15, 40),
            "min_acceptable_win_rate": 40,
            "max_acceptable_drawdown_pct": 20,
            "target_profit_factor": 0.9,
            "focus": "Aggressiv scalping. Edge via volumen.",
        },
        "ultra_aggressive": {
            "expected_trades_per_day": (20, 60),
            "min_acceptable_win_rate": 38,
            "max_acceptable_drawdown_pct": 25,
            "target_profit_factor": 0.8,
            "focus": "Hyper-frekvens scalping. Statistisk edge kræver 200+ trades.",
        },
    },
    "ai": {
        "ultra_conservative": {
            "expected_trades_per_day": (0.5, 2),
            "min_acceptable_win_rate": 60,
            "max_acceptable_drawdown_pct": 5,
            "target_profit_factor": 2.0,
            "focus": "Ekstremt selektiv AI. Kun høj-confidence opportunities.",
        },
        "conservative": {
            "expected_trades_per_day": (1, 3),
            "min_acceptable_win_rate": 55,
            "max_acceptable_drawdown_pct": 8,
            "target_profit_factor": 1.7,
            "focus": "Selektiv AI. Høj confidence-threshold, stram risikostyring.",
        },
        "balanced": {
            "expected_trades_per_day": (2, 5),
            "min_acceptable_win_rate": 50,
            "max_acceptable_drawdown_pct": 10,
            "target_profit_factor": 1.5,
            "focus": "Balanceret AI. Moderat selektivitet.",
        },
        "moderate": {
            "expected_trades_per_day": (2, 6),
            "min_acceptable_win_rate": 48,
            "max_acceptable_drawdown_pct": 12,
            "target_profit_factor": 1.3,
            "focus": "Standard AI drift. Bredere confidence-accept.",
        },
        "moderate_aggressive": {
            "expected_trades_per_day": (3, 8),
            "min_acceptable_win_rate": 45,
            "max_acceptable_drawdown_pct": 15,
            "target_profit_factor": 1.2,
            "focus": "Offensiv AI. Lavere confidence OK, flere idéer.",
        },
        "aggressive": {
            "expected_trades_per_day": (4, 10),
            "min_acceptable_win_rate": 42,
            "max_acceptable_drawdown_pct": 18,
            "target_profit_factor": 1.0,
            "focus": "Aggressiv AI. Mange opportunities, accepterer lavere præcision.",
        },
        "ultra_aggressive": {
            "expected_trades_per_day": (5, 15),
            "min_acceptable_win_rate": 38,
            "max_acceptable_drawdown_pct": 25,
            "target_profit_factor": 0.9,
            "focus": "Maksimal AI-eksponering. Bredt net, lav threshold.",
        },
    },
}

# Minimum trades required for statistically meaningful evaluation
MIN_TRADES_FOR_EVALUATION = {
    "preliminary": 20,   # Basic tendencies visible
    "meaningful": 50,    # Can judge with moderate confidence
    "reliable": 100,     # Statistical significance
    "definitive": 200,   # Solid conclusions
}


def get_expectations(bot_type, profile):
    """Get performance expectations for a bot type + profile combo."""
    type_expectations = STRATEGY_EXPECTATIONS.get(bot_type, {})
    return type_expectations.get(profile, type_expectations.get("moderate", {}))


def evaluate_against_expectations(bot_type, profile, metrics):
    """Evaluate actual metrics against expectations. Returns score dict."""
    expectations = get_expectations(bot_type, profile)
    if not expectations:
        return {"score": None, "verdict": "unknown", "details": []}

    details = []
    scores = []

    # Trade frequency
    trades_per_day = metrics.get("trades_per_day", 0)
    expected_range = expectations.get("expected_trades_per_day", (0, 100))
    if expected_range[0] <= trades_per_day <= expected_range[1]:
        scores.append(1.0)
        details.append(f"Trade frekvens OK: {trades_per_day:.1f}/dag (forventet {expected_range[0]}-{expected_range[1]})")
    elif trades_per_day < expected_range[0] * 0.5:
        scores.append(0.3)
        details.append(f"For FÅ trades: {trades_per_day:.1f}/dag (forventet {expected_range[0]}-{expected_range[1]})")
    elif trades_per_day > expected_range[1] * 1.5:
        scores.append(0.3)
        details.append(f"For MANGE trades: {trades_per_day:.1f}/dag (forventet {expected_range[0]}-{expected_range[1]})")
    else:
        scores.append(0.7)
        details.append(f"Trade frekvens lidt udenfor: {trades_per_day:.1f}/dag (forventet {expected_range[0]}-{expected_range[1]})")

    # Win rate
    win_rate = metrics.get("win_rate", 0)
    min_wr = expectations.get("min_acceptable_win_rate", 40)
    if win_rate >= min_wr:
        scores.append(1.0)
        details.append(f"Win rate OK: {win_rate:.1f}% (min {min_wr}%)")
    elif win_rate >= min_wr * 0.8:
        scores.append(0.5)
        details.append(f"Win rate lav: {win_rate:.1f}% (min {min_wr}%)")
    else:
        scores.append(0.0)
        details.append(f"Win rate KRITISK: {win_rate:.1f}% (min {min_wr}%)")

    # Drawdown
    max_dd = abs(metrics.get("max_drawdown_pct", 0))
    max_ok = expectations.get("max_acceptable_drawdown_pct", 15)
    if max_dd <= max_ok:
        scores.append(1.0)
        details.append(f"Drawdown OK: {max_dd:.1f}% (max {max_ok}%)")
    elif max_dd <= max_ok * 1.5:
        scores.append(0.4)
        details.append(f"Drawdown HØJ: {max_dd:.1f}% (max {max_ok}%)")
    else:
        scores.append(0.0)
        details.append(f"Drawdown KRITISK: {max_dd:.1f}% (max {max_ok}%)")

    # Profit factor
    pf = metrics.get("profit_factor", 0)
    target_pf = expectations.get("target_profit_factor", 1.0)
    if pf >= target_pf:
        scores.append(1.0)
        details.append(f"Profit factor STÆRK: {pf:.2f} (target {target_pf})")
    elif pf >= 1.0:
        scores.append(0.6)
        details.append(f"Profit factor OK: {pf:.2f} (target {target_pf})")
    else:
        scores.append(0.0)
        details.append(f"Profit factor NEGATIV: {pf:.2f} (target {target_pf})")

    overall = sum(scores) / len(scores) if scores else 0
    if overall >= 0.75:
        verdict = "excellent"
    elif overall >= 0.5:
        verdict = "acceptable"
    elif overall >= 0.25:
        verdict = "underperforming"
    else:
        verdict = "critical"

    return {
        "score": round(overall, 2),
        "verdict": verdict,
        "details": details,
        "focus": expectations.get("focus", ""),
    }
