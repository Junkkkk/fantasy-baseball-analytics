"""FA 픽업 추천 모듈."""

import pandas as pd

import config
from analytics.matchup import STAT_KEY_MAP, get_stat_value
from analytics.lineup import classify_players, _get_best_stats, PITCHER_POSITIONS
from analytics.blended_stats import get_blended_stats
from analytics.schedule import has_game_today, is_probable_starter_today, get_opponent_today


def analyze_roster_needs(roster: list) -> dict:
    """현재 로스터의 포지션 현황과 보강 필요 포지션을 분석한다.

    Returns:
        {
            "filled_slots": {슬롯명: [선수명, ...]},
            "bench": [선수명, ...],
            "il": [선수명, ...],
            "needs": [필요 포지션 리스트],
            "depth": {포지션: 선수 수},  # 포지션별 depth
        }
    """
    filled = {}
    bench = []
    il_list = []
    depth = {}

    for player in roster:
        slot = getattr(player, "lineupSlot", "BE")
        pos = player.position or ""
        eligible = player.eligibleSlots if hasattr(player, "eligibleSlots") else []

        # 현재 슬롯별 배치
        if slot == "BE":
            bench.append({"name": player.name, "position": pos, "eligible": eligible})
        elif slot == "IL":
            il_list.append({"name": player.name, "position": pos})
        else:
            if slot not in filled:
                filled[slot] = []
            filled[slot].append({"name": player.name, "position": pos})

        # 포지션별 depth 계산 (벤치 포함, IL 제외)
        if slot != "IL":
            for e in eligible:
                if e not in ("BE", "IL", "UTIL", "IF", "DH", "1B/3B", "2B/SS"):
                    depth[e] = depth.get(e, 0) + 1
            # LF/CF/RF → OF도 카운트
            if any(e in eligible for e in ("LF", "CF", "RF", "OF")):
                depth["OF"] = depth.get("OF", 0) + 1
            if "P" in eligible or "SP" in eligible:
                depth["SP"] = depth.get("SP", 0) + 1
            if "P" in eligible or "RP" in eligible:
                depth["RP"] = depth.get("RP", 0) + 1

    # 중복 제거 (OF는 별도로 세므로 LF/CF/RF 제거)
    for k in ("LF", "CF", "RF"):
        depth.pop(k, None)
    # P는 SP/RP에 통합
    depth.pop("P", None)

    # 보강 필요 포지션 (depth 1 이하)
    important_positions = ["C", "1B", "2B", "3B", "SS", "OF", "SP", "RP"]
    needs = []
    for pos in important_positions:
        d = depth.get(pos, 0)
        if d <= 1:
            needs.append({"position": pos, "depth": d, "urgency": "긴급" if d == 0 else "보강"})
        elif d == 2:
            needs.append({"position": pos, "depth": d, "urgency": "여유"})

    return {
        "filled_slots": filled,
        "bench": bench,
        "il": il_list,
        "needs": needs,
        "depth": depth,
    }


def identify_weak_categories(my_stats: dict, opp_stats: dict) -> list[dict]:
    """상대 대비 약한 카테고리를 식별한다."""
    weaknesses = []
    for cat in config.ALL_CATEGORIES:
        my_val = my_stats.get(cat, 0)
        opp_val = opp_stats.get(cat, 0)

        if cat in config.LOWER_IS_BETTER:
            gap = my_val - opp_val
            is_losing = my_val > opp_val
        else:
            gap = opp_val - my_val
            is_losing = my_val < opp_val

        if is_losing:
            weaknesses.append({
                "category": cat,
                "my_val": round(my_val, 3),
                "opp_val": round(opp_val, 3),
                "gap": round(abs(gap), 3),
                "priority": "HIGH" if abs(gap) < _close_threshold(cat) else "LOW",
            })

    weaknesses.sort(key=lambda x: (0 if x["priority"] == "HIGH" else 1, x["gap"]))
    return weaknesses


