"""Fantasy Baseball Analytics - Streamlit 대시보드."""

import sys
import os
import io
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import pandas as pd

import config

# 로컬 개인 설정이 있으면 자동 로드 (gitignore 처리됨)
try:
    import config_local
    config.LEAGUE_ID = config_local.LEAGUE_ID
    config.YEAR = config_local.YEAR
    config.MY_TEAM_NAME = config_local.MY_TEAM_NAME
    config.ESPN_S2 = config_local.ESPN_S2
    config.SWID = config_local.SWID
except ImportError:
    pass

from espn_client import (
    connect_league, get_my_team, get_current_matchup,
    get_free_agents, get_standings,
)
from analytics.matchup import (
    extract_category_stats, compare_categories, get_strategy_recommendations,
    calculate_matchup_progress,
)
from analytics.lineup import recommend_lineup, get_injury_alerts
from analytics.free_agents import (
    identify_weak_categories, rank_free_agents,
    recommend_drops, recommend_streaming_pitchers,
    analyze_roster_needs, recommend_pitcher_swaps,
)
from analytics.trade import analyze_trade, compare_player_value
from analytics.blended_stats import get_season_blend_summary
from analytics.scoring import compute_league_norms, get_norms_summary, is_norms_loaded
from analytics.schedule import load_today_schedule, get_today_summary
from report.excel import generate_report


# ============================================================
# 스타일 헬퍼 함수
# ============================================================
def _highlight_result(row):
    """매치업 결과에 따른 행 색상."""
    result = row.get("result", "")
    if result == "WIN":
        return ["background-color: #c6efce"] * len(row)
    elif result == "LOSE":
        return ["background-color: #ffc7ce"] * len(row)
    elif result == "TIE":
        return ["background-color: #ffeb9c"] * len(row)
    return [""] * len(row)


def _highlight_recommendation(row):
    """라인업 추천에 따른 행 색상."""
    rec = row.get("recommendation", "")
    if rec == "선발":
        return ["background-color: #c6efce"] * len(row)
    elif rec == "벤치":
        return ["background-color: #d9d9d9"] * len(row)
    return [""] * len(row)


def _highlight_trade(row):
    """트레이드 영향에 따른 행 색상."""
    verdict = row.get("verdict", "")
    if verdict == "향상":
        return ["background-color: #c6efce"] * len(row)
    elif verdict == "하락":
        return ["background-color: #ffc7ce"] * len(row)
    return [""] * len(row)


# ============================================================
# 페이지 설정
# ============================================================
st.set_page_config(
    page_title="Fantasy Baseball Analytics",
    page_icon="⚾",
    layout="wide",
)

st.title("⚾ Fantasy Baseball Analytics")
st.caption(f"📅 {datetime.now().strftime('%Y년 %m월 %d일 (%a)')}")


# ============================================================
# 사이드바: 설정
# ============================================================
with st.sidebar:
    st.header("리그 설정")

    league_id = st.number_input("League ID", value=config.LEAGUE_ID, min_value=1)
    year = st.number_input("시즌 연도", value=config.YEAR, min_value=2020, max_value=2030)
    team_name = st.text_input("내 팀 이름", value=config.MY_TEAM_NAME)

    st.divider()
    st.subheader("비공개 리그 (선택)")
    espn_s2 = st.text_input("ESPN_S2 쿠키", value=config.ESPN_S2, type="password")
    swid = st.text_input("SWID 쿠키", value=config.SWID, type="password")

    connect_btn = st.button("🔗 리그 연결", type="primary", use_container_width=True)


# ============================================================
# 세션 상태 초기화
# ============================================================
if "league" not in st.session_state:
    st.session_state.league = None
    st.session_state.my_team = None
    st.session_state.opponent = None
    st.session_state.matchup = None


