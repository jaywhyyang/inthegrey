# -*- coding: utf-8 -*-
"""
KOBIS 일별 박스오피스 + 좌석점유율 통합 수집기 (개봉 후 '그린랜드 2' 일자별 성적)

- 일별 박스오피스(findDailyBoxOfficeList): 관객수/매출/스크린수/상영횟수/전일대비/누적
- 좌석점유율(findDailySeatTicketList): 좌석수/좌석판매율/좌석점유율
  → 두 페이지를 영화명으로 합쳐 엑셀과 동일한 풍부한 일자별 데이터를 만든다.

매일 1회(전날 확정치) 실행 → greenland2_boxoffice.csv 에 하루 한 줄씩 적재.
이미 같은 날짜가 있으면 갱신(중복 방지).
"""
import os
import re
import csv
import sys
import datetime
import urllib.request
import urllib.parse
import http.cookiejar

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_CSV = os.path.join(BASE, "greenland2_boxoffice.csv")
COMP_CSV = os.path.join(BASE, "boxoffice_competitors.csv")  # 동시개봉작 경쟁력 리더보드용
MOVIE_KEYWORD = "그린랜드 2"

BOX_URL = "https://www.kobis.or.kr/kobis/business/stat/boxs/findDailyBoxOfficeList.do"
SEAT_URL = "https://www.kobis.or.kr/kobis/business/stat/boxs/findDailySeatTicketList.do"

HEADER = ["날짜", "순위", "영화명", "개봉일",
          "관객수", "관객수증감", "누적관객수",
          "매출액", "매출점유율", "매출액증감", "누적매출액",
          "스크린수", "상영횟수", "좌석수", "좌석판매율", "좌석점유율"]


def _clean(html_cell):
    t = re.sub(r"<[^>]+>", "", html_cell)
    t = t.replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", t).strip()


def _movie_name(raw):
    """박스오피스 영화명 끝 순위변동 표시 제거. 실제 형식은 '<등락폭>상승/하락'(예 '11상승'),
    '동일', '신규', 'New'. 제목 속 숫자(예 '토이 스토리 5')는 보존."""
    return re.sub(r"\s*(\d+(상승|하락)|동일|신규|New)\s*$", "", raw).strip()


