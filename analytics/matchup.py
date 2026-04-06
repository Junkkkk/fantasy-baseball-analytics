"""매치업 시뮬레이션 & 카테고리별 승패 예측."""

import pandas as pd
import numpy as np

import config


# ESPN API breakdown 키 매핑
# breakdown dict에서 사용하는 문자열 키
STAT_KEY_MAP = {
    # 타자
    "R": "R",
    "HR": "HR",
    "RBI": "RBI",
    "SB": "SB",
    "AVG": "AVG",
    "H": "H",
    "AB": "AB",
    "G": "G",
    # 투수
    "K": "K",
    "W": "W",
    "SV": "SV",
    "HD": "HLD",       # ESPN은 'HLD'로 표기
    "ERA": "ERA",
    "WHIP": "WHIP",
    "ER": "ER",
    "IP": "OUTS",       # ESPN은 OUTS로 반환 (IP = OUTS / 3)
    "BB": "P_BB",       # 투수 볼넷
    "HA": "P_H",        # 투수 피안타
}

# 하위 호환: 기존 코드에서 STAT_ID_MAP을 import하는 곳 대응
STAT_ID_MAP = STAT_KEY_MAP


def get_player_breakdown(player, period: int = 0) -> dict:
    """선수의 breakdown 스탯을 반환한다.

    Args:
        player: ESPN 선수 객체
        period: 0=시즌 전체, 다른 값=특정 매치업 기간

    Returns:
        breakdown dict (문자열 키)
    """
    if not hasattr(player, "stats") or not player.stats:
        return {}

    if period in player.stats:
        stat_data = player.stats[period]
        if isinstance(stat_data, dict):
            return stat_data.get("breakdown", {})

    # 지정 period 없으면 첫 번째 사용 가능한 breakdown 반환
    for pk, pv in player.stats.items():
        if isinstance(pv, dict) and "breakdown" in pv:
            bd = pv["breakdown"]
            if isinstance(bd, dict) and len(bd) > 0:
                return bd
    return {}


def get_player_projection(player) -> dict:
    """선수의 시즌 프로젝션(projected_breakdown)을 반환한다."""
    if not hasattr(player, "stats") or not player.stats:
        return {}

    for pk, pv in player.stats.items():
        if isinstance(pv, dict) and "projected_breakdown" in pv:
            pb = pv["projected_breakdown"]
            if isinstance(pb, dict) and len(pb) > 0:
                return pb
    return {}


def get_stat_value(breakdown: dict, category: str) -> float:
    """breakdown에서 카테고리 값을 가져온다."""
    key = STAT_KEY_MAP.get(category, category)
    val = breakdown.get(key)
    if val is None:
        return 0.0
    return float(val)


def extract_category_stats(box_score, team_side: str) -> dict:
    """박스스코어에서 팀의 카테고리별 스탯을 추출한다."""
    # H2H Categories 리그는 box_score에 home_stats/away_stats가 직접 제공됨
    direct_stats = getattr(box_score, f"{team_side}_stats", None)
    if direct_stats:
        totals = {}
        for cat in config.ALL_CATEGORIES:
            key = STAT_KEY_MAP.get(cat, cat)
            entry = direct_stats.get(key, {})
            val = entry.get("value", 0) if isinstance(entry, dict) else 0
            if val == "Infinity" or val == "-Infinity":
                val = 0.0
            try:
                totals[cat] = float(val)
            except (ValueError, TypeError):
                totals[cat] = 0.0
        return totals

    # Fallback: 라인업에서 직접 계산
    lineup = getattr(box_score, f"{team_side}_lineup", None)
    if lineup is None:
        return {cat: 0.0 for cat in config.ALL_CATEGORIES}
    totals = {cat: 0.0 for cat in config.ALL_CATEGORIES}

    total_h, total_ab = 0, 0
    total_er, total_outs = 0.0, 0.0
    total_bb_p, total_ha = 0, 0

    for player in lineup:
        bd = get_player_breakdown(player)
        if not bd:
            continue

        # 카운팅 스탯 누적
        for cat in ["R", "HR", "RBI", "SB"]:
            totals[cat] += get_stat_value(bd, cat)

        for cat in ["K", "W", "SV", "HD"]:
            totals[cat] += get_stat_value(bd, cat)

        # 비율 계산용
        total_h += get_stat_value(bd, "H")
        total_ab += get_stat_value(bd, "AB")
        total_er += get_stat_value(bd, "ER")
        total_outs += get_stat_value(bd, "IP")  # 실제로는 OUTS
        total_bb_p += get_stat_value(bd, "BB")
        total_ha += get_stat_value(bd, "HA")

    # 비율 스탯 계산
    totals["AVG"] = total_h / total_ab if total_ab > 0 else 0.0
    total_ip = total_outs / 3.0 if total_outs > 0 else 0.0
    totals["ERA"] = (total_er * 9) / total_ip if total_ip > 0 else 0.0
    totals["WHIP"] = (total_bb_p + total_ha) / total_ip if total_ip > 0 else 0.0

    return totals