def rank_free_agents(fa_list: list, target_categories: list[str], top_n: int = 10,
                     daily_only: bool = False) -> pd.DataFrame:
    """타겟 카테고리 기준으로 FA를 랭킹한다.

    Args:
        daily_only: True이면 오늘 경기 있는 선수만, SP는 오늘 선발 등판만 추천
    """
    rows = []
    for player in fa_list:
        # 데일리 필터: 경기 없으면 제외, SP는 선발 등판 아니면 제외
        if daily_only:
            if not has_game_today(player):
                continue
            if _is_sp(player) and not is_probable_starter_today(player):
                continue

        is_pitcher = _is_pitcher(player)
        stats = get_blended_stats(player, is_pitcher=is_pitcher)
        if not stats:
            continue

        score = 0.0
        cat_values = {}
        for cat in target_categories:
            val = get_stat_value(stats, cat)
            cat_values[cat] = val
            if cat in config.LOWER_IS_BETTER:
                ip_key = STAT_KEY_MAP.get("IP", "OUTS")
                ip = stats.get(ip_key, 0) or 0
                if ip > 0:
                    score += (1.0 / max(val, 0.01)) * 10
            else:
                score += val

        if score > 0:
            eligible = player.eligibleSlots if hasattr(player, "eligibleSlots") else []
            pos_list = [e for e in eligible if e not in ("BE", "IL", "UTIL", "IF", "DH")]
            row = {
                "name": player.name,
                "position": player.position,
                "eligible": ", ".join(pos_list),
                "proTeam": getattr(player, "proTeam", ""),
                "score": round(score, 2),
            }
            if daily_only:
                row["상대팀"] = get_opponent_today(player)
            for cat in target_categories:
                row[cat] = round(cat_values.get(cat, 0), 3)
            rows.append(row)

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("score", ascending=False).head(top_n).reset_index(drop=True)
    return df


