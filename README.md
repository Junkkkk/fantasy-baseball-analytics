# ⚾ Fantasy Baseball Analytics

ESPN Fantasy Baseball H2H Categories 리그용 분석 대시보드.

## 사용법

### 1. 사이드바에서 정보 입력
- **League ID**: ESPN 리그 페이지 URL에서 `leagueId=` 뒤의 숫자
- **시즌 연도**: 2026
- **내 팀 이름**: ESPN에 표시되는 본인 팀 이름 (정확히 일치)

### 2. (비공개 리그면) 쿠키 입력
브라우저에서 ESPN Fantasy 로그인 후:
1. F12 (개발자 도구) → Application 탭
2. Cookies → `https://www.espn.com`
3. `espn_s2`와 `SWID` 값을 복사
4. 사이드바에 붙여넣기

### 3. "리그 연결" 클릭

## 기능

- **매치업 분석**: 카테고리별 승패 비교, 집중/포기 전략 추천
- **라인업 추천**: Z-score 기반 점수, 상대 선발투수/구장 팩터 반영
- **FA 추천**: 약점 카테고리 보강 + 오늘 등판 SP 교체 추천
- **트레이드 분석**: 카테고리별 영향 시뮬레이션
- **포지션 Depth 분석**: 보강 필요 포지션 자동 식별
