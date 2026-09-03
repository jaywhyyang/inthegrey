# -*- coding: utf-8 -*-
"""
인 더 그레이 일일 리포트 — 매일 오전 10시(로컬) 실행.
- 어제(전일) 회원통계 실관객 최종을 KOBIS 로그인으로 조회(과거 날짜는 완전 확정치).
- 애널리스트 톤의 줄글 리포트 생성: 성적 + 인사이트 + 예측 자가점검 + 한계 + 생각할 거리.
- daily_report.json 저장(대시보드 상단 카드용) + Slack Incoming Webhook 발송(slack_webhook.txt 있으면).
- report_state.json에 일별 실측/예측을 누적 저장(다음날 자가점검용).
반복 실행/부분 데이터에 안전. 웹훅 없으면 발송만 건너뛰고 리포트·카드는 갱신.
"""
import os, re, io, json, math, datetime, urllib.request

import member_auto as M
import member_ingest as MI

BASE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(BASE, "report_state.json")
OUT_JSON = os.path.join(BASE, "daily_report.json")
WEBHOOK_FILE = os.path.join(BASE, "slack_webhook.txt")
BAND_LOCAL = os.path.join(BASE, "megabox_solo_band.json")
BAND_UP = os.path.join(BASE, "..", "그린랜드2", "megabox_solo_band.json")
OPEN_DATE = datetime.date(2026, 9, 2)
DASH_URL = "https://jaywhyyang.github.io/inthegrey/"
DOW = ["월", "화", "수", "목", "금", "토", "일"]


def _load(path, default):
    try:
        return json.load(io.open(path, encoding="utf-8"))
    except Exception:
        return default


def _band():
    for p in (BAND_LOCAL, BAND_UP):
        if os.path.exists(p):
            try:
                return json.load(io.open(p, encoding="utf-8"))
            except Exception:
                pass
    return {}


def _query_day(op, ds):
    """해당 날짜 회원통계 요약+상세 집계."""
    s = M._post(op, "/kobis/business/mast/thea/findCompanyStatXls.do", {}, ds)
    summ = MI.parse_summary_html(s) or {}
    d = M._post(op, "/kobis/business/mast/thea/findCompanyStatDetailXls.do", {"movieCd": M.MOVIE_CD}, ds)
    cr = [[re.sub(r"<[^>]+>", "", c) for c in re.findall(r"<Data[^>]*>(.*?)</Data>", r, re.S)]
          for r in re.findall(r"<Row[^>]*>(.*?)</Row>", d, re.S)]
    det = MI.aggregate_detail(cr)
    return summ, det


def _short(name):
    for p in ("메가박스 ", "CGV ", "롯데시네마 "):
        if name.startswith(p):
            return name[len(p):]
    return name


def _man(n):
    """사람이 읽는 만 단위(예: 17234 -> '1.7만')."""
    return f"{n/10000:.1f}만"


def _pcum(n, pac):
    """페이싱(누적비중) 곡선을 일차 보간해 n일차 누적비중 반환."""
    pts = sorted((int(k[1:]), v) for k, v in pac.items() if k.startswith("D"))
    if not pts:
        return None
    pts = [(0, 0.0)] + pts
    if n <= 0:
        return 0.0
    if n >= pts[-1][0]:
        return min(1.0, pts[-1][1])
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= n <= x1:
            return y0 + (y1 - y0) * (n - x0) / (x1 - x0)
    return pts[-1][1]


