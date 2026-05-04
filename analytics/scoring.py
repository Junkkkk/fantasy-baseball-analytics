"""Z-score 기반 선수 스코어링 모듈.

리그 전체 선수의 프로젝션 스탯을 분석하여
각 카테고리가 동등한 영향력을 갖도록 정규화한다.

점수 = Σ z-score(카테고리) × 매치업_가중치
  - z-score = (선수값 - 리그평균) / 리그표준편차
  - ERA/GDP/E는 낮을수록 좋으므로 부호 반전

리그 카테고리 (13개):
  타자: H, HR, RBI, SB, OPS, GDP(↓), E(↓)
  투수: OUTS, W, K, SVHD, K/BB, ERA(↓)
"""

import numpy as np

import config
from analytics.matchup import get_player_projection, get_stat_value
from analytics.blended_stats import get_blended_stats
from analytics.schedule import has_game_today, get_opponent_today, get_matchup_adjustment


# 리그 통계 캐시
_league_norms: dict = {}
_norms_loaded = False


def compute_league_norms(league):
    """리그 전체 선수의 카테고리별 평균/표준편차를 계산한다.

    Args:
        league: ESPN League 객체
    """
    global _league_norms, _norms_loaded

    pitcher_positions = {"SP", "RP", "P"}

    hitter_stats = {cat: [] for cat in config.HITTING_CATEGORIES}
    pitcher_stats = {cat: [] for cat in config.PITCHING_CATEGORIES}

    for team in league.teams:
        for player in team.roster:
            proj = get_player_projection(player)
            if not proj:
                continue

            pos = player.position or ""
            eligible = player.eligibleSlots if hasattr(player, "eligibleSlots") else []
            is_pitcher = pos in pitcher_positions or any(s in pitcher_positions for s in eligible)

            if is_pitcher:
                for cat in config.PITCHING_CATEGORIES:
                    val = get_stat_value(proj, cat)
                    if val > 0:
                        pitcher_stats[cat].append(val)
            else:
                for cat in config.HITTING_CATEGORIES:
                    val = get_stat_value(proj, cat)
                    if val > 0:
                        hitter_stats[cat].append(val)

    # 평균 & 표준편차 계산
    for cat in config.HITTING_CATEGORIES:
        vals = hitter_stats[cat]
        if len(vals) >= 3:
            _league_norms[cat] = {
                "mean": np.mean(vals),
                "std": max(np.std(vals), 0.001),  # 0 방지
                "type": "hitter",
            }

    for cat in config.PITCHING_CATEGORIES:
        vals = pitcher_stats[cat]
        if len(vals) >= 3:
            _league_norms[cat] = {
                "mean": np.mean(vals),
                "std": max(np.std(vals), 0.001),
                "type": "pitcher",
            }

    _norms_loaded = True


def z_score(value: float, category: str) -> float:
    """카테고리 값의 z-score를 계산한다.

    ERA/GDP/E는 낮을수록 좋으므로 부호를 반전한다.
    """
    if category not in _league_norms:
        return 0.0

    norm = _league_norms[category]
    z = (value - norm["mean"]) / norm["std"]

    if category in config.LOWER_IS_BETTER:
        z = -z  # 낮을수록 좋으니 부호 반전

    return z


def score_hitter_zscore(player, matchup_context: dict = None) -> dict:
    """Z-score 기반 타자 점수를 계산한다."""
    details = {
        "name": player.name,
        "position": player.position,
        "injury": getattr(player, "injuryStatus", "ACTIVE"),
        "proTeam": getattr(player, "proTeam", ""),
    }

    injury = getattr(player, "injuryStatus", "ACTIVE")
    if injury in ("OUT", "IL", "IL10", "IL60", "SUSPENSION",
                  "FIFTEEN_DAY_DL", "SIXTY_DAY_DL", "TEN_DAY_DL"):
        details["score"] = 0
        details["reason"] = f"부상/결장 ({injury})"
        details["category_scores"] = {}
        return details

    # 오늘 경기 유무 확인
    game_today = has_game_today(player)
    opponent = get_opponent_today(player)
    details["game_today"] = "O" if game_today else "X"
    details["opponent"] = opponent

    if not game_today:
        details["score"] = 0
        details["reason"] = "오늘 경기 없음"
        details["category_scores"] = {}
        return details

    # 매치업 조정 (상대 투수 + 구장)
    matchup_adj = get_matchup_adjustment(player, is_pitcher=False)
    details["opp_pitcher"] = matchup_adj["opp_pitcher"]
    details["opp_era"] = matchup_adj["opp_era"]
    details["matchup_adj"] = matchup_adj["total_adj"]
    details["venue"] = matchup_adj["venue"]

    from analytics.blended_stats import get_blend_info
    stats = get_blended_stats(player, is_pitcher=False)
    blend = get_blend_info(player, is_pitcher=False)
    details["blend"] = f"실제 {blend['actual_weight']:.0%} / Proj {blend['proj_weight']:.0%} ({blend['sample']})"

    weights = matchup_context or {}
    total_score = 0.0
    cat_scores = {}

    for cat in config.HITTING_CATEGORIES:
        val = get_stat_value(stats, cat)
        z = z_score(val, cat)
        w = weights.get(cat, 1.0)
        cat_score = z * w
        cat_scores[cat] = round(cat_score, 2)
        total_score += cat_score

    # 매치업 조정 적용
    total_score *= matchup_adj["total_adj"]

    details["score"] = round(total_score, 2)
    details["category_scores"] = cat_scores
    return details


