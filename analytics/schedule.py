"""MLB 경기 스케줄, 상대 선발투수, 구장 팩터 모듈."""

import requests
from datetime import datetime, timedelta

# ESPN proTeam 약칭 → MLB API 팀명 매핑
ESPN_TO_MLB = {
    "Ari": "Arizona Diamondbacks",
    "Atl": "Atlanta Braves",
    "Bal": "Baltimore Orioles",
    "Bos": "Boston Red Sox",
    "ChC": "Chicago Cubs",
    "CWS": "Chicago White Sox",
    "Cin": "Cincinnati Reds",
    "Cle": "Cleveland Guardians",
    "Col": "Colorado Rockies",
    "Det": "Detroit Tigers",
    "Hou": "Houston Astros",
    "KC": "Kansas City Royals",
    "LAA": "Los Angeles Angels",
    "LAD": "Los Angeles Dodgers",
    "Mia": "Miami Marlins",
    "Mil": "Milwaukee Brewers",
    "Min": "Minnesota Twins",
    "NYM": "New York Mets",
    "NYY": "New York Yankees",
    "Oak": "Athletics",
    "Phi": "Philadelphia Phillies",
    "Pit": "Pittsburgh Pirates",
    "SD": "San Diego Padres",
    "SF": "San Francisco Giants",
    "Sea": "Seattle Mariners",
    "StL": "St. Louis Cardinals",
    "TB": "Tampa Bay Rays",
    "Tex": "Texas Rangers",
    "Tor": "Toronto Blue Jays",
    "Wsh": "Washington Nationals",
}
MLB_TO_ESPN = {v: k for k, v in ESPN_TO_MLB.items()}

# 구장 팩터 (타자 기준, 1.0 = 중립)
# 1.0 이상 = 타자 유리, 1.0 이하 = 투수 유리
PARK_FACTORS = {
    "Coors Field": 1.30,           # 콜로라도 - 극단적 타자 천국
    "Fenway Park": 1.10,           # 보스턴
    "Globe Life Field": 1.08,      # 텍사스
    "Great American Ball Park": 1.12,  # 신시내티
    "Yankee Stadium": 1.10,        # 뉴욕 양키스
    "Citizens Bank Park": 1.05,    # 필라델피아
    "Wrigley Field": 1.05,         # 시카고 컵스
    "Nationals Park": 1.02,        # 워싱턴
    "Camden Yards": 1.03,          # 볼티모어
    "Target Field": 1.01,          # 미네소타
    "Chase Field": 1.02,           # 아리조나
    "Truist Park": 1.00,           # 애틀란타
    "Busch Stadium": 0.98,         # 세인트루이스
    "American Family Field": 0.98, # 밀워키
    "Angel Stadium": 0.97,         # LA 에인절스
    "Minute Maid Park": 1.02,      # 휴스턴
    "Rogers Centre": 1.00,         # 토론토
    "Tropicana Field": 0.93,       # 탬파베이
    "Comerica Park": 0.95,         # 디트로이트
    "T-Mobile Park": 0.94,         # 시애틀
    "Progressive Field": 0.97,     # 클리블랜드
    "Kauffman Stadium": 0.97,      # 캔자스시티
    "Citi Field": 0.95,            # 뉴욕 메츠
    "loanDepot park": 0.93,        # 마이애미
    "Dodger Stadium": 0.98,        # LA 다저스
    "Petco Park": 0.92,            # 샌디에이고
    "Oracle Park": 0.90,           # 샌프란시스코
    "PNC Park": 0.96,              # 피츠버그
    "Rate Field": 1.00,            # 시카고 화이트삭스
    "Oakland Coliseum": 0.90,      # 오클랜드
    "Sutter Health Park": 0.95,    # 새크라멘토 (A's 임시)
}

# 캐시
_today_teams: set[str] = set()
_schedule_loaded = False
_schedule_date: str = ""
_today_games: list[dict] = []
_probable_pitchers: dict[str, dict] = {}  # ESPN팀약칭 → {name, era, whip, id}
_game_venues: dict[str, str] = {}         # ESPN팀약칭 → 구장이름