# ============================================================
# 리그 연결
# ============================================================
if connect_btn:
    if league_id == 0:
        st.error("League ID를 입력해주세요.")
    else:
        with st.spinner("리그 연결 중..."):
            try:
                # config 업데이트
                config.LEAGUE_ID = league_id
                config.YEAR = year
                config.MY_TEAM_NAME = team_name
                config.ESPN_S2 = espn_s2
                config.SWID = swid

                league = connect_league()
                st.session_state.league = league

                my_team = get_my_team(league)
                st.session_state.my_team = my_team

                if my_team:
                    matchup, opponent = get_current_matchup(league, my_team)
                    st.session_state.matchup = matchup
                    st.session_state.opponent = opponent

                    # 리그 정규화 통계 & 스케줄 로드
                    compute_league_norms(league)
                    load_today_schedule()

                    st.success(f"연결 완료! {my_team.team_name}")
                else:
                    st.warning("팀을 찾을 수 없습니다. 팀 이름을 확인해주세요.")
                    # 사용 가능한 팀 표시
                    st.info("사용 가능한 팀: " + ", ".join([t.team_name for t in league.teams]))
            except Exception as e:
                st.error(f"연결 실패: {e}")


# ============================================================
# 블렌딩 정보 (사이드바)
# ============================================================
with st.sidebar:
    st.divider()
    st.subheader("📊 스탯 블렌딩")
    blend_summary = get_season_blend_summary()
    st.caption(f"시즌 진행: {blend_summary['season_progress']}%")
    st.progress(blend_summary["season_progress"] / 100)
    st.info(blend_summary["recommendation"])


# ============================================================
# 메인 콘텐츠 (연결된 경우)
# ============================================================
league = st.session_state.league
my_team = st.session_state.my_team

if not league or not my_team:
    st.info("👈 사이드바에서 리그 정보를 입력하고 연결하세요.")
    st.stop()

# 탭 구성
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 매치업 분석", "⚾ 라인업 추천", "🔍 FA 추천", "🔄 트레이드 분석", "📋 리그 순위"
])


# ============================================================
# 탭 1: 매치업 분석
# ============================================================
with tab1:
    opponent = st.session_state.opponent
    matchup = st.session_state.matchup

    if opponent:
        st.subheader(f"🆚 {my_team.team_name} vs {opponent.team_name}")

        try:
            box_scores = league.box_scores()
            for bs in box_scores:
                if bs.home_team == my_team or bs.away_team == my_team:
                    my_side = "home" if bs.home_team == my_team else "away"
                    opp_side = "away" if my_side == "home" else "home"
                    my_stats = extract_category_stats(bs, my_side)
                    opp_stats = extract_category_stats(bs, opp_side)

                    comparison = compare_categories(my_stats, opp_stats)

                    # 승패 요약
                    wins = len(comparison[comparison["result"] == "WIN"])
                    losses = len(comparison[comparison["result"] == "LOSE"])
                    ties = len(comparison[comparison["result"] == "TIE"])

                    col1, col2, col3 = st.columns(3)
                    col1.metric("승", wins)
                    col2.metric("패", losses)
                    col3.metric("무", ties)

                    # 카테고리별 비교 테이블
                    st.dataframe(
                        comparison.style.apply(_highlight_result, axis=1),
                        use_container_width=True,
                        hide_index=True,
                    )

                    # 전략 추천
                    st.subheader("🎯 전략 추천")
                    progress = calculate_matchup_progress()
                    strategy = get_strategy_recommendations(comparison, matchup_progress=progress)
                    for rec in strategy:
                        icon = {"집중": "🔵", "수비": "🟢", "포기": "🔴", "요약": "📌", "관망": "⏳"}.get(rec["action"], "⚪")
                        st.markdown(f"{icon} **[{rec['action']}] {rec['category']}**: {rec['reason']}")

                    # 엑셀 다운로드 (매치업)
                    st.session_state["matchup_df"] = comparison
                    st.session_state["strategy"] = strategy
                    break
        except Exception as e:
            st.warning(f"매치업 데이터를 불러올 수 없습니다: {e}")
    else:
        st.info("현재 매치업 정보가 없습니다.")


