# -*- coding: utf-8 -*-
"""
KOBIS 회원용 통계 엑셀(.xls) 2종을 파싱해서 대시보드용 데이터로 적재.
- 다운로드 폴더에서 최신 파일 자동 탐색:
    * KOBIS_회원용통계보기_*.xls        → 우리 영화 일별 요약(오늘 관객수 등)
    * 회원용통계(영화사별)상세_*.xls     → 극장·상영관·회차별 상세
- member_snapshots.csv 에 요약 스냅샷(파일 시각 기준) 적재 → '오늘 실관람' 추이
- member_detail.json 에 극장별/지역별/회차별 집계 저장 → 히트맵/랭킹
"""
import os
import re
import csv
import json
import glob
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")
SNAP_CSV = os.path.join(BASE, "member_snapshots.csv")
DETAIL_JSON = os.path.join(BASE, "member_detail.json")
MOVIE_KEYWORD = "그린랜드 2"

DETAIL_HISTORY = os.path.join(BASE, "member_detail_history.json")
SNAP_HEADER = ["수집시각", "날짜", "관객수", "누적관객수", "무료관객수",
               "스크린수", "상영횟수", "매출액", "누적매출액"]


def save_detail_history(detail, date_str):
    """날짜별 상세(체인/극장) 이력 저장 → 대시보드 날짜 선택용."""
    hist = {}
    if os.path.exists(DETAIL_HISTORY):
        try:
            hist = json.load(open(DETAIL_HISTORY, encoding="utf-8"))
        except Exception:
            hist = {}
    hist[date_str] = {"chains": detail.get("chains"), "theaters": detail.get("theaters"),
                      "theater_slots": detail.get("theater_slots"),
                      "regions": detail.get("regions"), "slots": detail.get("slots"),
                      "total": detail.get("total"), "updated": detail.get("updated")}
    json.dump(hist, open(DETAIL_HISTORY, "w", encoding="utf-8"), ensure_ascii=False)


def _latest(pattern):
    files = glob.glob(os.path.join(DOWNLOADS, pattern))
    return max(files, key=os.path.getmtime) if files else None


def _num(s):
    s = re.sub(r"[^\d\-]", "", str(s))
    return int(s) if s not in ("", "-") else None


def parse_summary(path):
    return parse_summary_html(open(path, "rb").read().decode("utf-8", "replace"))