def load_today_schedule():
    """오늘 MLB 경기 스케줄, probable pitcher, 구장 정보를 로드한다."""
    global _today_teams, _schedule_loaded, _schedule_date, _today_games
    global _probable_pitchers, _game_venues

    today = datetime.now().strftime("%Y-%m-%d")
    if _schedule_loaded and _schedule_date == today:
        return

    try:
        url = f"https://statsapi.mlb.com/api/v1/schedule?date={today}&sportId=1&hydrate=probablePitcher,venue"
        resp = requests.get(url, timeout=10)
        data = resp.json()

        _today_teams.clear()
        _today_games.clear()
        _probable_pitchers.clear()
        _game_venues.clear()

        if data.get("dates"):
            for game in data["dates"][0].get("games", []):
                away_info = game["teams"]["away"]
                home_info = game["teams"]["home"]
                away_name = away_info["team"]["name"]
                home_name = home_info["team"]["name"]
                venue_name = game.get("venue", {}).get("name", "")

                away_espn = MLB_TO_ESPN.get(away_name, "")
                home_espn = MLB_TO_ESPN.get(home_name, "")

                if away_espn:
                    _today_teams.add(away_espn)
                if home_espn:
                    _today_teams.add(home_espn)

                _today_games.append({
                    "away": away_espn or away_name,
                    "home": home_espn or home_name,
                    "venue": venue_name,
                })

                # 구장 정보 (원정팀, 홈팀 모두 같은 구장)
                if away_espn:
                    _game_venues[away_espn] = venue_name
                if home_espn:
                    _game_venues[home_espn] = venue_name

                # Probable pitcher (상대 팀 선발)
                away_pp = away_info.get("probablePitcher", {})
                home_pp = home_info.get("probablePitcher", {})

                # 홈팀 타자가 상대하는 건 원정 선발투수
                if away_pp and home_espn:
                    _probable_pitchers[home_espn] = {
                        "id": away_pp.get("id"),
                        "name": away_pp.get("fullName", "TBD"),
                    }
                # 원정팀 타자가 상대하는 건 홈 선발투수
                if home_pp and away_espn:
                    _probable_pitchers[away_espn] = {
                        "id": home_pp.get("id"),
                        "name": home_pp.get("fullName", "TBD"),
                    }

        # Probable pitcher 스탯 로드
        _load_pitcher_stats()

        _schedule_date = today
        _schedule_loaded = True

    except Exception as e:
        print(f"[경고] MLB 스케줄 로드 실패: {e}")
        _today_teams.update(ESPN_TO_MLB.keys())
        _schedule_loaded = True
        _schedule_date = today


def _load_pitcher_stats():
    """Probable pitcher들의 시즌 스탯을 MLB API에서 가져온다."""
    year = datetime.now().year
    for team_abbr, pp_info in _probable_pitchers.items():
        pid = pp_info.get("id")
        if not pid:
            continue
        try:
            url = (
                f"https://statsapi.mlb.com/api/v1/people/{pid}"
                f"?hydrate=stats(group=[pitching],type=[season],season={year})"
            )
            resp = requests.get(url, timeout=5)
            data = resp.json()
            person = data.get("people", [{}])[0]
            stats_list = person.get("stats", [])
            for s in stats_list:
                splits = s.get("splits", [])
                if splits:
                    stat = splits[0].get("stat", {})
                    pp_info["era"] = float(stat.get("era", 0) or 0)
                    pp_info["whip"] = float(stat.get("whip", 0) or 0)
                    pp_info["k"] = int(stat.get("strikeOuts", 0) or 0)
                    pp_info["ip"] = float(stat.get("inningsPitched", 0) or 0)
                    break
        except Exception:
            pass


def has_game_today(player) -> bool:
    """선수가 오늘 경기가 있는지 확인한다."""
    if not _schedule_loaded:
        load_today_schedule()
    return getattr(player, "proTeam", "") in _today_teams