def recommend_drops(roster: list, top_n: int = 3) -> pd.DataFrame:
    """드롭 후보를 추천한다."""
    hitters, pitchers = classify_players(roster)
    rows = []

    for player in hitters + pitchers:
        is_pitcher = player in pitchers
        stats = get_blended_stats(player, is_pitcher=is_pitcher)
        if not stats:
            rows.append({
                "name": player.name,
                "position": player.position,
                "total_score": 0,
                "reason": "스탯 데이터 없음",
            })
            continue

        total_score = 0.0
        categories = config.PITCHING_CATEGORIES if is_pitcher else config.HITTING_CATEGORIES

        for cat in categories:
            val = get_stat_value(stats, cat)
            if cat in config.LOWER_IS_BETTER:
                total_score += (1.0 / max(val, 0.01)) * 10
            else:
                total_score += val

        injury = getattr(player, "injuryStatus", "ACTIVE")
        if injury in ("IL", "IL10", "IL60", "FIFTEEN_DAY_DL", "SIXTY_DAY_DL", "TEN_DAY_DL"):
            total_score *= 0.5

        rows.append({
            "name": player.name,
            "position": player.position,
            "total_score": round(total_score, 2),
            "injury": injury,
            "reason": "부상 중" if injury not in ("ACTIVE", "NORMAL", None) else "",
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("total_score", ascending=True).head(top_n).reset_index(drop=True)
    return df


def recommend_streaming_pitchers(fa_list: list, top_n: int = 5) -> pd.DataFrame:
    """스트리밍 투수 추천."""
    rows = []
    for player in fa_list:
        pos = player.position if hasattr(player, "position") else ""
        eligible = player.eligibleSlots if hasattr(player, "eligibleSlots") else []

        if pos != "SP" and "SP" not in eligible:
            continue

        stats = get_blended_stats(player, is_pitcher=True)
        if not stats:
            continue

        outs = stats.get("OUTS", 0) or 0
        ip = outs / 3.0 if outs > 0 else 0
        if ip < 10:
            continue

        k = get_stat_value(stats, "K")
        era = get_stat_value(stats, "ERA")
        whip = get_stat_value(stats, "WHIP")
        w = get_stat_value(stats, "W")

        score = k * 0.5 + w * 3 + (1 / max(era, 0.01)) * 20 + (1 / max(whip, 0.01)) * 15

        rows.append({
            "name": player.name,
            "position": player.position,
            "proTeam": getattr(player, "proTeam", ""),
            "IP": round(ip, 1),
            "K": int(k),
            "W": int(w),
            "ERA": round(era, 2),
            "WHIP": round(whip, 2),
            "score": round(score, 2),
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("score", ascending=False).head(top_n).reset_index(drop=True)
    return df


def recommend_pitcher_swaps(my_roster: list, fa_list: list) -> dict:
    """오늘 등판 안 하는 내 SP & 오늘 등판하는 FA SP 전체 목록 + 시즌 기록.

    Returns:
        {
            "my_off_today": DataFrame (내 SP 중 오늘 등판 없는 선수 + 시즌 기록),
            "fa_starting_today": DataFrame (FA SP 중 오늘 등판 예정 + 시즌 기록),
        }
    """
    from analytics.scoring import score_pitcher_zscore

    # 내 팀에서 SP만 필터
    my_pitchers = []
    for p in my_roster:
        pos = p.position or ""
        eligible = p.eligibleSlots if hasattr(p, "eligibleSlots") else []
        if pos == "SP" or ("SP" in eligible and "RP" not in eligible):
            my_pitchers.append(p)

    # 내 투수 중 오늘 등판 안 하는 선수
    my_off_rows = []
    for p in my_pitchers:
        injury = getattr(p, "injuryStatus", "ACTIVE")
        if injury in ("OUT", "IL", "IL10", "IL60", "FIFTEEN_DAY_DL", "SIXTY_DAY_DL", "TEN_DAY_DL"):
            continue
        if not is_probable_starter_today(p):
            stats = get_blended_stats(p, is_pitcher=True)
            outs = (stats or {}).get("OUTS", 0) or 0
            ip = outs / 3.0 if outs > 0 else 0
            score = score_pitcher_zscore(p).get("score", 0)
            my_off_rows.append({
                "name": p.name,
                "proTeam": getattr(p, "proTeam", ""),
                "IP": round(ip, 1),
                "K": int(get_stat_value(stats or {}, "K")),
                "W": int(get_stat_value(stats or {}, "W")),
                "ERA": round(get_stat_value(stats or {}, "ERA"), 2),
                "WHIP": round(get_stat_value(stats or {}, "WHIP"), 2),
                "score": round(score, 2),
            })

    # FA 중 오늘 등판하는 SP 전체
    fa_rows = []
    for p in fa_list:
        pos = p.position or ""
        eligible = p.eligibleSlots if hasattr(p, "eligibleSlots") else []
        if pos != "SP" and "SP" not in eligible:
            continue
        if is_probable_starter_today(p):
            stats = get_blended_stats(p, is_pitcher=True)
            outs = (stats or {}).get("OUTS", 0) or 0
            ip = outs / 3.0 if outs > 0 else 0
            score = score_pitcher_zscore(p).get("score", 0)
            fa_rows.append({
                "name": p.name,
                "proTeam": getattr(p, "proTeam", ""),
                "상대팀": get_opponent_today(p),
                "IP": round(ip, 1),
                "K": int(get_stat_value(stats or {}, "K")),
                "W": int(get_stat_value(stats or {}, "W")),
                "ERA": round(get_stat_value(stats or {}, "ERA"), 2),
                "WHIP": round(get_stat_value(stats or {}, "WHIP"), 2),
                "score": round(score, 2),
            })

    my_off_df = pd.DataFrame(my_off_rows)
    fa_starting_df = pd.DataFrame(fa_rows)

    if not my_off_df.empty:
        my_off_df = my_off_df.sort_values("score", ascending=True).reset_index(drop=True)
    if not fa_starting_df.empty:
        fa_starting_df = fa_starting_df.sort_values("score", ascending=False).reset_index(drop=True)

    return {"my_off_today": my_off_df, "fa_starting_today": fa_starting_df}


def _is_pitcher(player) -> bool:
    """선수가 투수인지 판별."""
    pos = player.position if hasattr(player, "position") else ""
    eligible = player.eligibleSlots if hasattr(player, "eligibleSlots") else []
    return pos in PITCHER_POSITIONS or any(s in PITCHER_POSITIONS for s in eligible)


def _is_sp(player) -> bool:
    """선수가 선발투수(SP)인지 판별."""
    pos = player.position if hasattr(player, "position") else ""
    eligible = player.eligibleSlots if hasattr(player, "eligibleSlots") else []
    return pos == "SP" or ("SP" in eligible and "RP" not in eligible)


def _close_threshold(category: str) -> float:
    """역전 가능 판단 임계값."""
    thresholds = {
        "R": 8, "HR": 3, "RBI": 8, "SB": 3, "AVG": 0.015,
        "K": 15, "W": 2, "SV": 2, "HD": 2, "ERA": 0.75, "WHIP": 0.08,
    }
    return thresholds.get(category, 5)
