# -*- coding: utf-8 -*-
"""
KOBIS 실시간 예매율 - '인 더 그레이'(2026-09-02 개봉) 시간당 예매관객수 수집기
실행할 때마다 현재 스냅샷을 읽어 CSV에 한 줄씩 추가한다.
(KOBIS 실시간 페이지는 '조회 시점의 누적값'만 제공하므로,
 매 시간 실행해서 시계열로 쌓는 구조)
"""
import re
import csv
import sys
import os
import datetime
import urllib.request
import urllib.parse

URL = "https://www.kobis.or.kr/kobis/business/stat/boxs/findRealTicketList.do"
# 영화명에 이 문자열이 포함된 행을 찾는다
MOVIE_KEYWORD = "인 더 그레이"
# CSV 저장 위치 (스크립트와 같은 폴더)
_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_CSV = os.path.join(_DIR, "inthegrey_hourly.csv")
COMP_CSV = os.path.join(_DIR, "competitors_hourly.csv")  # 경쟁작 비교용 TOP-N 스냅샷
TOP_N = 25  # 매시간 상위 N편 수집(개봉일 필터 후 동일 개봉작 비교용으로 넉넉히)

COLUMNS = ["순위", "영화명", "개봉일", "예매율", "예매매출액", "누적매출액", "예매관객수", "누적관객수"]


def _slot(ts):
    """30분 슬롯 키('YYYY-MM-DD HH:0'/':3'). 같은 30분대 재실행은 교체(한 슬롯 1줄)."""
    mm = ts[14:16]
    return ts[:14] + ("0" if mm.isdigit() and int(mm) < 30 else "3")


def fetch_html():
    data = urllib.parse.urlencode({
        "loadEnd": "0",
        "searchType": "real",
        "sNationType": "",
        "sWideareaCd": "",
        "sMmType": "",
    }).encode("utf-8")
    req = urllib.request.Request(URL, data=data, method="POST", headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": URL,
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


def parse_movie(html, keyword):
    m = re.search(r"<tbody>(.*?)</tbody>", html, re.S)
    if not m:
        return None
    body = m.group(1)
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
        if keyword not in row:
            continue
        tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", t)).strip() for t in tds]
        cells = [c for c in cells if c != ""]
        if len(cells) >= 8:
            return cells[:8]
    return None


def main():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        html = fetch_html()
        cells = parse_movie(html, MOVIE_KEYWORD)
    except Exception as e:
        print("ERROR:", e)
        return 1

    if not cells:
        print(now, "- 영화를 찾지 못했습니다 (상영/예매 데이터 없음일 수 있음)")
        # 빈 행도 기록해 두면 추적에 도움됨
        cells = ["", "", "", "", "", "", "", ""]

    row = [now] + cells
    header = ["수집시각"] + COLUMNS

    # 같은 30분 슬롯에 이미 행이 있으면 교체 → 슬롯당 한 줄(수동 재실행 오염 방지)
    slot_key = _slot(now)
    existing = []
    if os.path.exists(OUT_CSV):
        with open(OUT_CSV, encoding="utf-8-sig", newline="") as f:
            rd = list(csv.reader(f))
        existing = [r for r in rd[1:] if r and _slot(r[0]) != slot_key]
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(existing)
        w.writerow(row)

    print("OK:", now, "| 예매율:", cells[3], "| 예매관객수:", cells[6], "| 누적관객수:", cells[7])
    print("저장:", OUT_CSV)

    # 경쟁작 TOP-N 스냅샷 같이 저장 (실패해도 본 수집은 성공)
    try:
        save_competitors(html, now)
    except Exception as e:
        print("경쟁작 수집 건너뜀:", e)

    # (회원통계는 member_auto.py 30분 작업이 전담 — 여기선 호출 안 함)

    # 배급 시간표(편성) 있으면 오늘 날짜 시트 반영
    try:
        import schedule_ingest
        if schedule_ingest._find_file():
            schedule_ingest.main()
    except Exception as e:
        print("편성 반영 건너뜀:", e)

    # 대시보드 HTML 갱신 (실패해도 수집 자체는 성공으로 둠)
    try:
        import build_ig as build_dashboard
        out = build_dashboard.generate()
        print("대시보드:", out)
    except Exception as e:
        print("대시보드 생성 건너뜀:", e)

    # GitHub로 자동 publish (원격 'origin'이 연결돼 있을 때만)
    try:
        publish_to_github(now)
    except Exception as e:
        print("publish 건너뜀:", e)

    return 0


def save_competitors(html, now):
    """실시간 표 상위 TOP_N편을 competitors_hourly.csv 에 한 줄씩 추가."""
    m = re.search(r"<tbody>(.*?)</tbody>", html, re.S)
    if not m:
        return
    header = ["수집시각", "순위", "영화명", "개봉일", "예매율", "예매관객수", "누적관객수"]
    newrows = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(1), re.S):
        tds = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", t)).strip()
               for t in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        tds = [t for t in tds if t != ""]
        if len(tds) >= 8:
            newrows.append([now, tds[0], tds[1], tds[2], tds[3], tds[6], tds[7]])
        if len(newrows) >= TOP_N:
            break

    # 같은 30분 슬롯 행은 교체 → 슬롯당 TOP-N 한 세트만 유지
    slot_key = _slot(now)
    existing = []
    if os.path.exists(COMP_CSV):
        with open(COMP_CSV, encoding="utf-8-sig", newline="") as f:
            rd = list(csv.reader(f))
        existing = [r for r in rd[1:] if r and _slot(r[0]) != slot_key]
    with open(COMP_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(existing)
        w.writerows(newrows)
    print(f"경쟁작 {len(newrows)}편 저장(시간당 갱신):", COMP_CSV)


def publish_to_github(now):
    # 루프가 수집기를 여러 개 돌린 뒤 한 번만 푸시하고 싶을 때(NO_PUBLISH=1) 개별 푸시 생략
    if os.environ.get("NO_PUBLISH") == "1":
        print("publish 생략: NO_PUBLISH(루프가 일괄 푸시)")
        return
    # GitHub Actions(클라우드)에서는 워크플로가 커밋/푸시를 담당하므로 여기선 생략
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print("publish 생략: CI(워크플로가 커밋/푸시)")
        return
    import subprocess
    repo = os.path.dirname(os.path.abspath(__file__))

    def git(*args, check=True):
        return subprocess.run(["git", "-C", repo, *args],
                              capture_output=True, text=True, encoding="utf-8")

    # 원격이 없으면 아무 것도 하지 않음
    remotes = git("remote").stdout.split()
    if "origin" not in remotes:
        print("publish 건너뜀: GitHub 원격(origin) 미연결")
        return

    for fn in ("index.html", "inthegrey_hourly.csv", "competitors_hourly.csv",
               "inthegrey_boxoffice.csv", "boxoffice_competitors.csv",
               "member_snapshots.csv", "member_detail.json", "schedule.json",
               "schedule_history.json", "member_detail_history.json",
               "future_advance_log.json", "schedule_capacity_log.json",
               "ai_comment.json"):
        if os.path.exists(os.path.join(repo, fn)):
            git("add", fn)
    # 변경사항 없으면 커밋 스킵
    diff = subprocess.run(["git", "-C", repo, "diff", "--cached", "--quiet"])
    if diff.returncode != 0:
        git("commit", "-m", f"data update {now}")
    push = git("push", "origin", "main")
    if push.returncode == 0:
        print("publish 완료: GitHub push OK")
    else:
        print("publish 실패:", (push.stderr or "").strip()[:200])


if __name__ == "__main__":
    sys.exit(main())