def get_opponent_today(player) -> str:
    """선수의 오늘 상대 팀을 반환한다."""
    if not _schedule_loaded:
        load_today_schedule()
    pro_team = getattr(player, "proTeam", "")
    for game in _today_games:
        if game["away"] == pro_team:
            return game["home"]
        if game["home"] == pro_team:
            return game["away"]
    return ""


def get_opposing_pitcher(player) -> dict:
    """선수가 오늘 상대하는 선발투수 정보를 반환한다.

    Returns:
        {name, era, whip, k, ip} 또는 빈 dict
    """
    if not _schedule_loaded:
        load_today_schedule()
    pro_team = getattr(player, "proTeam", "")
    return _probable_pitchers.get(pro_team, {})


def get_park_factor(player) -> float:
    """오늘 경기 구장의 파크 팩터를 반환한다.

    Returns:
        파크팩터 (1.0 = 중립, >1.0 = 타자 유리, <1.0 = 투수 유리)
    """
    if not _schedule_loaded:
        load_today_schedule()
    pro_team = getattr(player, "proTeam", "")
    venue = _game_venues.get(pro_team, "")
    return PARK_FACTORS.get(venue, 1.0)


def get_matchup_adjustment(player, is_pitcher: bool = False) -> dict:
    """선수의 오늘 매치업 기반 점수 조정 정보를 반환한다.

    Returns:
        {
            "opp_pitcher": str,        # 상대 선발투수 이름
            "opp_era": float,          # 상대 선발투수 ERA
            "pitcher_adj": float,      # 상대 투수 기반 조정 배수 (1.0 = 중립)
            "park_factor": float,      # 구장 팩터
            "park_adj": float,         # 구장 기반 조정 배수
            "total_adj": float,        # 종합 조정 배수
            "venue": str,              # 구장 이름
        }
    """
    if not _schedule_loaded:
        load_today_schedule()

    pro_team = getattr(player, "proTeam", "")
    venue = _game_venues.get(pro_team, "")
    pf = PARK_FACTORS.get(venue, 1.0)

    # 구장 조정: 파크팩터에서 약간만 반영 (과도한 조정 방지)
    # 타자: pf 그대로, 투수: 역수
    if is_pitcher:
        park_adj = 1.0 + (1.0 - pf) * 0.5  # 투수에게 타자 천국은 불리
    else:
        park_adj = 1.0 + (pf - 1.0) * 0.5  # 타자에게 타자 천국은 유리

    # 상대 선발투수 조정 (타자 전용)
    pitcher_adj = 1.0
    opp_pp = _probable_pitchers.get(pro_team, {})
    opp_era = opp_pp.get("era", 0)
    opp_name = opp_pp.get("name", "TBD")

    if not is_pitcher and opp_era > 0:
        # ERA가 리그 평균(~3.5) 대비 높으면 타자에게 유리
        league_avg_era = 3.50
        era_diff = opp_era - league_avg_era
        # ERA 1.0 차이당 ±10% 조정 (최대 ±25%)
        pitcher_adj = 1.0 + min(max(era_diff * 0.10, -0.25), 0.25)

    total_adj = pitcher_adj * park_adj

    return {
        "opp_pitcher": opp_name,
        "opp_era": round(opp_era, 2),
        "pitcher_adj": round(pitcher_adj, 2),
        "park_factor": round(pf, 2),
        "park_adj": round(park_adj, 2),
        "total_adj": round(total_adj, 2),
        "venue": venue,
    }


def is_probable_starter_today(player) -> bool:
    """선수가 오늘 선발 등판 예정인지 확인 (MLB probable pitcher 기준)."""
    if not _schedule_loaded:
        load_today_schedule()

    player_name = player.name.lower().strip()
    # 내 팀 또는 상대 팀의 probable pitcher 명단에서 찾기
    for opponent_team, pp in _probable_pitchers.items():
        pp_name = (pp.get("name") or "").lower().strip()
        if pp_name and pp_name == player_name:
            return True
    return False


