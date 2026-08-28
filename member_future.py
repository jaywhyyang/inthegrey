# -*- coding: utf-8 -*-
"""
미래 날짜(오늘 이후) 선예매 추적 수집기.
KOBIS 회원통계는 날짜를 지정하면 그 날짜 상영분의 예매관객수를 준다
(미래 날짜 = 아직 적립 중인 선예매). 이걸 매일 기록하면
'며칠에 걸쳐 예매가 쌓이는 곡선' = 주말 수요 선행지표가 된다.

future_advance_log.json 구조:
  { "2026-07-04": { "2026-07-02": {"aud": 1229, "ts": "..."} , ... }, ... }
  (대상일 → 수집일(asof) → 그 시점까지의 선예매 관객수. 수집일당 최신값 1개)
"""
import os
import json
import datetime

import member_auto as MA
import member_ingest as MI

DIR = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(DIR, "future_advance_log.json")
DAYS_AHEAD = 5  # 오늘 포함 향후 며칠


def collect(op=None, today=None):
    op = op or MA.login()
    today = today or datetime.date.today()
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    asof = today.strftime("%Y-%m-%d")
    log = {}
    if os.path.exists(LOG):
        try:
            log = json.load(open(LOG, encoding="utf-8"))
        except Exception:
            log = {}
    got = {}
    for i in range(DAYS_AHEAD):
        d = (today + datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        try:
            html = MA._post(op, "/kobis/business/mast/thea/findCompanyStatXls.do", {}, d)
            s = MI.parse_summary_html(html)
            aud = None
            if s:
                v = str(s.get("관객수", "")).replace(",", "").strip()
                aud = int(v) if v.isdigit() else None
            if aud is not None:
                log.setdefault(d, {})[asof] = {"aud": aud, "ts": ts}
                got[d] = aud
        except Exception as e:
            print(f"  {d} 실패: {str(e)[:60]}")
    json.dump(log, open(LOG, "w", encoding="utf-8"), ensure_ascii=False)
    return got


def main():
    try:
        got = collect()
    except Exception as e:
        print("미래날짜 예매 수집 실패:", e)
        return 1
    print("미래날짜 선예매:", " · ".join(f"{d[5:]} {a:,}" for d, a in sorted(got.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