def parse_summary_html(html):
    """회원용통계보기 HTML에서 그린랜드2 행 파싱 (엑셀/웹 공통)."""
    date = ""
    m = re.search(r"조회일\s*:\s*(\d{4}-\d{2}-\d{2})", html)
    if m:
        date = m.group(1)
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        tds = [re.sub(r"<[^>]+>", "", c).strip()
               for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if tds and MOVIE_KEYWORD in tds[0]:
            # [영화명, 스크린수, 상영횟수, 매출액, 누적매출액, 관객수, 누적관객수, 무료관객수]
            return {
                "날짜": date,
                "스크린수": _num(tds[1]), "상영횟수": _num(tds[2]),
                "매출액": _num(tds[3]), "누적매출액": _num(tds[4]),
                "관객수": _num(tds[5]), "누적관객수": _num(tds[6]),
                "무료관객수": _num(tds[7]) if len(tds) > 7 else None,
            }
    return None


def parse_detail(path):
    """영화사별 상세(SpreadsheetML 엑셀) → 셀행 추출 후 집계."""
    xml = open(path, "rb").read().decode("utf-8", "replace")
    cellrows = [[re.sub(r"<[^>]+>", "", c) for c in re.findall(r"<Data[^>]*>(.*?)</Data>", r, re.S)]
                for r in re.findall(r"<Row[^>]*>(.*?)</Row>", xml, re.S)]
    return aggregate_detail(cellrows)


def aggregate_detail(cellrows):
    """상세 셀행(list of cell-lists) → 극장/지역/체인/회차 집계."""
    by_theater, by_region, by_screen = {}, {}, {}
    by_slot = [0] * 7  # 1회~7회 관객 합
    by_theater_slot = {}  # 극장 → [1회~7회 관객] (지점×시간대 크로스; 과거엔 미보존이라 오늘부터 적재)
    total = 0
    for d in cellrows:
        if len(d) < 22 or not re.match(r"^\d{4}", str(d[0])):  # 20260701 / 2026-07-01 둘다
            continue
        region, theater, screen, seats = d[1], d[2], d[3], _num(d[4])
        aud_total = _num(d[7]) or 0           # 전체 관객수
        total += aud_total
        by_theater[theater] = by_theater.get(theater, 0) + aud_total
        by_region[region] = by_region.get(region, 0) + aud_total
        # 상영관 좌석수(대표값)와 관객 누적
        key = f"{theater} | {screen}"
        s = by_screen.setdefault(key, {"관객": 0, "좌석": seats or 0, "region": region})
        s["관객"] += aud_total
        # 회차별 관객: col9,11,13,15,17,19,21 = 1~7회 관객수
        tslot = by_theater_slot.setdefault(theater, [0] * 7)
        for i, col in enumerate(range(9, 22, 2)):
            v = _num(d[col]) or 0
            by_slot[i] += v
            tslot[i] += v            # 지점별 회차 관객 크로스 보존
    # 체인별 집계 (상영관수/좌석수/관객) — 상영관 단위로 중복 없이
    def chain_of(name):
        if "CGV" in name:
            return "CGV"
        if "메가박스" in name:
            return "메가박스"
        if "롯데" in name:
            return "롯데시네마"
        return "기타"
    by_chain = {}
    for key, s in by_screen.items():
        ch = chain_of(key.split(" | ")[0])
        c = by_chain.setdefault(ch, {"screens": 0, "seats": 0, "aud": 0})
        c["screens"] += 1
        c["seats"] += s["좌석"]
        c["aud"] += s["관객"]
    chains = sorted(
        ([k, v["screens"], v["seats"], v["aud"]] for k, v in by_chain.items()),
        key=lambda x: x[2], reverse=True)

    # 지역별 좌석수(상영관 단위 중복없이) → 좌석점유율 계산용
    region_seats = {}
    for s in by_screen.values():
        region_seats[s["region"]] = region_seats.get(s["region"], 0) + s["좌석"]
    # 극장별 상영관수(관객 랭킹표에 함께 표시)
    scr_per_theater = {}
    for key in by_screen:
        th = key.split(" | ")[0]
        scr_per_theater[th] = scr_per_theater.get(th, 0) + 1
    top_theaters = [[name, aud, scr_per_theater.get(name, 0)]
                    for name, aud in sorted(by_theater.items(), key=lambda x: x[1], reverse=True)[:50]]
    # 지점×시간대 크로스: 상위 극장에 한해 [1회~7회] 관객 (히트맵용)
    theater_slots = {name: by_theater_slot.get(name, [0] * 7) for name, _, _ in top_theaters}
    # regions: [지역, 관객, 좌석, 좌석점유율%]
    regions = sorted(
        ([r, by_region[r], region_seats.get(r, 0),
          round(by_region[r] / region_seats[r] * 100, 1) if region_seats.get(r) else 0]
         for r in by_region),
        key=lambda x: x[1], reverse=True)
    return {
        "total": total,
        "theaters": top_theaters,
        "theater_slots": theater_slots,
        "regions": regions,
        "chains": chains,
        "slots": by_slot,
        "screen_count": len(by_screen),
    }


def append_snapshot(summary, ts):
    rec = {"수집시각": ts}
    rec.update({k: summary.get(k) for k in SNAP_HEADER if k != "수집시각"})
    slot_key = ts[:13]  # 시각(시) 단위 upsert
    rows = []
    if os.path.exists(SNAP_CSV):
        with open(SNAP_CSV, encoding="utf-8-sig", newline="") as f:
            rows = [r for r in csv.DictReader(f) if r.get("수집시각", "")[:13] != slot_key]
    rows.append(rec)
    rows.sort(key=lambda r: r.get("수집시각", ""))
    with open(SNAP_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SNAP_HEADER)
        w.writeheader()
        w.writerows(rows)


def main():
    sf = _latest("KOBIS_회원용통계보기_*.xls")
    df = _latest("회원용통계(영화사별)상세_*.xls")
    if not sf:
        print("회원용통계보기 파일을 Downloads에서 못 찾음")
        return 1
    ts = datetime.datetime.fromtimestamp(os.path.getmtime(sf)).strftime("%Y-%m-%d %H:%M:%S")
    summary = parse_summary(sf)
    if not summary:
        print("그린랜드2 요약 행 없음")
        return 1
    if not summary.get("날짜"):
        fm = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(sf))
        summary["날짜"] = fm.group(1) if fm else ts[:10]
    append_snapshot(summary, ts)
    print(f"요약 스냅샷 저장 {ts} | 관객 {summary['관객수']} | 누적 {summary['누적관객수']} | 무료 {summary['무료관객수']}")

    if df:
        detail = parse_detail(df)
        detail["updated"] = ts
        with open(DETAIL_JSON, "w", encoding="utf-8") as f:
            json.dump(detail, f, ensure_ascii=False)
        print(f"상세 저장 | 총관객 {detail['total']:,} | 극장 {len(detail['theaters'])} | 상영관 {detail['screen_count']} | 회차합 {detail['slots']}")

    try:
        import build_dashboard
        build_dashboard.generate()
        print("대시보드 갱신")
    except Exception as e:
        print("대시보드 건너뜀:", e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
