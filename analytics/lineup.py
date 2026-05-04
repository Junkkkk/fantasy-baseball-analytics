"""최적 라인업 추천 모듈."""

import pandas as pd

import config
from analytics.matchup import get_player_breakdown, get_stat_value
from analytics.scoring import (
    score_hitter_zscore, score_pitcher_zscore, is_norms_loaded,
)


# ESPN 포지션 슬롯 매핑
POSITION_SLOTS = {
    "C": "C", "1B": "1B", "2B": "2B", "3B": "3B", "SS": "SS",
    "LF": "OF", "CF": "OF", "RF": "OF", "OF": "OF",
    "DH": "UTIL", "UTIL": "UTIL",
    "SP": "SP", "RP": "RP", "P": "P",
}

HITTER_POSITIONS = {"C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "OF", "DH", "UTIL"}
PITCHER_POSITIONS = {"SP", "RP", "P"}


def classify_players(roster: list) -> tuple[list, list]:
    """로스터를 타자와 투수로 분류한다."""
    hitters = []
    pitchers = []
    for player in roster:
        pos = player.position if hasattr(player, "position") else ""
        eligible = player.eligibleSlots if hasattr(player, "eligibleSlots") else []

        if pos in PITCHER_POSITIONS or any(s in PITCHER_POSITIONS for s in eligible):
            pitchers.append(player)
        else:
            hitters.append(player)
    return hitters, pitchers


def recommend_lineup(roster: list, matchup_context: dict = None) -> pd.DataFrame:
    """최적 라인업을 추천한다."""
    hitters, pitchers = classify_players(roster)

    hitter_scores = [score_hitter_zscore(p, matchup_context) for p in hitters]
    hitter_scores.sort(key=lambda x: x["score"], reverse=True)

    pitcher_scores = [score_pitcher_zscore(p, matchup_context) for p in pitchers]
    pitcher_scores.sort(key=lambda x: x["score"], reverse=True)

    rows = []
    for h in hitter_scores:
        cat_str = ", ".join(f"{c}:{v:+.1f}" for c, v in h.get("category_scores", {}).items())
        reason = h.get("reason", "")
        adj = h.get("matchup_adj", 1.0)
        adj_str = f"{adj:.0%}" if adj != 1.0 else ""
        rows.append({
            "name": h["name"],
            "position": h["position"],
            "type": "타자",
            "경기": h.get("game_today", ""),
            "상대": h.get("opponent", ""),
            "상대SP": h.get("opp_pitcher", ""),
            "SP ERA": h.get("opp_era", ""),
            "vs SP": h.get("vs_SP", "-"),
            "wRC+": h.get("wRC+", "-"),
            "구장보정": adj_str,
            "score": h["score"],
            "카테고리별": cat_str,
            "recommendation": "선발" if h["score"] > 0 else "벤치",
            "사유": reason,
            "injury": h["injury"],
        })

    for p in pitcher_scores:
        cat_str = ", ".join(f"{c}:{v:+.1f}" for c, v in p.get("category_scores", {}).items())
        reason = p.get("reason", "")
        adj = p.get("matchup_adj", 1.0)
        adj_str = f"{adj:.0%}" if adj != 1.0 else ""
        rows.append({
            "name": p["name"],
            "position": p["position"],
            "type": "투수",
            "경기": p.get("game_today", ""),
            "상대": p.get("opponent", ""),
            "상대SP": "",
            "SP ERA": "",
            "구장보정": adj_str,
            "score": p["score"],
            "카테고리별": cat_str,
            "recommendation": "선발" if p["score"] > 0 else "벤치",
            "사유": reason,
            "injury": p["injury"],
        })

    return pd.DataFrame(rows)


def get_injury_alerts(roster: list) -> list[dict]:
    """부상 선수 알림을 반환한다."""
    alerts = []
    for player in roster:
        status = getattr(player, "injuryStatus", "ACTIVE")
        if status not in ("ACTIVE", "NORMAL", None):
            slot = getattr(player, "lineupSlot", "BENCH")
            alerts.append({
                "name": player.name,
                "position": player.position,
                "injury_status": status,
                "lineup_slot": slot,
                "action": "벤치로 이동 필요" if slot != "BE" and slot != "IL" else "이미 벤치/IL",
            })
    return alerts


def _get_best_stats(player) -> dict:
    """선수의 가장 적절한 breakdown 스탯을 반환한다. (하위 호환용)"""
    return get_player_breakdown(player)
