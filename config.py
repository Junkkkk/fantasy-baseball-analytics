"""ESPN Fantasy Baseball 리그 설정.

배포 환경에서는 사이드바에서 직접 입력합니다.
로컬 사용 시 아래 값을 본인 정보로 채워도 됩니다.
"""

# ESPN 리그 ID (기본값: 우리 리그)
LEAGUE_ID = 1902227688

# 시즌 연도
YEAR = 2026

# 본인 팀 이름
MY_TEAM_NAME = ""

# 비공개 리그 쿠키 (브라우저 개발자도구 → Application → Cookies → espn.com)
ESPN_S2 = ""
SWID = ""

# ============================================================
# H2H Categories 설정 (수정 불필요)
# ============================================================

HITTING_CATEGORIES = ["R", "HR", "RBI", "SB", "AVG"]
PITCHING_CATEGORIES = ["K", "W", "SV", "HD", "ERA", "WHIP"]
ALL_CATEGORIES = HITTING_CATEGORIES + PITCHING_CATEGORIES

LOWER_IS_BETTER = {"ERA", "WHIP"}
RATIO_STATS = {"AVG", "ERA", "WHIP"}
RECENT_DAYS = [7, 14, 30]
FA_SIZE = 100
