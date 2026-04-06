"""ESPN Fantasy Baseball API 클라이언트."""

import pandas as pd
from espn_api.baseball import League

import config


def connect_league() -> League:
    """ESPN Fantasy 리그에 연결하여 League 객체를 반환한다."""
    kwargs = {
        "league_id": config.LEAGUE_ID,
        "year": config.YEAR,
    }
    if config.ESPN_S2 and config.SWID:
        kwargs["espn_s2"] = config.ESPN_S2
        kwargs["swid"] = config.SWID
    return League(**kwargs)


def get_my_team(league: League):
    """본인 팀 객체를 반환한다."""
    for team in league.teams:
        if team.team_name == config.MY_TEAM_NAME:
            return team
    # 이름으로 못 찾으면 첫 번째 팀 반환 (디버깅용)
    print(f"[경고] '{config.MY_TEAM_NAME}' 팀을 찾을 수 없습니다.")
    print("사용 가능한 팀 목록:")
    for t in league.teams:
        print(f"  - {t.team_name}")
    return None


def get_current_matchup(league: League, my_team):
    """현재 주간의 매치업(상대 팀)을 반환한다."""
    # scoreboard에서 현재 매치업 기간 찾기
    scoreboard = league.scoreboard()
    for matchup in scoreboard:
        if matchup.home_team == my_team:
            return matchup, matchup.away_team
        if matchup.away_team == my_team:
            return matchup, matchup.home_team
    return None, None


def get_roster_df(team) -> pd.DataFrame:
    """팀 로스터를 DataFrame으로 변환한다."""
    rows = []
    for player in team.roster:
        row = {
            "name": player.name,
            "position": player.position,
            "eligibleSlots": ", ".join(player.eligibleSlots) if hasattr(player, "eligibleSlots") else "",
            "injuryStatus": getattr(player, "injuryStatus", "ACTIVE"),
            "proTeam": getattr(player, "proTeam", ""),
        }
        # 시즌 스탯
        if hasattr(player, "stats") and player.stats:
            for period, stat_dict in player.stats.items():
                if isinstance(stat_dict, dict) and "avg" in str(period).lower() or "total" in str(stat_dict):
                    for key, val in stat_dict.get("stats", stat_dict).items():
                        row[f"stat_{key}"] = val
        rows.append(row)
    return pd.DataFrame(rows)


def get_free_agents(league: League, size: int = None, position: str = None) -> list:
    """FA 리스트를 반환한다."""
    size = size or config.FA_SIZE
    kwargs = {"size": size}
    if position:
        kwargs["position"] = position
    return league.free_agents(**kwargs)


def get_free_agents_df(league: League, size: int = None, position: str = None) -> pd.DataFrame:
    """FA 리스트를 DataFrame으로 변환한다."""
    fas = get_free_agents(league, size, position)
    rows = []
    for player in fas:
        row = {
            "name": player.name,
            "position": player.position,
            "proTeam": getattr(player, "proTeam", ""),
        }
        if hasattr(player, "stats") and player.stats:
            for period, stat_dict in player.stats.items():
                if isinstance(stat_dict, dict):
                    for key, val in stat_dict.get("stats", stat_dict).items():
                        row[f"stat_{key}"] = val
        rows.append(row)
    return pd.DataFrame(rows)


def get_standings(league: League) -> pd.DataFrame:
    """리그 순위를 DataFrame으로 반환한다."""
    rows = []
    for team in league.standings():
        rows.append({
            "team_name": team.team_name,
            "wins": team.wins,
            "losses": team.losses,
            "ties": team.ties,
            "points_for": getattr(team, "points_for", 0),
            "points_against": getattr(team, "points_against", 0),
        })
    return pd.DataFrame(rows)


def get_box_scores(league: League, matchup_period: int = None):
    """박스 스코어를 반환한다."""
    if matchup_period:
        return league.box_scores(matchup_period=matchup_period)
    return league.box_scores()


def extract_player_stats(player) -> dict:
    """선수 객체에서 주요 스탯을 추출한다."""
    stats = {}
    if not hasattr(player, "stats") or not player.stats:
        return stats

    for period_key, period_data in player.stats.items():
        if isinstance(period_data, dict):
            raw = period_data.get("stats", period_data)
            if isinstance(raw, dict):
                stats[period_key] = raw
    return stats


def print_league_info(league: League):
    """리그 기본 정보를 출력한다."""
    print(f"리그명: {league.settings.name if hasattr(league.settings, 'name') else 'N/A'}")
    print(f"시즌: {config.YEAR}")
    print(f"팀 수: {len(league.teams)}")
    print(f"\n팀 목록:")
    for team in league.teams:
        print(f"  [{team.team_id}] {team.team_name} ({team.wins}W-{team.losses}L)")
