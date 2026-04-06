"""트레이드 분석 모듈."""

import pandas as pd

import config
from analytics.matchup import STAT_KEY_MAP, get_stat_value
from analytics.lineup import _get_best_stats, PITCHER_POSITIONS
from analytics.blended_stats import get_blended_stats


def analyze_trade(
    my_roster: list,
    giving_players: list[str],
    receiving_players: list,
    league_teams: list = None,
) -> dict:
    """트레이드의 영향을 분석한다."""
    current_totals = _sum_category_stats(my_roster)
    giving_stats = _sum_category_stats(
        [p for p in my_roster if p.name in giving_players]
    )
    receiving_stats = _sum_category_stats(receiving_players)

    projected = {}
    impact = {}
    for cat in config.ALL_CATEGORIES:
        before = current_totals.get(cat, 0)
        lost = giving_stats.get(cat, 0)
        gained = receiving_stats.get(cat, 0)

        if cat in config.RATIO_STATS:
            projected[cat] = before
            impact[cat] = 0
        else:
            projected[cat] = before - lost + gained
            impact[cat] = gained - lost

    rows = []
    upgrades = []
    downgrades = []

    for cat in config.ALL_CATEGORIES:
        change = impact.get(cat, 0)

        if cat in config.LOWER_IS_BETTER:
            is_improvement = change < 0
        else:
            is_improvement = change > 0

        verdict = "향상" if is_improvement else ("하락" if change != 0 else "변동없음")

        if is_improvement:
            upgrades.append(cat)
        elif change != 0:
            downgrades.append(cat)

        rows.append({
            "category": cat,
            "before": round(current_totals.get(cat, 0), 3),
            "after": round(projected.get(cat, 0), 3),
            "change": round(change, 3),
            "verdict": verdict,
        })

    impact_df = pd.DataFrame(rows)

    net = len(upgrades) - len(downgrades)
    if net > 0:
        overall = f"유리한 트레이드 (↑{len(upgrades)} ↓{len(downgrades)})"
    elif net < 0:
        overall = f"불리한 트레이드 (↑{len(upgrades)} ↓{len(downgrades)})"
    else:
        overall = f"동등한 트레이드 (↑{len(upgrades)} ↓{len(downgrades)})"

    return {
        "overall": overall,
        "impact_df": impact_df,
        "upgrades": upgrades,
        "downgrades": downgrades,
        "giving": giving_players,
        "receiving": [p.name for p in receiving_players],
        "summary": _generate_trade_summary(upgrades, downgrades, giving_players, receiving_players),
    }


def compare_player_value(player_a, player_b) -> pd.DataFrame:
    """두 선수의 카테고리별 가치를 비교한다."""
    stats_a = get_blended_stats(player_a, is_pitcher=_is_pitcher(player_a))
    stats_b = get_blended_stats(player_b, is_pitcher=_is_pitcher(player_b))

    rows = []
    for cat in config.ALL_CATEGORIES:
        val_a = get_stat_value(stats_a, cat)
        val_b = get_stat_value(stats_b, cat)

        if cat in config.LOWER_IS_BETTER:
            better = player_a.name if val_a < val_b else player_b.name
        else:
            better = player_a.name if val_a > val_b else player_b.name

        rows.append({
            "category": cat,
            player_a.name: round(val_a, 3),
            player_b.name: round(val_b, 3),
            "better": better if val_a != val_b else "동일",
        })

    return pd.DataFrame(rows)


def _sum_category_stats(players: list) -> dict:
    """선수 리스트의 카테고리별 스탯을 합산한다."""
    totals = {cat: 0.0 for cat in config.ALL_CATEGORIES}
    total_h, total_ab = 0, 0
    total_er, total_outs = 0.0, 0.0
    total_bb_p, total_ha = 0, 0

    for player in players:
        is_pitcher = _is_pitcher(player)
        stats = get_blended_stats(player, is_pitcher=is_pitcher)
        if not stats:
            continue

        for cat in ["R", "HR", "RBI", "SB"]:
            totals[cat] += get_stat_value(stats, cat)

        for cat in ["K", "W", "SV", "HD"]:
            totals[cat] += get_stat_value(stats, cat)

        total_h += get_stat_value(stats, "H")
        total_ab += get_stat_value(stats, "AB")
        total_er += get_stat_value(stats, "ER")
        total_outs += stats.get("OUTS", 0) or 0
        total_bb_p += get_stat_value(stats, "BB")
        total_ha += get_stat_value(stats, "HA")

    totals["AVG"] = total_h / total_ab if total_ab > 0 else 0.0
    total_ip = total_outs / 3.0 if total_outs > 0 else 0.0
    totals["ERA"] = (total_er * 9) / total_ip if total_ip > 0 else 0.0
    totals["WHIP"] = (total_bb_p + total_ha) / total_ip if total_ip > 0 else 0.0

    return totals


def _is_pitcher(player) -> bool:
    """선수가 투수인지 판별."""
    pos = player.position if hasattr(player, "position") else ""
    eligible = player.eligibleSlots if hasattr(player, "eligibleSlots") else []
    return pos in PITCHER_POSITIONS or any(s in PITCHER_POSITIONS for s in eligible)


def _generate_trade_summary(upgrades, downgrades, giving, receiving) -> str:
    """트레이드 요약 문장을 생성한다."""
    giving_names = ", ".join(giving)
    receiving_names = ", ".join([p.name for p in receiving])

    parts = [f"[보내는 선수] {giving_names}", f"[받는 선수] {receiving_names}"]

    if upgrades:
        parts.append(f"[향상 카테고리] {', '.join(upgrades)}")
    if downgrades:
        parts.append(f"[하락 카테고리] {', '.join(downgrades)}")

    return "\n".join(parts)
