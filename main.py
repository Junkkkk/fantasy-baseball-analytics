"""Fantasy Baseball Analytics - CLI / 자동 리포트 진입점."""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from espn_client import (
    connect_league, get_my_team, get_current_matchup,
    get_free_agents, print_league_info,
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
from analytics.scoring import compute_league_norms
from analytics.schedule import load_today_schedule, get_today_summary
from report.excel import generate_report


def main():
    """메인 실행 함수."""
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    print("=" * 60)
    print(f"  ⚾ ESPN Fantasy Baseball Analytics")
    print(f"  📅 {today}")
    print("=" * 60)

    if config.LEAGUE_ID == 0:
        print("\n[오류] config.py에서 LEAGUE_ID를 설정해주세요.")
        sys.exit(1)

    # 리그 연결
    print("\n리그 연결 중...")
    league = connect_league()
    print_league_info(league)

    my_team = get_my_team(league)
    if not my_team:
        print("\n[오류] 팀을 찾을 수 없습니다.")
        sys.exit(1)
    print(f"\n내 팀: {my_team.team_name} ({my_team.wins}W-{my_team.losses}L)")

    # 리그 정규화 & 스케줄 로드
    print("리그 통계 계산 중...")
    compute_league_norms(league)
    load_today_schedule()

    sched = get_today_summary()
    print(f"오늘 {sched['total_games']}경기", end="")
    if sched["teams_off"]:
        print(f" | 쉬는 팀: {', '.join(sched['teams_off'])}")
    else:
        print(" (전 팀 경기)")

    # 매치업
    matchup, opponent = get_current_matchup(league, my_team)
    matchup_df = None
    strategy = None

    if matchup and opponent:
        print(f"\n이번 주 상대: {opponent.team_name}")
        print("\n" + "=" * 60)
        print("  📊 매치업 분석")
        print("=" * 60)

        try:
            box_scores = league.box_scores()
            for bs in box_scores:
                if bs.home_team == my_team or bs.away_team == my_team:
                    my_side = "home" if bs.home_team == my_team else "away"
                    opp_side = "away" if my_side == "home" else "home"
                    my_stats = extract_category_stats(bs, my_side)
                    opp_stats = extract_category_stats(bs, opp_side)

                    matchup_df = compare_categories(my_stats, opp_stats)
                    print(matchup_df.to_string(index=False))

                    progress = calculate_matchup_progress()
                    strategy = get_strategy_recommendations(matchup_df, matchup_progress=progress)
                    print("\n전략 추천:")
                    for rec in strategy:
                        icon = {"집중": "🔵", "수비": "🟢", "포기": "🔴", "요약": "📌", "관망": "⏳"}.get(rec["action"], "⚪")
                        print(f"  {icon} [{rec['action']}] {rec['category']}: {rec['reason']}")
                    break
        except Exception as e:
            print(f"매치업 분석 실패: {e}")

    # 라인업 추천
    print("\n" + "=" * 60)
    print("  ⚾ 라인업 추천")
    print("=" * 60)

    matchup_context = {}
    if strategy:
        for rec in strategy:
            if rec["action"] == "집중":
                matchup_context[rec["category"]] = 2.0
            elif rec["action"] == "포기":
                matchup_context[rec["category"]] = 0.3

    lineup_df = recommend_lineup(my_team.roster, matchup_context)
    print(lineup_df.to_string(index=False))

    injuries = get_injury_alerts(my_team.roster)
    if injuries:
        print("\n⚠️ 부상 알림:")
        for inj in injuries:
            print(f"  {inj['name']} ({inj['position']}) - {inj['injury_status']} → {inj['action']}")

    # 로스터 분석
    print("\n" + "=" * 60)
    print("  📋 로스터 포지션 분석")
    print("=" * 60)

    roster_analysis = analyze_roster_needs(my_team.roster)
    for n in roster_analysis["needs"]:
        icon = {"긴급": "🔴", "보강": "🟡", "여유": "🟢"}.get(n["urgency"], "⚪")
        print(f"  {icon} {n['position']}: depth {n['depth']} ({n['urgency']})")

    # FA 추천
    print("\n" + "=" * 60)
    print("  🔍 FA 픽업 추천")
    print("=" * 60)

    fa_df = None
    try:
        fa_list = get_free_agents(league)

        if matchup_df is not None:
            weak_cats = [w["category"] for w in identify_weak_categories(
                dict(zip(matchup_df["category"], matchup_df["my_stat"])),
                dict(zip(matchup_df["category"], matchup_df["opp_stat"])),
            )]
            if weak_cats:
                print(f"\n약점 카테고리: {', '.join(weak_cats)}")
                target_cats = weak_cats
            else:
                target_cats = config.ALL_CATEGORIES
        else:
            target_cats = config.ALL_CATEGORIES

        # ⚡ 데일리 추천
        print("\n⚡ 데일리 추천 — 오늘 바로 활용 가능한 선수")
        print("-" * 40)
        daily_df = rank_free_agents(fa_list, target_cats, daily_only=True)
        if not daily_df.empty:
            print(daily_df.to_string(index=False))
        else:
            print("오늘 추천할 FA가 없습니다.")

        # SP 교체 추천
        print("\n🔁 오늘 SP 교체 추천")
        swaps = recommend_pitcher_swaps(my_team.roster, fa_list)
        print("\n내 SP — 오늘 등판 없음 (교체 후보):")
        if not swaps["my_off_today"].empty:
            print(swaps["my_off_today"].to_string(index=False))
        else:
            print("  없음")
        print("\nFA SP — 오늘 등판 예정 (픽업 후보):")
        if not swaps["fa_starting_today"].empty:
            print(swaps["fa_starting_today"].to_string(index=False))
        else:
            print("  없음")

        # 📈 중장기 추천
        print("\n📈 중장기 추천 — 장기적으로 챙길 매물")
        print("-" * 40)
        fa_df = rank_free_agents(fa_list, target_cats, daily_only=False, roster=my_team.roster)
        if fa_df is not None and not fa_df.empty:
            print(fa_df.to_string(index=False))

        streamers = recommend_streaming_pitchers(fa_list)
        if not streamers.empty:
            print("\n🔥 스트리밍 투수 추천:")
            print(streamers.to_string(index=False))

        # 드롭 후보
        drops = recommend_drops(my_team.roster)
        if not drops.empty:
            print("\n📉 드롭 후보:")
            print(drops.to_string(index=False))

    except Exception as e:
        print(f"FA 분석 실패: {e}")

    # 엑셀 리포트 생성
    print("\n" + "=" * 60)
    print("  📄 엑셀 리포트 생성")
    print("=" * 60)

    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
    os.makedirs(output_dir, exist_ok=True)

    filepath = generate_report(
        matchup_df=matchup_df,
        lineup_df=lineup_df,
        fa_df=fa_df,
        strategy=strategy,
        output_dir=output_dir,
    )
    print(f"\n완료! 리포트: {filepath}")


if __name__ == "__main__":
    main()