def get_all_probable_pitchers_today() -> list[dict]:
    """오늘 등판 예정인 모든 선발투수 명단."""
    if not _schedule_loaded:
        load_today_schedule()
    seen = set()
    result = []
    for opp_team, pp in _probable_pitchers.items():
        pid = pp.get("id")
        if pid and pid not in seen:
            seen.add(pid)
            result.append(pp)
    return result


def get_today_summary() -> dict:
    """오늘 스케줄 요약."""
    if not _schedule_loaded:
        load_today_schedule()
    return {
        "date": _schedule_date,
        "total_games": len(_today_games),
        "teams_playing": len(_today_teams),
        "teams_off": sorted(set(ESPN_TO_MLB.keys()) - _today_teams),
        "games": _today_games,
    }


def get_rotation_forecast(roster: list, days_ahead: int = 7) -> list[dict]:
    """내 팀 SP들의 다음 등판 예측.

    1) MLB API에서 향후 N일간 발표된 probable pitcher 확인
    2) 미발표 SP는 마지막 등판일 기준 5일 로테이션으로 추정

    Returns:
        [{name, proTeam, next_start, source("발표"/"추정"), opponent, days_until}, ...]
    """
    if not _schedule_loaded:
        load_today_schedule()

    # 내 팀 SP만 추출
    my_sps = []
    for p in roster:
        pos = p.position or ""
        eligible = p.eligibleSlots if hasattr(p, "eligibleSlots") else []
        if pos == "SP" or ("SP" in eligible and "RP" not in eligible):
            injury = getattr(p, "injuryStatus", "ACTIVE")
            if injury in ("OUT", "IL", "IL10", "IL60", "FIFTEEN_DAY_DL",
                          "SIXTY_DAY_DL", "TEN_DAY_DL"):
                continue
            my_sps.append(p)

    if not my_sps:
        return []

    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    end_date = (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    # 향후 N일간 probable pitcher 가져오기
    upcoming_probables = {}  # {pitcher_name_lower: [{date, opponent}, ...]}
    try:
        url = (
            f"https://statsapi.mlb.com/api/v1/schedule"
            f"?startDate={today_str}&endDate={end_date}"
            f"&sportId=1&hydrate=probablePitcher"
        )
        resp = requests.get(url, timeout=10)
        data = resp.json()

        for date_entry in data.get("dates", []):
            game_date = date_entry.get("date", "")
            for game in date_entry.get("games", []):
                away_info = game["teams"]["away"]
                home_info = game["teams"]["home"]
                away_name = away_info["team"]["name"]
                home_name = home_info["team"]["name"]
                away_espn = MLB_TO_ESPN.get(away_name, "")
                home_espn = MLB_TO_ESPN.get(home_name, "")

                # 원정 선발투수
                away_pp = away_info.get("probablePitcher", {})
                if away_pp:
                    pp_name = (away_pp.get("fullName") or "").lower().strip()
                    if pp_name:
                        if pp_name not in upcoming_probables:
                            upcoming_probables[pp_name] = []
                        upcoming_probables[pp_name].append({
                            "date": game_date,
                            "opponent": home_espn or home_name,
                            "team": away_espn,
                        })

                # 홈 선발투수
                home_pp = home_info.get("probablePitcher", {})
                if home_pp:
                    pp_name = (home_pp.get("fullName") or "").lower().strip()
                    if pp_name:
                        if pp_name not in upcoming_probables:
                            upcoming_probables[pp_name] = []
                        upcoming_probables[pp_name].append({
                            "date": game_date,
                            "opponent": away_espn or away_name,
                            "team": home_espn,
                        })
    except Exception as e:
        print(f"[경고] 향후 스케줄 로드 실패: {e}")

    # 각 SP별 다음 등판 찾기
    results = []
    for p in my_sps:
        player_name = p.name.lower().strip()
        pro_team = getattr(p, "proTeam", "")

        # 1) 발표된 probable pitcher에서 찾기
        if player_name in upcoming_probables:
            starts = upcoming_probables[player_name]
            # 오늘 이후 가장 빠른 등판
            future_starts = [s for s in starts if s["date"] >= today_str]
            if future_starts:
                future_starts.sort(key=lambda x: x["date"])
                next_s = future_starts[0]
                next_date = datetime.strptime(next_s["date"], "%Y-%m-%d")
                days_until = (next_date - today).days
                results.append({
                    "name": p.name,
                    "proTeam": pro_team,
                    "next_start": next_s["date"],
                    "opponent": next_s["opponent"],
                    "days_until": days_until,
                    "source": "발표",
                })
                continue

        # 2) 발표 안 됨 → 마지막 등판에서 5일 로테이션 추정
        last_start = _get_last_start_date(p, pro_team)
        if last_start:
            # 5일 로테이션: 마지막 등판 + 5일씩
            estimated = last_start + timedelta(days=5)
            while estimated.strftime("%Y-%m-%d") < today_str:
                estimated += timedelta(days=5)
            # 최대 days_ahead 이내
            if (estimated - today).days <= days_ahead:
                days_until = (estimated - today).days
                # 그날 팀 경기가 있는지 확인은 생략 (추정이므로)
                results.append({
                    "name": p.name,
                    "proTeam": pro_team,
                    "next_start": estimated.strftime("%Y-%m-%d"),
                    "opponent": "미정",
                    "days_until": days_until,
                    "source": "추정(5일)",
                })
                continue

        # 정보 없음
        results.append({
            "name": p.name,
            "proTeam": pro_team,
            "next_start": "미정",
            "opponent": "미정",
            "days_until": 99,
            "source": "정보없음",
        })

    results.sort(key=lambda x: x["days_until"])
    return results


def _get_last_start_date(player, pro_team: str):
    """MLB API에서 투수의 마지막 선발 등판일을 가져온다."""
    # ESPN player에서 MLB ID 추출 시도
    # player name으로 팀 로스터에서 찾기
    year = datetime.now().year
    team_mlb_name = ESPN_TO_MLB.get(pro_team, "")
    if not team_mlb_name:
        return None

    player_name_lower = player.name.lower().strip()

    try:
        # MLB API에서 팀 로스터 가져와서 선수 ID 찾기
        # 먼저 팀 ID 찾기
        teams_url = f"https://statsapi.mlb.com/api/v1/teams?sportId=1&season={year}"
        resp = requests.get(teams_url, timeout=5)
        teams_data = resp.json()
        team_id = None
        for t in teams_data.get("teams", []):
            if t["name"] == team_mlb_name:
                team_id = t["id"]
                break

        if not team_id:
            return None

        # 팀 로스터에서 선수 찾기
        roster_url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/roster?season={year}"
        resp = requests.get(roster_url, timeout=5)
        roster_data = resp.json()
        player_id = None
        for entry in roster_data.get("roster", []):
            person = entry.get("person", {})
            if (person.get("fullName") or "").lower().strip() == player_name_lower:
                player_id = person["id"]
                break

        if not player_id:
            return None

        # 게임 로그에서 마지막 선발 등판 찾기
        log_url = (
            f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats"
            f"?stats=gameLog&season={year}&group=pitching"
        )
        resp = requests.get(log_url, timeout=5)
        log_data = resp.json()

        for stat_group in log_data.get("stats", []):
            splits = stat_group.get("splits", [])
            # 최신순으로 정렬
            splits.sort(key=lambda x: x.get("date", ""), reverse=True)
            for split in splits:
                stat = split.get("stat", {})
                # 선발 등판: gamesStarted > 0
                if int(stat.get("gamesStarted", 0)) > 0:
                    date_str = split.get("date", "")
                    if date_str:
                        return datetime.strptime(date_str, "%Y-%m-%d")

    except Exception:
        pass

    return None


def is_loaded() -> bool:
    return _schedule_loaded
