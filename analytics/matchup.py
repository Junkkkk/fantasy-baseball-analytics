"""매치업 시뮬레이션 & 카테고리별 승패 예측."""

import pandas as pd
import numpy as np

import config


# ESPN API breakdown 키 매핑
# breakdown dict에서 사용하는 문자열 키 (13개 카테고리 리그)
STAT_KEY_MAP = {
    # 타자 (스코어링 7개)
    "H": "H",
    "HR": "HR",
    "RBI": "RBI",
    "SB": "SB",
    "OPS": "OPS",
    "GDP": "GDP",
    "E": "E",
    # 투수 (스코어링 6개)
    "OUTS": "OUTS",     # 이닝 카운팅 (IP*3)
    "W": "W",
    "K": "K",
    "SVHD": "SVHD",     # Saves + Holds
    "K/BB": "K/BB",
    "ERA": "ERA",
    # 참조용 (계산/표시)
    "AVG": "AVG",
    "R": "R",
    "AB": "AB",
    "G": "G",
    "SV": "SV",
    "HD": "HLD",
    "WHIP": "WHIP",
    "ER": "ER",
    "IP": "OUTS",
    "BB": "P_BB",
    "HA": "P_H",
    "B_BB": "B_BB",     # 타자 볼넷 (OPS 계산용)
    "SF": "SF",
    "HBP": "HBP",
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
    total_bb_h, total_hbp, total_sf = 0, 0, 0  # OPS 분모용
    total_2b, total_3b, total_hr_h = 0, 0, 0    # SLG용
    total_er, total_outs = 0.0, 0.0
    total_bb_p, total_k_p = 0, 0

    for player in lineup:
        bd = get_player_breakdown(player)
        if not bd:
            continue

        # 타자 카운팅 (H, HR, RBI, SB, GDP, E)
        for cat in ["H", "HR", "RBI", "SB", "GDP", "E"]:
            totals[cat] += get_stat_value(bd, cat)

        # 투수 카운팅 (OUTS, W, K, SVHD)
        for cat in ["OUTS", "W", "K"]:
            totals[cat] += get_stat_value(bd, cat)
        # SVHD = SV + HLD (원본 SVHD 키가 있으면 사용, 없으면 합산)
        svhd_direct = get_stat_value(bd, "SVHD")
        if svhd_direct > 0:
            totals["SVHD"] += svhd_direct
        else:
            totals["SVHD"] += get_stat_value(bd, "SV") + get_stat_value(bd, "HD")

        # 비율 계산용
        total_h += get_stat_value(bd, "H")
        total_ab += get_stat_value(bd, "AB")
        total_bb_h += get_stat_value(bd, "B_BB")
        total_hbp += get_stat_value(bd, "HBP")
        total_sf += get_stat_value(bd, "SF")
        total_2b += get_stat_value(bd, "2B") if "2B" in bd else 0
        total_3b += get_stat_value(bd, "3B") if "3B" in bd else 0
        total_hr_h += get_stat_value(bd, "HR")
        total_er += get_stat_value(bd, "ER")
        total_outs += get_stat_value(bd, "IP")  # 실제로는 OUTS
        total_bb_p += get_stat_value(bd, "BB")
        total_k_p += get_stat_value(bd, "K")

    # OPS = OBP + SLG
    obp_denom = total_ab + total_bb_h + total_hbp + total_sf
    obp = (total_h + total_bb_h + total_hbp) / obp_denom if obp_denom > 0 else 0.0
    total_1b = total_h - total_2b - total_3b - total_hr_h
    tb = total_1b + 2 * total_2b + 3 * total_3b + 4 * total_hr_h
    slg = tb / total_ab if total_ab > 0 else 0.0
    totals["OPS"] = obp + slg

    # ERA = ER*9 / IP
    total_ip = total_outs / 3.0 if total_outs > 0 else 0.0
    totals["ERA"] = (total_er * 9) / total_ip if total_ip > 0 else 0.0

    # K/BB = 탈삼진 / 볼넷
    totals["K/BB"] = total_k_p / total_bb_p if total_bb_p > 0 else (total_k_p if total_k_p > 0 else 0.0)

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


def get_strategy_recommendations(comparison_df: pd.DataFrame, matchup_progress: float = 1.0) -> list[dict]:
    """매치업 비교 결과를 기반으로 전략 추천을 생성한다.

    Args:
        comparison_df: 카테고리별 비교 결과
        matchup_progress: 매치업 진행도 (0.0 = 시작 직후, 1.0 = 마지막 날)
                          주중 표본이 적을 때는 분류를 보수적으로 처리한다.
    """
    recommendations = []
    wins = comparison_df[comparison_df["result"] == "WIN"]
    losses = comparison_df[comparison_df["result"] == "LOSE"]
    ties = comparison_df[comparison_df["result"] == "TIE"]

    total_cats = len(config.ALL_CATEGORIES)
    win_count = len(wins)
    loss_count = len(losses)

    progress_pct = int(matchup_progress * 100)
    recommendations.append({
        "category": "전체",
        "action": "요약",
        "reason": f"현재 {win_count}승 {loss_count}패 {len(ties)}무 → "
                  f"{'유리' if win_count > total_cats // 2 else '불리'}한 상황 "
                  f"(매치업 진행도: {progress_pct}%)",
    })

    # 매치업 초반 (20% 미만 ≈ 첫날~1.5일차): 표본 부족으로 전략 분류 자제
    if matchup_progress < 0.20:
        recommendations.append({
            "category": "전체",
            "action": "관망",
            "reason": "매치업 초반이라 표본이 적습니다. 며칠 더 지나봐야 의미 있는 추세가 보입니다. "
                      "오늘 라인업/FA는 평소대로 운영하세요.",
        })
        return recommendations

    # 진행도에 따른 임계값 조정
    # 초반일수록 더 큰 차이가 있어야 '근소' 또는 '큰 차이'로 판정
    # progress=0.2 → 4배, progress=0.5 → 2배, progress=1.0 → 1배
    threshold_multiplier = max(1.0, 1.0 / matchup_progress)
    # 포기 판정은 더 보수적: 매치업 끝나갈 때만 적극적으로
    abandon_multiplier = threshold_multiplier * (1.0 + (1.0 - matchup_progress) * 2.0)

    for _, row in comparison_df.iterrows():
        cat = row["category"]
        diff = abs(row["diff"])
        base_threshold = _get_threshold(cat)
        close_threshold = base_threshold * threshold_multiplier
        abandon_threshold = base_threshold * 3 * abandon_multiplier

        if row["result"] == "LOSE" and diff < close_threshold:
            confidence = "역전 가능성 있음" if matchup_progress >= 0.5 else "초반이라 추세 미확정"
            recommendations.append({
                "category": cat,
                "action": "집중",
                "reason": f"{cat}에서 근소하게 뒤짐 (차이: {row['diff']:.3f}). {confidence}.",
            })
        elif row["result"] == "WIN" and diff < close_threshold:
            recommendations.append({
                "category": cat,
                "action": "수비",
                "reason": f"{cat}에서 근소 리드 (차이: {row['diff']:.3f}). 리드 유지 필요.",
            })
        elif row["result"] == "LOSE" and diff >= abandon_threshold:
            recommendations.append({
                "category": cat,
                "action": "포기",
                "reason": f"{cat}에서 큰 차이로 뒤짐 (차이: {row['diff']:.3f}). 다른 카테고리에 집중 권장.",
            })

    return recommendations


def calculate_matchup_progress(matchup_period: int = None) -> float:
    """현재 매치업 진행도를 계산한다 (0.0 ~ 1.0).

    ESPN H2H 매치업은 월요일~일요일 7일 단위.
    """
    from datetime import datetime
    today = datetime.now()
    # weekday(): 월=0, 일=6
    day_of_week = today.weekday()
    # 매치업 첫날(월) 기준으로 경과 진행도
    # 월 = 1/7, 화 = 2/7, ..., 일 = 7/7
    progress = (day_of_week + 1) / 7.0
    return progress


def _get_threshold(category: str) -> float:
    """카테고리별 '접전' 판단 임계값 (13개 리그)."""
    thresholds = {
        # 타자
        "H": 5, "HR": 2, "RBI": 5, "SB": 2,
        "OPS": 0.020, "GDP": 1, "E": 1,
        # 투수
        "OUTS": 9, "W": 1, "K": 10, "SVHD": 1,
        "K/BB": 0.30, "ERA": 0.50,
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


def project_weekly_totals(my_stats: dict, opp_stats: dict,
                          my_roster: list, opp_roster: list) -> pd.DataFrame:
    """현재 스탯 + 남은 경기 예상치를 합산하여 이번 주 최종 예상 성적을 보여준다.

    Returns:
        DataFrame: category, my_current, my_projected, opp_current, opp_projected, projected_result
    """
    progress = calculate_matchup_progress()
    # 남은 일수 기반 잔여 경기 추정 (팀당 하루 평균 ~1경기)
    days_remaining = max(1, round((1.0 - progress) * 7))

    my_remaining = estimate_remaining_stats(my_roster, days_remaining)
    opp_remaining = estimate_remaining_stats(opp_roster, days_remaining)

    rows = []
    for cat in config.ALL_CATEGORIES:
        my_cur = my_stats.get(cat, 0)
        opp_cur = opp_stats.get(cat, 0)

        if cat in config.RATIO_STATS:
            # 비율 스탯은 현재값 유지 (경기가 쌓이면 자연히 수렴)
            my_proj = my_cur
            opp_proj = opp_cur
        else:
            my_proj = my_cur + my_remaining.get(cat, 0)
            opp_proj = opp_cur + opp_remaining.get(cat, 0)

        # 예상 승패
        if cat in config.LOWER_IS_BETTER:
            result = "WIN" if my_proj <= opp_proj else "LOSE"
        else:
            result = "WIN" if my_proj >= opp_proj else "LOSE"
        if abs(my_proj - opp_proj) < 0.001:
            result = "TIE"

        rows.append({
            "category": cat,
            "현재(나)": round(my_cur, 3),
            "예상(나)": round(my_proj, 3) if cat not in config.RATIO_STATS else "-",
            "현재(상대)": round(opp_cur, 3),
            "예상(상대)": round(opp_proj, 3) if cat not in config.RATIO_STATS else "-",
            "예상결과": result,
        })

    return pd.DataFrame(rows)