def build(target=None, dry=False):
    op = M.login()
    y = target or (datetime.date.today() - datetime.timedelta(days=1))
    ys = y.strftime("%Y-%m-%d")
    day_n = (y - OPEN_DATE).days + 1          # 개봉일=1일차
    summ, det = _query_day(op, ys)
    daily = MI._num(str(summ.get("관객수"))) or det.get("total") or 0
    cum = MI._num(str(summ.get("누적관객수"))) or 0
    shows = MI._num(str(summ.get("상영횟수"))) or 0
    screens = MI._num(str(summ.get("스크린수"))) or 0
    sales = MI._num(str(summ.get("매출액"))) or 0
    per_show = daily / shows if shows else 0

    st = _load(STATE, {"open_admits": None, "finals": {}, "predictions": {}, "screens": {}})
    # 전일(감소율용)
    prev = st["finals"].get((y - datetime.timedelta(days=1)).strftime("%Y-%m-%d"))
    st["finals"][ys] = daily
    st["screens"][ys] = screens
    if day_n == 1:
        st["open_admits"] = daily
    open_admits = st.get("open_admits") or daily

    # 모델 최종 + 페이싱
    band = _band()
    model = band.get("model", {})
    pac = (band.get("pacing", {}) or {}).get("median", {})
    a, b = model.get("a"), model.get("b")
    final_model = math.exp(a + b * math.log(open_admits)) if (a and b and open_admits > 0) else None
    d1f = pac.get("D1")
    final_pace = open_admits / d1f if d1f else None
    # D3 판정
    verdict = None
    if day_n >= 3 and final_model:
        frac = cum / final_model
        verdict = ("즉시소진형(개봉 몰아보기)" if frac > 0.40 else
                   "롱런형(주말·입소문 견인)" if frac < 0.34 else "경계(즉시소진~롱런 사이)")

    # 자가점검(어제에 대해 우리가 로그해둔 예측)
    pred = st["predictions"].get(ys)
    # 다음날 예측 로그(자가점검용): 페이싱 곡선의 일별 증분 × 모델 최종
    nd = y + datetime.timedelta(days=1)
    if final_model and pac:
        nn = day_n + 1
        pd = (_pcum(nn, pac) - _pcum(nn - 1, pac)) * final_model
        st["predictions"][nd.strftime("%Y-%m-%d")] = int(round(max(0, pd) / 100.0) * 100)

    ctx = dict(ys=ys, dow=DOW[y.weekday()], day_n=day_n, daily=daily, cum=cum, shows=shows,
               screens=screens, sales=sales, per_show=per_show, prev=prev,
               theaters=det.get("theaters", []), regions=det.get("regions", []),
               slots=det.get("slots", []), open_admits=open_admits,
               final_model=final_model, final_pace=final_pace, verdict=verdict, pred=pred,
               band=band)
    text = _prose(ctx)
    payload = {"date": ys, "day_n": day_n, "daily": daily, "cum": cum,
               "final_model": int(final_model) if final_model else None,
               "verdict": verdict, "text": text, "updated": datetime.datetime.now().strftime("%m-%d %H:%M")}
    if not dry:
        json.dump(payload, io.open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        json.dump(st, io.open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        _post_slack(text)
    return text


def _prose(c):
    P = []
    dn = c["day_n"]
    label = "개봉일" if dn == 1 else f"개봉 {dn}일차"
    P.append(f"📊 *인 더 그레이 · 일일 리포트 | {c['ys'][5:].replace('-', '월 ')}일({c['dow']}) {label}*")
    # 성적
    per = c["per_show"]
    tone = "알찬 회전" if per >= 15 else "무난" if per >= 8 else "편성 대비 얕은 회전"
    s1 = (f"어제 실관객은 *{c['daily']:,}명*(누적 {c['cum']:,}), {c['screens']}개 관에서 {c['shows']}회를 돌려 "
          f"회당 평균 {per:.1f}명이 들었습니다({tone}). 매출은 약 {c['sales']//10000:,}만원입니다.")
    P.append(s1)
    # 감소/증가
    if c["prev"]:
        ch = (c["daily"] - c["prev"]) / c["prev"] * 100
        if ch <= -35:
            P.append(f"전일 대비 *{ch:+.0f}%*로 감소가 가파릅니다 — 초반에 수요가 앞으로 몰리는 즉시소진 성향을 시사합니다.")
        elif ch < 0:
            P.append(f"전일 대비 {ch:+.0f}%로 완만히 줄었습니다 — 급격한 이탈은 아닙니다.")
        else:
            P.append(f"전일 대비 *{ch:+.0f}%*로 오히려 늘었습니다 — 주말·입소문 반등 신호일 수 있습니다.")
    # 인사이트: 관별·지역·시간대
    th = c["theaters"][:3]
    if th:
        tstr = " · ".join(f"{_short(t[0])}({t[1]})" for t in th)
        rg = c["regions"][:2]
        rgstr = " · ".join(f"{r[0].replace('특별시','').replace('광역시','')} {r[1]:,}" for r in rg)
        seoul = next((r[1] for r in c["regions"] if "서울" in r[0]), 0)
        gg = next((r[1] for r in c["regions"] if "경기" in r[0]), 0)
        capital = (seoul + gg) / c["daily"] * 100 if c["daily"] else 0
        P.append(f"관객은 대도시 도심에 집중됐습니다. 상위 극장은 {tstr}, 지역은 {rgstr}로 "
                 f"수도권이 약 {capital:.0f}%를 차지했습니다.")
    sl = c["slots"]
    if sl and any(sl):
        peak = sl.index(max(sl)) + 1
        early = sum(sl[:3]); late = sum(sl[4:])
        when = "낮 회차가 저녁보다 강했습니다" if early > late else "저녁 회차가 낮보다 강했습니다"
        P.append(f"시간대는 {peak}회차가 정점이고 {when} — 관객층·관람 패턴의 단서지만 하루치라 단정은 이릅니다.")
    # 자가점검
    if c["pred"]:
        err = (c["pred"] - c["daily"]) / c["daily"] * 100 if c["daily"] else 0
        if abs(err) <= 10:
            P.append(f"*예측 자가점검.* 어제 우리가 본 예상은 약 {c['pred']:,}명이었고 실제 {c['daily']:,}명 — 오차 {err:+.0f}%로 잘 맞았습니다.")
        else:
            why = "선예매가 앞당겨져 예측이 부풀었" if err > 0 else "주말·현매 유입을 과소평가했"
            P.append(f"*예측 자가점검.* 어제 예상은 약 {c['pred']:,}명, 실제 {c['daily']:,}명으로 {err:+.0f}% 빗나갔습니다 — {why}던 것으로 보입니다. 예측 규칙을 계속 보정 중입니다.")
    # 최종
    if c["final_model"]:
        pieces = [f"회귀모델 최종 *약 {_man(c['final_model'])}명*"]
        if c["final_pace"]:
            pieces.append(f"페이싱 역산 약 {_man(c['final_pace'])}명")
        it = c["band"].get("model", {}).get("interval_68")
        lim = ""
        if it:
            lo = c["final_model"] * it[0]; hi = c["final_model"] * it[1]
            lim = f" 다만 68% 구간이 {_man(lo)}~{_man(hi)}으로 넓고(표본 적음), "
        wk = "첫 주말이 아직 안 왔다는 점" if c["day_n"] <= 3 else "주말·평일 리듬"
        P.append(f"*최종 전망.* 개봉일 {c['open_admits']:,}명 기준 {', '.join(pieces)}으로 겹칩니다(밴드 하단~중심)."
                 f"{lim}{wk}을 함께 감안해야 합니다.")
    # D3 판정
    if c["verdict"]:
        P.append(f"*3일차 판정.* 누적/최종 비중으로 보면 현재는 *{c['verdict']}*에 가깝습니다.")
    # 생각할 거리
    P.append("*생각할 거리.* 편성 축소가 수요를 따라간 조정인지, 극장이 성급히 뺀 것인지는 "
             "주말 좌석판매율로 갈립니다. 관을 넓히기보다 잘 드는 극장·시간대에 회차를 몰아주는 게 "
             "이 작품엔 더 맞을 수 있습니다.")
    P.append(f"📈 실시간 대시보드: {DASH_URL}")
    return "\n\n".join(P)


def _post_slack(text):
    if not os.path.exists(WEBHOOK_FILE):
        print("webhook 없음: Slack 발송 건너뜀(리포트/카드는 저장됨)")
        return
    url = io.open(WEBHOOK_FILE, encoding="utf-8").read().strip()
    if not url.startswith("https://hooks.slack.com/"):
        print("webhook URL 형식 아님: 발송 건너뜀")
        return
    body = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=30).read()
        print("Slack 발송 완료")
    except Exception as e:
        print("Slack 발송 실패:", str(e)[:120])


if __name__ == "__main__":
    import sys
    tgt = None
    dry = "--dry" in sys.argv
    for a in sys.argv[1:]:
        if re.match(r"\d{4}-\d{2}-\d{2}", a):
            tgt = datetime.datetime.strptime(a, "%Y-%m-%d").date()
    out = build(target=tgt, dry=dry)
    io.open(os.path.join(BASE, "_last_report.txt"), "w", encoding="utf-8").write(out)
    print("리포트 생성 완료 (_last_report.txt 저장)")