# ============================================================
# 탭 2: 라인업 추천
# ============================================================
with tab2:
    st.subheader("⚾ 오늘의 최적 라인업")

    blend_summary = get_season_blend_summary()
    st.caption(f"💡 스탯 블렌딩: {blend_summary['recommendation']}")

    # 오늘 경기 정보
    try:
        sched = get_today_summary()
        if sched["teams_off"]:
            st.warning(f"⚠️ 오늘 경기 없는 팀: {', '.join(sched['teams_off'])}")
        else:
            st.caption(f"오늘 {sched['total_games']}경기 (전 팀 경기)")
    except Exception:
        pass

    # 매치업 컨텍스트 반영
    matchup_context = {}
    if "strategy" in st.session_state:
        for rec in st.session_state["strategy"]:
            if rec["action"] == "집중":
                matchup_context[rec["category"]] = 2.0
            elif rec["action"] == "포기":
                matchup_context[rec["category"]] = 0.3

    lineup_df = recommend_lineup(my_team.roster, matchup_context)
    st.session_state["lineup_df"] = lineup_df

    # 타자 / 투수 분리 표시
    hitters = lineup_df[lineup_df["type"] == "타자"]
    pitchers = lineup_df[lineup_df["type"] == "투수"]

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 타자")
        st.dataframe(
            hitters.style.apply(_highlight_recommendation, axis=1),
            use_container_width=True,
            hide_index=True,
        )

    with col2:
        st.markdown("### 투수")
        st.dataframe(
            pitchers.style.apply(_highlight_recommendation, axis=1),
            use_container_width=True,
            hide_index=True,
        )

    # 부상 알림
    injuries = get_injury_alerts(my_team.roster)
    if injuries:
        st.subheader("⚠️ 부상 알림")
        for inj in injuries:
            st.warning(f"**{inj['name']}** ({inj['position']}) - {inj['injury_status']} → {inj['action']}")


# ============================================================
# 탭 3: FA 추천
# ============================================================
with tab3:
    st.subheader("🔍 FA 픽업 추천")

    # 로스터 현황 분석
    roster_analysis = analyze_roster_needs(my_team.roster)
    needs = roster_analysis["needs"]

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("#### 포지션 Depth")
        depth_rows = []
        for n in needs:
            icon = {"긴급": "🔴", "보강": "🟡", "여유": "🟢"}.get(n["urgency"], "⚪")
            depth_rows.append({
                "포지션": n["position"],
                "보유": n["depth"],
                "상태": f"{icon} {n['urgency']}",
            })
        if depth_rows:
            st.dataframe(pd.DataFrame(depth_rows), use_container_width=True, hide_index=True)

    with col_b:
        st.markdown("#### 벤치 & IL")
        for b in roster_analysis["bench"]:
            st.caption(f"벤치: **{b['name']}** ({b['position']})")
        for il in roster_analysis["il"]:
            st.caption(f"IL: **{il['name']}** ({il['position']})")

    st.divider()

    try:
        with st.spinner("FA 리스트 로딩 중..."):
            fa_list = get_free_agents(league)

        # 약점 카테고리 기반 or 전체 카테고리
        if "matchup_df" in st.session_state:
            mdf = st.session_state["matchup_df"]
            my_stat_dict = dict(zip(mdf["category"], mdf["my_stat"]))
            opp_stat_dict = dict(zip(mdf["category"], mdf["opp_stat"]))
            weak = identify_weak_categories(my_stat_dict, opp_stat_dict)
            weak_cats = [w["category"] for w in weak]

            if weak_cats:
                st.info(f"약점 카테고리: **{', '.join(weak_cats)}**")
                target = weak_cats
            else:
                st.success("모든 카테고리에서 앞서고 있습니다!")
                target = config.ALL_CATEGORIES
        else:
            target = config.ALL_CATEGORIES

        # 타겟 카테고리 선택
        selected_cats = st.multiselect(
            "보강할 카테고리 선택",
            config.ALL_CATEGORIES,
            default=target[:5],
        )

        # ============================================================
        # ⚡ 데일리 추천 (오늘 바로 활용 가능)
        # ============================================================
        st.subheader("⚡ 데일리 추천 — 오늘 바로 활용 가능한 선수")
        st.caption("오늘 경기가 있는 선수만 추천합니다. SP는 오늘 선발 등판 예정인 경우만 포함됩니다.")

        if selected_cats:
            daily_df = rank_free_agents(fa_list, selected_cats, daily_only=True)
            if not daily_df.empty:
                st.dataframe(daily_df, use_container_width=True, hide_index=True)
            else:
                st.info("오늘 추천할 FA가 없습니다.")

        # 오늘 SP 교체 추천 (전체 목록 + 시즌 기록)
        st.markdown("#### 🔁 오늘 SP 교체 추천")
        swaps = recommend_pitcher_swaps(my_team.roster, fa_list)
        swap_col1, swap_col2 = st.columns(2)
        with swap_col1:
            st.markdown("**내 SP — 오늘 등판 없음** (교체 후보)")
            if not swaps["my_off_today"].empty:
                st.dataframe(swaps["my_off_today"], use_container_width=True, hide_index=True)
            else:
                st.caption("오늘 등판 안 하는 내 SP가 없습니다.")
        with swap_col2:
            st.markdown("**FA SP — 오늘 등판 예정** (픽업 후보)")
            if not swaps["fa_starting_today"].empty:
                st.dataframe(swaps["fa_starting_today"], use_container_width=True, hide_index=True)
            else:
                st.caption("오늘 등판 예정인 FA SP가 없습니다.")

        st.divider()

        # ============================================================
        # 📈 중장기 추천 (좋은 매물 선점)
        # ============================================================
        st.subheader("📈 중장기 추천 — 장기적으로 챙길 매물")
        st.caption("경기 유무와 관계없이 실력 기준으로 추천합니다.")

        if selected_cats:
            fa_df = rank_free_agents(fa_list, selected_cats, daily_only=False)
            st.session_state["fa_df"] = fa_df
            if not fa_df.empty:
                st.dataframe(fa_df, use_container_width=True, hide_index=True)
            else:
                st.info("추천할 FA가 없습니다.")

        # 스트리밍 투수
        st.markdown("#### 🔥 스트리밍 투수 추천")
        streamers = recommend_streaming_pitchers(fa_list)
        if not streamers.empty:
            st.dataframe(streamers, use_container_width=True, hide_index=True)

        st.divider()

        # 드롭 후보
        st.subheader("📉 드롭 후보")
        drops = recommend_drops(my_team.roster)
        if not drops.empty:
            st.dataframe(drops, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"FA 데이터 로딩 실패: {e}")


