"""MLB Stats API 연동 모듈.

wRC+, 타자 vs 투수 상대전적 등 고급 스탯을 제공한다.
"""

import requests

# 선수 이름 → MLB player ID 캐시
_mlb_id_cache: dict[str, int] = {}
# MLB ID → wRC+ 캐시
_wrc_cache: dict[int, int] = {}
# (batter_id, pitcher_id) → 상대전적 캐시
_matchup_cache: dict[tuple, dict] = {}

MLB_API = "https://statsapi.mlb.com/api/v1"
TIMEOUT = 8


def get_mlb_id(player_name: str) -> int | None:
    """선수 이름으로 MLB player ID를 반환한다."""
    if player_name in _mlb_id_cache:
        return _mlb_id_cache[player_name]

    try:
        r = requests.get(
            f"{MLB_API}/people/search",
            params={"names": player_name, "season": 2026},
            timeout=TIMEOUT,
        )
        people = r.json().get("people", [])
        if people:
            mlb_id = people[0]["id"]
            _mlb_id_cache[player_name] = mlb_id
            return mlb_id
    except Exception:
        pass

    _mlb_id_cache[player_name] = None
    return None


def get_wrc_plus(player_name: str, season: int = 2026) -> int | None:
    """선수의 wRC+를 반환한다. (리그 평균 = 100)"""
    mlb_id = get_mlb_id(player_name)
    if not mlb_id:
        return None

    if mlb_id in _wrc_cache:
        return _wrc_cache[mlb_id]

    try:
        r = requests.get(
            f"{MLB_API}/people/{mlb_id}/stats",
            params={"stats": "sabermetrics", "season": season, "group": "hitting"},
            timeout=TIMEOUT,
        )
        splits = r.json().get("stats", [{}])[0].get("splits", [])
        if splits:
            wrc = splits[0]["stat"].get("wRcPlus")
            if wrc is not None:
                val = int(round(float(wrc)))
                _wrc_cache[mlb_id] = val
                return val
    except Exception:
        pass

    _wrc_cache[mlb_id] = None
    return None


def get_batter_vs_pitcher(batter_name: str, pitcher_name: str) -> dict | None:
    """타자 vs 투수 통산 상대전적을 반환한다.

    Returns:
        {
            "pa": 타석수,
            "ab": 타수,
            "avg": 타율,
            "hr": 홈런,
            "ops": OPS,
            "k": 삼진,
            "bb": 볼넷,
            "display": "3-12 .250 1HR" 형태 문자열,
        }
        또는 None (데이터 없음)
    """
    batter_id = get_mlb_id(batter_name)
    pitcher_id = get_mlb_id(pitcher_name)

    if not batter_id or not pitcher_id:
        return None

    cache_key = (batter_id, pitcher_id)
    if cache_key in _matchup_cache:
        return _matchup_cache[cache_key]

    try:
        r = requests.get(
            f"{MLB_API}/people/{batter_id}/stats",
            params={
                "stats": "vsPlayer",
                "group": "hitting",
                "opposingPlayerId": pitcher_id,
            },
            timeout=TIMEOUT,
        )
        splits = r.json().get("stats", [{}])[0].get("splits", [])
        if splits:
            s = splits[0]["stat"]
            pa = int(s.get("plateAppearances", 0))
            ab = int(s.get("atBats", 0))
            hits = int(s.get("hits", 0))
            hr = int(s.get("homeRuns", 0))
            k = int(s.get("strikeOuts", 0))
            bb = int(s.get("baseOnBalls", 0))
            avg = s.get("avg", ".---")
            ops = s.get("ops", ".---")

            # 표시 문자열: "2-8 .250 1HR" (타석 5 미만이면 표본 부족 표시)
            if pa < 5:
                display = f"{hits}-{ab} ({pa}PA) ⚠️소표본"
            else:
                hr_str = f" {hr}HR" if hr > 0 else ""
                display = f"{hits}-{ab} {avg}{hr_str}"

            result = {
                "pa": pa,
                "ab": ab,
                "hits": hits,
                "avg": avg,
                "hr": hr,
                "k": k,
                "bb": bb,
                "ops": ops,
                "display": display,
            }
            _matchup_cache[cache_key] = result
            return result
    except Exception:
        pass

    _matchup_cache[cache_key] = None
    return None


def clear_cache():
    """캐시를 초기화한다 (테스트/재로딩용)."""
    _mlb_id_cache.clear()
    _wrc_cache.clear()
    _matchup_cache.clear()
