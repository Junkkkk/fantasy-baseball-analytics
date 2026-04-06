#!/bin/bash
# Fantasy Baseball 일일 자동 분석 스크립트

PROJECT_DIR="/Users/junyoung/Desktop/claude_ai/fantasy_baseball"
LOG_DIR="$PROJECT_DIR/logs"
REPORT_DIR="$PROJECT_DIR/reports"

# 디렉토리 생성
mkdir -p "$LOG_DIR" "$REPORT_DIR"

# 날짜
DATE=$(date +%Y%m%d_%H%M%S)

# 로그 파일
LOG_FILE="$LOG_DIR/run_$DATE.log"

echo "[$DATE] Fantasy Baseball 분석 시작" >> "$LOG_FILE"

# venv 활성화 후 실행
cd "$PROJECT_DIR"
source venv/bin/activate
python3 main.py >> "$LOG_FILE" 2>&1

# 리포트는 main.py가 reports/ 폴더에 직접 생성

echo "[$DATE] 완료" >> "$LOG_FILE"

# 30일 이상 된 로그 정리
find "$LOG_DIR" -name "*.log" -mtime +30 -delete 2>/dev/null