# ============================================================
# 탭 4: 트레이드 분석
# ============================================================
with tab4:
    st.subheader("🔄 트레이드 분석")

    roster_names = [p.name for p in my_team.roster]

    giving = st.multiselect("보내는 선수 (내 팀)", roster_names)

    # 다른 팀의 선수 목록
    other_teams = [t for t in league.teams if t != my_team]
    selected_team = st.selectbox("상대 팀", [t.team_name for t in other_teams])

    if selected_team:
        target_team = next(t for t in other_teams if t.team_name == selected_team)
        target_names = [p.name for p in target_team.roster]
        receiving_names = st.multiselect("받는 선수 (상대 팀)", target_names)

        if giving and receiving_names and st.button("📊 분석하기"):
            receiving_players = [p for p in target_team.roster if p.name in receiving_names]

            result = analyze_trade(
                my_team.roster,
                giving,
                receiving_players,
                league.teams,
            )

            # 결과 표시
            st.markdown(f"### {result['overall']}")

            if result["upgrades"]:
                st.success(f"향상되는 카테고리: **{', '.join(result['upgrades'])}**")
            if result["downgrades"]:
                st.error(f"하락하는 카테고리: **{', '.join(result['downgrades'])}**")

            st.dataframe(
                result["impact_df"].style.apply(_highlight_trade, axis=1),
                use_container_width=True,
                hide_index=True,
            )


# ============================================================
# 탭 5: 리그 순위
# ============================================================
with tab5:
    st.subheader("📋 리그 순위")
    try:
        standings = get_standings(league)
        st.dataframe(standings, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"순위 데이터 로딩 실패: {e}")


# ============================================================
# 엑셀 다운로드 버튼 (사이드바)
# ============================================================
with st.sidebar:
    st.divider()
    st.subheader("📄 리포트 다운로드")

    if st.button("엑셀 리포트 생성", use_container_width=True):
        filepath = generate_report(
            matchup_df=st.session_state.get("matchup_df"),
            lineup_df=st.session_state.get("lineup_df"),
            fa_df=st.session_state.get("fa_df"),
            strategy=st.session_state.get("strategy"),
            output_dir=os.path.dirname(os.path.abspath(__file__)),
        )
        with open(filepath, "rb") as f:
            st.download_button(
                "📥 다운로드",
                data=f,
                file_name=os.path.basename(filepath),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        st.success("리포트 생성 완료!")
