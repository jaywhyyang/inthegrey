# -*- coding: utf-8 -*-
"""
KOBIS 회원통계 자동 수집 (로그인 → 요약/상세 직접 수집). 로컬(한국 IP)에서 30분마다 실행.
- 자격증명은 kobis_login.txt (gitignore, 3줄: 아이디 / 비번 / 인증번호)에서 읽음. 저장소엔 안 올라감.
- 요약(findCompanyStatXls.do) → member_snapshots.csv (실관람 추이)
- 상세(findCompanyStatDetail.do, rowspan 보정) → member_detail.json (극장/체인/회차)
"""
import os
import re
import json
import urllib.request
import urllib.parse
import http.cookiejar
import datetime

import member_ingest as MI

BASE = "https://www.kobis.or.kr"
DIR = os.path.dirname(os.path.abspath(__file__))
LOGIN_FILE = os.path.join(DIR, "kobis_login.txt")
MOVIE_CD = "20264056"  # 그린랜드 2: 마이그레이션


def _creds():
    if not os.path.exists(LOGIN_FILE):
        raise RuntimeError("kobis_login.txt 없음 (3줄: 아이디/비번/인증번호)")
    lines = [l.strip() for l in open(LOGIN_FILE, encoding="utf-8") if l.strip()]
    return lines[0], lines[1], lines[2]


def login():
    uid, pw, otp = _creds()
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")]
    op.open(BASE + "/kobis/business/comm/user/openLogin.do", timeout=30).read()
    q = urllib.parse.urlencode({"userId": uid, "userPw": pw, "aprvNo": otp})
    chk = op.open(urllib.request.Request(BASE + "/kobis/business/comm/user/findSmsNo.do?" + q,
                  headers={"Accept": "application/json+sua"}), timeout=30).read().decode("utf-8", "replace")
    if '"listSms":[' not in chk or '"useYn":"Y"' not in chk:
        raise RuntimeError("인증 실패(아이디/비번/인증번호 확인): " + chk[:200])
    op.open(urllib.request.Request(BASE + "/kobis/j_login?" + urllib.parse.urlencode({"j_username": uid, "j_password": pw}),
            data=b'{t:1}', headers={"Accept": "application/extJs+sua", "Content-Type": "application/extJs+sua"},
            method="POST"), timeout=30).read()
    return op


def _post(op, path, extra, date_str):
    g = op.open(BASE + "/kobis/business/mast/thea/findCompanyStat.do", timeout=30).read().decode("utf-8", "replace")
    tok = re.search(r'name="CSRFToken"[^>]*value="([^"]+)"', g)
    tok = tok.group(1) if tok else ""
    p = {"CSRFToken": tok, "loadEnd": "0", "sStartDt": date_str, "sEndDt": date_str,
         "showStartDt": date_str, "showEndDt": date_str, "sMovName": "", "sMovLang": "ko",
         "movieCd": "", "img_type": ""}
    p.update(extra)
    return op.open(urllib.request.Request(BASE + path, data=urllib.parse.urlencode(p).encode()),
                   timeout=30).read().decode("utf-8", "replace")


def _detail_cellrows(html):
    """웹 상세 HTML(극장/상영관/좌석 rowspan)에서 셀행 복원 → 22칸 정렬."""
    m = re.search(r"<tbody[^>]*>(.*?)</tbody>", html, re.S)
    body = m.group(1) if m else html
    out, carry = [], None
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
        cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", t)).strip()
                 for t in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if not cells:
            continue
        if len(cells) >= 22:
            carry = cells[:5]
            out.append(cells)
        elif carry and len(cells) >= 17:
            out.append(carry + cells)
    return out


def main():
    date_str = datetime.date.today().strftime("%Y-%m-%d")
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        op = login()
    except Exception as e:
        print("로그인 실패:", e)
        return 1

    # 요약
    try:
        s_html = _post(op, "/kobis/business/mast/thea/findCompanyStatXls.do", {}, date_str)
        summary = MI.parse_summary_html(s_html)
        if summary:
            summary["날짜"] = summary.get("날짜") or date_str
            MI.append_snapshot(summary, ts)
            print(f"요약 저장 {ts} | 관객 {summary['관객수']} | 누적 {summary['누적관객수']} | 무료 {summary['무료관객수']}")
        else:
            print("요약: 그린랜드2 행 없음")
    except Exception as e:
        print("요약 수집 실패:", e)

    # 상세: 엑셀(SpreadsheetML) 엔드포인트 → rowspan 없이 기존 파서로 집계
    try:
        d_xml = _post(op, "/kobis/business/mast/thea/findCompanyStatDetailXls.do", {"movieCd": MOVIE_CD}, date_str)
        cellrows = [[re.sub(r"<[^>]+>", "", c) for c in re.findall(r"<Data[^>]*>(.*?)</Data>", r, re.S)]
                    for r in re.findall(r"<Row[^>]*>(.*?)</Row>", d_xml, re.S)]
        detail = MI.aggregate_detail(cellrows)
        if detail.get("total") and len(detail.get("theaters", [])) >= 20:
            detail["updated"] = ts
            detail["date"] = date_str
            json.dump(detail, open(MI.DETAIL_JSON, "w", encoding="utf-8"), ensure_ascii=False)
            # 날짜별 이력 저장(날짜 선택용)
            MI.save_detail_history(detail, date_str)
            print(f"상세 저장 {date_str} | 총관객 {detail['total']:,} | 극장 {len(detail['theaters'])}")
        else:
            print(f"상세 스킵(정합성 미달): 총 {detail.get('total')} / 극장 {len(detail.get('theaters', []))}")
    except Exception as e:
        print("상세 수집 실패:", e)

    # 미래 날짜 선예매 추적(같은 로그인 세션 재사용)
    try:
        import member_future
        got = member_future.collect(op)
        print("미래날짜 선예매:", " · ".join(f"{d[5:]} {a:,}" for d, a in sorted(got.items())))
    except Exception as e:
        print("미래날짜 예매 건너뜀:", e)

    try:
        import schedule_ingest
        if schedule_ingest._find_file():
            schedule_ingest.main()
    except Exception as e:
        print("편성 반영 건너뜀:", e)
    try:
        import build_dashboard
        build_dashboard.generate()
        print("대시보드 갱신")
    except Exception as e:
        print("대시보드 건너뜀:", e)
    try:
        import kobis_greenland2
        kobis_greenland2.publish_to_github(ts)
    except Exception as e:
        print("publish 건너뜀:", e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