def fetch_rows(url, date_str):
    """해당 URL을 GET해서 CSRF/쿠키 확보 후, 날짜 지정 POST → 결과 표의 행(셀 리스트들) 반환."""
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"),
                     ("Referer", url)]
    g = op.open(url, timeout=30).read().decode("utf-8", "replace")
    m = re.search(r'name="CSRFToken"[^>]*value="([^"]+)"', g)
    token = m.group(1) if m else ""
    data = urllib.parse.urlencode({
        "CSRFToken": token, "loadEnd": "0", "searchType": "",
        "sSearchFrom": date_str, "sSearchTo": date_str,     # 박스오피스 페이지 날짜
        "startDate": date_str, "endDate": date_str,          # 좌석 페이지 날짜(이름 다름)
        "sMultiMovieYn": "", "sRepNationCd": "", "sWideAreaCd": "",
        "sMovName": "", "sMovLang": "ko",
    }).encode()
    r = op.open(urllib.request.Request(url, data=data), timeout=30).read().decode("utf-8", "replace")
    for mb in re.finditer(r"<tbody[^>]*>(.*?)</tbody>", r, re.S):
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", mb.group(1), re.S)
        if len(rows) > 2:  # 결과 표
            out = []
            for row in rows:
                cells = [_clean(t) for t in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
                cells = [c for c in cells if c != ""]
                if cells:
                    out.append(cells)
            return out
    return []


def find_movie(rows, keyword):
    for c in rows:
        if len(c) >= 2 and keyword in c[1]:
            return c
    return None


def _build_rec(box, seat, date_str):
    rec = {h: "" for h in HEADER}
    rec["날짜"] = date_str
    # 박스오피스: [순위,영화명,개봉일,매출액,매출점유율,매출증감,누적매출액,관객수,관객증감,누적관객수,스크린수,상영횟수]
    if box and len(box) >= 12:
        rec.update({"순위": box[0], "영화명": _movie_name(box[1]), "개봉일": box[2],
                    "매출액": box[3], "매출점유율": box[4], "매출액증감": box[5],
                    "누적매출액": box[6], "관객수": box[7], "관객수증감": box[8],
                    "누적관객수": box[9], "스크린수": box[10], "상영횟수": box[11]})
    # 좌석: [순위,영화명,개봉일,좌석판매율,좌석점유율,좌석수,매출액,누적매출액,관객수,누적관객수]
    if seat and len(seat) >= 6:
        rec["영화명"] = rec["영화명"] or seat[1]
        rec["개봉일"] = rec["개봉일"] or seat[2]
        rec.update({"좌석판매율": seat[3], "좌석점유율": seat[4], "좌석수": seat[5]})
    return rec


def collect(date_str, keyword=MOVIE_KEYWORD):
    box = find_movie(fetch_rows(BOX_URL, date_str), keyword)
    seat = find_movie(fetch_rows(SEAT_URL, date_str), keyword)
    if not box and not seat:
        return None
    return _build_rec(box, seat, date_str)


def collect_all(date_str, top_n=25):
    """상위 top_n편 전부를 박스오피스+좌석 병합. 좌석 페이지 영화명이 비어 있어
    개봉일+관객수로 매칭(둘 다 같은 값이라 안정적)."""
    def mkey(opendt, aud):
        return (str(opendt).strip(), re.sub(r"[^\d]", "", str(aud)))
    box_rows = fetch_rows(BOX_URL, date_str)
    seat_rows = fetch_rows(SEAT_URL, date_str)
    # 좌석: [순위,영화명,개봉일,좌석판매율,좌석점유율,좌석수,매출,누적매출,관객수,누적관객]
    seat_by = {mkey(s[2], s[8]): s for s in seat_rows if len(s) >= 9}
    recs = []
    for c in box_rows[:top_n]:
        if len(c) >= 12:  # 박스: ...개봉일=c[2]...관객수=c[7]
            recs.append(_build_rec(c, seat_by.get(mkey(c[2], c[7])), date_str))
    return recs


def upsert(rec):
    rows = []
    if os.path.exists(OUT_CSV):
        with open(OUT_CSV, encoding="utf-8-sig", newline="") as f:
            rows = [r for r in csv.DictReader(f)]
    rows = [r for r in rows if r.get("날짜") != rec["날짜"]]  # 같은 날짜 제거(갱신)
    rows.append(rec)
    rows.sort(key=lambda r: r.get("날짜", ""))
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        w.writerows(rows)


def upsert_competitors(recs, date_str):
    rows = []
    if os.path.exists(COMP_CSV):
        with open(COMP_CSV, encoding="utf-8-sig", newline="") as f:
            rows = [r for r in csv.DictReader(f)]
    rows = [r for r in rows if r.get("날짜") != date_str]  # 같은 날짜 제거(갱신)
    rows.extend(recs)
    rows.sort(key=lambda r: (r.get("날짜", ""), r.get("영화명", "")))
    with open(COMP_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        w.writerows(rows)


def main():
    # 인자로 날짜(YYYY-MM-DD) 받으면 그 날, 없으면 어제
    if len(sys.argv) > 1:
        date_str = sys.argv[1]
    else:
        date_str = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        recs = collect_all(date_str)
    except Exception as e:
        print("ERROR:", e)
        return 1

    if not recs:
        print(f"{date_str}: 박스오피스 데이터 없음 (개봉 전/미집계일 수 있음)")
        return 0

    # 동시개봉작 전부 저장
    upsert_competitors(recs, date_str)
    print(f"동시개봉작 {len(recs)}편 저장: {COMP_CSV}")

    # 그린랜드2 단독 파일도 유지(기존 차트용)
    rec = next((r for r in recs if MOVIE_KEYWORD in r.get("영화명", "")), None)
    if not rec:
        print(f"{date_str}: '{MOVIE_KEYWORD}' 미집계 (개봉 전일 수 있음) — 경쟁작만 저장")
        rec = {"관객수": "-", "누적관객수": "-", "좌석수": "-", "스크린수": "-", "상영횟수": "-"}
    else:
        upsert(rec)
        print(f"OK {date_str} | 관객 {rec['관객수']} | 누적 {rec['누적관객수']} "
              f"| 좌석수 {rec['좌석수']} | 스크린 {rec['스크린수']} | 상영 {rec['상영횟수']}")
    print("저장:", OUT_CSV)

    # 대시보드 갱신 + GitHub push (실패해도 수집은 성공)
    try:
        import build_dashboard
        build_dashboard.generate()
    except Exception as e:
        print("대시보드 건너뜀:", e)
    try:
        import kobis_greenland2
        kobis_greenland2.publish_to_github(date_str)
    except Exception as e:
        print("publish 건너뜀:", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