def score_pitcher_zscore(player, matchup_context: dict = None) -> dict:
    """Z-score 기반 투수 점수를 계산한다.

    SP와 RP를 구분하여 관련 카테고리만 평가:
      - SP: OUTS, W, K, K/BB, ERA (SVHD 제외)
      - RP: K, SVHD, K/BB, ERA (W/OUTS 제외)
    """
    details = {
        "name": player.name,
        "position": player.position,
        "injury": getattr(player, "injuryStatus", "ACTIVE"),
        "proTeam": getattr(player, "proTeam", ""),
    }

    injury = getattr(player, "injuryStatus", "ACTIVE")
    if injury in ("OUT", "IL", "IL10", "IL60", "SUSPENSION",
                  "FIFTEEN_DAY_DL", "SIXTY_DAY_DL", "TEN_DAY_DL"):
        details["score"] = 0
        details["reason"] = f"부상/결장 ({injury})"
        details["category_scores"] = {}
        return details

    # 오늘 경기 유무 확인
    game_today = has_game_today(player)
    opponent = get_opponent_today(player)
    details["game_today"] = "O" if game_today else "X"
    details["opponent"] = opponent

    if not game_today:
        details["score"] = 0
        details["reason"] = "오늘 경기 없음"
        details["category_scores"] = {}
        return details

    # 매치업 조정 (구장 팩터, 투수는 상대 투수 조정 없음)
    matchup_adj = get_matchup_adjustment(player, is_pitcher=True)
    details["matchup_adj"] = matchup_adj["total_adj"]
    details["venue"] = matchup_adj["venue"]

    from analytics.blended_stats import get_blend_info
    stats = get_blended_stats(player, is_pitcher=True)
    blend = get_blend_info(player, is_pitcher=True)
    details["blend"] = f"실제 {blend['actual_weight']:.0%} / Proj {blend['proj_weight']:.0%} ({blend['sample']})"

    # SP vs RP 구분
    pos = player.position or ""
    eligible = player.eligibleSlots if hasattr(player, "eligibleSlots") else []
    is_sp = pos == "SP" or ("SP" in eligible and "RP" not in eligible)
    is_rp = pos == "RP" or ("RP" in eligible and "SP" not in eligible)

    if is_sp:
        # SP: 이닝, 승, 삼진, K/BB, ERA (SVHD 제외)
        relevant_cats = ["OUTS", "W", "K", "K/BB", "ERA"]
    elif is_rp:
        # RP: 삼진, SVHD, K/BB, ERA (W/OUTS는 기여도 낮음)
        relevant_cats = ["K", "SVHD", "K/BB", "ERA"]
    else:
        # SP/RP 겸업
        relevant_cats = config.PITCHING_CATEGORIES

    weights = matchup_context or {}
    total_score = 0.0
    cat_scores = {}

    for cat in relevant_cats:
        val = get_stat_value(stats, cat)
        z = z_score(val, cat)
        w = weights.get(cat, 1.0)
        cat_score = z * w
        cat_scores[cat] = round(cat_score, 2)
        total_score += cat_score

    # SP/RP 카테고리 수 차이 보정
    if len(relevant_cats) > 0:
        total_score = total_score / len(relevant_cats) * len(config.PITCHING_CATEGORIES)

    # 매치업 조정 적용
    total_score *= matchup_adj["total_adj"]

    details["score"] = round(total_score, 2)
    details["category_scores"] = cat_scores
    details["pitcher_type"] = "SP" if is_sp else ("RP" if is_rp else "SP/RP")
    return details


def is_norms_loaded() -> bool:
    """리그 통계가 로드되었는지 확인."""
    return _norms_loaded


def get_norms_summary() -> dict:
    """리그 통계 요약 (디버깅/UI용)."""
    summary = {}
    for cat, norm in _league_norms.items():
        summary[cat] = {
            "mean": round(norm["mean"], 3),
            "std": round(norm["std"], 3),
        }
    return summary