def compare_categories(my_stats: dict, opp_stats: dict) -> pd.DataFrame:
    """두 팀의 카테고리별 비교 결과를 반환한다."""
    rows = []
    for cat in config.ALL_CATEGORIES:
        my_val = my_stats.get(cat, 0)
        opp_val = opp_stats.get(cat, 0)

        if cat in config.LOWER_IS_BETTER:
            if my_val < opp_val:
                result = "WIN"
            elif my_val > opp_val:
                result = "LOSE"
            else:
                result = "TIE"
        else:
            if my_val > opp_val:
                result = "WIN"
            elif my_val < opp_val:
                result = "LOSE"
            else:
                result = "TIE"

        diff = my_val - opp_val
        if cat in config.LOWER_IS_BETTER:
            diff = -diff

        rows.append({
            "category": cat,
            "my_stat": round(my_val, 3),
            "opp_stat": round(opp_val, 3),
            "diff": round(diff, 3),
            "result": result,
        })

    return pd.DataFrame(rows)


def simulate_matchup(my_stats: dict, opp_stats: dict, my_remaining: dict, opp_remaining: dict) -> pd.DataFrame:
    """잔여 경기 예측을 포함한 매치업 시뮬레이션."""
    rows = []
    for cat in config.ALL_CATEGORIES:
        current_my = my_stats.get(cat, 0)
        current_opp = opp_stats.get(cat, 0)
        remaining_my = my_remaining.get(cat, 0)
        remaining_opp = opp_remaining.get(cat, 0)

        if cat in config.RATIO_STATS:
            projected_my = current_my
            projected_opp = current_opp
        else:
            projected_my = current_my + remaining_my
            projected_opp = current_opp + remaining_opp

        if cat in config.LOWER_IS_BETTER:
            result = "WIN" if projected_my < projected_opp else ("LOSE" if projected_my > projected_opp else "TIE")
            margin = projected_opp - projected_my
        else:
            result = "WIN" if projected_my > projected_opp else ("LOSE" if projected_my < projected_opp else "TIE")
            margin = projected_my - projected_opp

        rows.append({
            "category": cat,
            "current_my": round(current_my, 3),
            "current_opp": round(current_opp, 3),
            "projected_my": round(projected_my, 3),
            "projected_opp": round(projected_opp, 3),
            "margin": round(margin, 3),
            "result": result,
        })

    return pd.DataFrame(rows)


def get_strategy_recommendations(comparison_df: pd.DataFrame) -> list[dict]:
    """매치업 비교 결과를 기반으로 전략 추천을 생성한다."""
    recommendations = []
    wins = comparison_df[comparison_df["result"] == "WIN"]
    losses = comparison_df[comparison_df["result"] == "LOSE"]
    ties = comparison_df[comparison_df["result"] == "TIE"]

    total_cats = len(config.ALL_CATEGORIES)
    win_count = len(wins)
    loss_count = len(losses)

    recommendations.append({
        "category": "전체",
        "action": "요약",
        "reason": f"현재 {win_count}승 {loss_count}패 {len(ties)}무 → "
                  f"{'유리' if win_count > total_cats // 2 else '불리'}한 상황",
    })

    for _, row in comparison_df.iterrows():
        cat = row["category"]
        diff = abs(row["diff"])

        if row["result"] == "LOSE" and diff < _get_threshold(cat):
            recommendations.append({
                "category": cat,
                "action": "집중",
                "reason": f"{cat}에서 근소하게 뒤짐 (차이: {row['diff']:.3f}). 역전 가능성 있음!",
            })
        elif row["result"] == "WIN" and diff < _get_threshold(cat):
            recommendations.append({
                "category": cat,
                "action": "수비",
                "reason": f"{cat}에서 근소 리드 (차이: {row['diff']:.3f}). 리드 유지 필요.",
            })
        elif row["result"] == "LOSE" and diff >= _get_threshold(cat) * 3:
            recommendations.append({
                "category": cat,
                "action": "포기",
                "reason": f"{cat}에서 큰 차이로 뒤짐 (차이: {row['diff']:.3f}). 다른 카테고리에 집중 권장.",
            })

    return recommendations


def _get_threshold(category: str) -> float:
    """카테고리별 '접전' 판단 임계값."""
    thresholds = {
        "R": 5, "HR": 2, "RBI": 5, "SB": 2, "AVG": 0.010,
        "K": 10, "W": 1, "SV": 1, "HD": 1, "ERA": 0.50, "WHIP": 0.05,
    }
    return thresholds.get(category, 3)


def estimate_remaining_stats(roster: list, games_remaining: int) -> dict:
    """로스터의 최근 성적 기반으로 잔여 경기 예상 스탯을 계산한다."""
    per_game = {cat: 0.0 for cat in config.ALL_CATEGORIES if cat not in config.RATIO_STATS}

    for player in roster:
        bd = get_player_breakdown(player)
        if not bd:
            continue

        games = get_stat_value(bd, "G")
        if games <= 0:
            continue

        for cat in per_game:
            val = get_stat_value(bd, cat)
            per_game[cat] += val / games

    return {cat: val * games_remaining for cat, val in per_game.items()}
