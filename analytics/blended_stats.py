"""실제 스탯 + ESPN Projection 블렌딩 모듈.

시즌 초반에는 ESPN projection 비중을 높이고,
실제 데이터가 쌓이면 점진적으로 실제 스탯 비중을 높인다.

블렌딩 가중치:
  - 타자: AB(타석) 기준 → 200AB 이상이면 실제 스탯 90% 반영
  - 투수: OUTS 기준 → 240 OUTS(=80IP) 이상이면 실제 스탯 90% 반영
"""

from datetime import datetime

from analytics.matchup import get_player_breakdown, get_player_projection, get_stat_value, STAT_KEY_MAP

# 블렌딩 설정
HITTER_SAMPLE_THRESHOLD = 200   # AB 기준
PITCHER_SAMPLE_THRESHOLD = 240  # OUTS 기준 (= 80 IP)
MIN_ACTUAL_WEIGHT = 0.10        # 실제 스탯 최소 비중
MAX_ACTUAL_WEIGHT = 0.90        # 실제 스탯 최대 비중


def get_blended_stats(player, is_pitcher: bool = False) -> dict:
    """실제 스탯 + projection 블렌딩 결과를 반환한다.

    Returns:
        블렌딩된 breakdown dict (문자열 키)
    """
    actual = get_player_breakdown(player)
    projection = get_player_projection(player)

    if not actual and not projection:
        return {}
    if not actual:
        return projection
    if not projection:
        return actual

    # 블렌딩
    weight = _calculate_actual_weight(actual, is_pitcher)
    return _blend(actual, projection, weight, is_pitcher)


def get_blend_info(player, is_pitcher: bool = False) -> dict:
    """블렌딩 정보 (UI 표시용)."""
    actual = get_player_breakdown(player)
    projection = get_player_projection(player)

    has_actual = bool(actual)
    has_proj = bool(projection)

    if has_actual and has_proj:
        weight = _calculate_actual_weight(actual, is_pitcher)
        if is_pitcher:
            sample = actual.get("OUTS", 0) or 0
            sample_label = f"{sample / 3:.1f} IP"
        else:
            sample = actual.get("AB", 0) or 0
            sample_label = f"{int(sample)} AB"
    elif has_actual:
        weight = 1.0
        sample_label = "projection 없음"
    else:
        weight = 0.0
        sample_label = "실제 데이터 없음"

    return {
        "actual_weight": round(weight, 2),
        "proj_weight": round(1 - weight, 2),
        "sample": sample_label,
        "has_actual": has_actual,
        "has_projection": has_proj,
    }


def get_season_blend_summary() -> dict:
    """현재 시즌 진행도 기반 블렌딩 요약."""
    today = datetime.now()
    season_start = datetime(today.year, 3, 27)
    season_end = datetime(today.year, 9, 28)
    total_days = (season_end - season_start).days
    elapsed = max(0, (today - season_start).days)
    progress = min(elapsed / total_days, 1.0)

    return {
        "season_progress": round(progress * 100, 1),
        "elapsed_days": elapsed,
        "total_days": total_days,
        "recommendation": _get_blend_recommendation(progress),
    }


def is_loaded() -> bool:
    """블렌딩 사용 가능 여부. projection은 ESPN이 항상 제공하므로 True."""
    return True


def _calculate_actual_weight(actual: dict, is_pitcher: bool) -> float:
    """실제 스탯 비중 계산."""
    if is_pitcher:
        sample = actual.get("OUTS", 0) or 0
        threshold = PITCHER_SAMPLE_THRESHOLD
    else:
        sample = actual.get("AB", 0) or 0
        threshold = HITTER_SAMPLE_THRESHOLD

    if sample <= 0:
        return MIN_ACTUAL_WEIGHT

    weight = MIN_ACTUAL_WEIGHT + (MAX_ACTUAL_WEIGHT - MIN_ACTUAL_WEIGHT) * min(sample / threshold, 1.0)
    return weight


def _blend(actual: dict, projection: dict, actual_weight: float, is_pitcher: bool) -> dict:
    """실제 스탯과 projection을 블렌딩.

    비율 스탯 (AVG, ERA, WHIP, OBP, SLG, OPS 등): 가중 평균
    카운팅 스탯 (R, HR, K 등): per-game rate 블렌딩 → 프로젝션 게임 수로 환산
    """
    proj_weight = 1.0 - actual_weight
    blended = {}

    # 비율 스탯: 가중 평균
    ratio_keys = {"AVG", "ERA", "WHIP", "OBP", "SLG", "OPS", "K/9", "K/BB", "WPCT", "SV%", "OBA", "OOBP", "FPCT", "PPA"}

    # 프로젝션 게임 수 (시즌 전체 기준)
    proj_games = projection.get("G", 0) or 150
    actual_games = actual.get("G", 0) or 0
    proj_outs = projection.get("OUTS", 0) or 0

    all_keys = set(actual.keys()) | set(projection.keys())

    for key in all_keys:
        act_val = actual.get(key)
        proj_val = projection.get(key)

        # None 처리
        if act_val is None:
            act_val = 0.0
        if proj_val is None:
            proj_val = 0.0

        try:
            act_val = float(act_val)
            proj_val = float(proj_val)
        except (ValueError, TypeError):
            blended[key] = act_val
            continue

        if key in ratio_keys:
            # 비율 스탯: 가중 평균
            blended[key] = act_val * actual_weight + proj_val * proj_weight
        else:
            # 카운팅 스탯: per-game rate 블렌딩
            if is_pitcher:
                act_denom = actual.get("OUTS", 0) or 0
                proj_denom = projection.get("OUTS", 0) or 0
            else:
                act_denom = actual_games
                proj_denom = proj_games

            act_rate = act_val / max(act_denom, 1)
            proj_rate = proj_val / max(proj_denom, 1)

            blended_rate = act_rate * actual_weight + proj_rate * proj_weight

            # 프로젝션 규모로 환산 (전체 시즌 기준)
            if is_pitcher:
                blended[key] = blended_rate * max(proj_denom, 1)
            else:
                blended[key] = blended_rate * max(proj_denom, 1)

    return blended


def _get_blend_recommendation(progress: float) -> str:
    """시즌 진행도에 따른 블렌딩 추천 메시지."""
    if progress < 0.05:
        return "시즌 극초반 → Projection 위주 (90%+)"
    elif progress < 0.15:
        return "시즌 초반 → Projection 높은 비중 (70-80%)"
    elif progress < 0.35:
        return "시즌 중반 진입 → 균형 블렌딩 (50:50)"
    elif progress < 0.60:
        return "시즌 중반 → 실제 스탯 높은 비중 (60-70%)"
    else:
        return "시즌 후반 → 실제 스탯 위주 (80%+)"
