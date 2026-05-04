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
# H2H Categories 설정 (리그: 13개 카테고리)
# ============================================================

# 타자 (7): H, HR, RBI, SB, OPS, GDP(↓), E(↓)
HITTING_CATEGORIES = ["H", "HR", "RBI", "SB", "OPS", "GDP", "E"]

# 투수 (6): OUTS, W, K, SVHD, K/BB, ERA(↓)
PITCHING_CATEGORIES = ["OUTS", "W", "K", "SVHD", "K/BB", "ERA"]

ALL_CATEGORIES = HITTING_CATEGORIES + PITCHING_CATEGORIES

# 낮을수록 좋은 카테고리
LOWER_IS_BETTER = {"ERA", "GDP", "E"}

# 비율/평균 스탯 (경기당 누적이 아닌 평균값)
RATIO_STATS = {"OPS", "ERA", "K/BB"}

RECENT_DAYS = [7, 14, 30]
FA_SIZE = 100

# ESPN statId -> 카테고리명 매핑 (13개 스코어링 카테고리)
ESPN_STAT_ID_MAP = {
    1: "H",       # Hits
    5: "HR",      # Home Runs
    18: "OPS",    # On-base Plus Slugging
    21: "RBI",    # Runs Batted In
    23: "SB",     # Stolen Bases
    26: "GDP",    # Grounded into Double Play (↓)
    72: "E",      # Errors (↓)
    34: "OUTS",   # Outs recorded (= IP * 3)
    47: "ERA",    # Earned Run Average (↓)
    48: "K",      # Strikeouts (pitching)
    53: "W",      # Wins
    82: "K/BB",   # Strikeout to Walk ratio
    83: "SVHD",   # Saves + Holds
}
