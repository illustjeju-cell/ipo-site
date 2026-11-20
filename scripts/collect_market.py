# -*- coding: utf-8 -*-
"""오늘의 상한가·하한가 수집 — 네이버 증권(m.stock.naver.com) 시가총액 목록 API를 전 종목 스캔해
가격제한폭 도달 종목을 정확히 가려낸다. 상한가 = 전일종가×1.3을 호가단위로 절사한 가격과 종가 일치,
하한가 = 전일종가×0.7을 호가단위로 절상한 가격과 종가 일치 (KRX 가격제한폭 산정 방식).
장중에는 그 시각 기준, 장 마감 후에는 확정 종가 기준이다. 결과는 data/market.json."""
import json, math, os, sys, datetime, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "market.json")
API = "https://m.stock.naver.com/api/stocks/marketValue/{m}?page={p}&pageSize=100"

def fetch(market):
    out, page = [], 1
    while page <= 40:
        req = urllib.request.Request(API.format(m=market, p=page), headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
        out.extend(d.get("stocks") or [])
        total = d.get("totalCount") or len(out)
        if len(out) >= total or not d.get("stocks"):
            break
        page += 1
    return out

def tick(p):
    if p < 2000: return 1
    if p < 5000: return 5
    if p < 20000: return 10
    if p < 50000: return 50
    if p < 200000: return 100
    if p < 500000: return 500
    return 1000

def num(s):
    s = str(s or "0")
    neg = s.startswith("-")
    v = int(s.replace(",", "").replace("-", "").replace("+", "") or 0)
    return -v if neg else v

def main():
    upper, lower, traded_at = [], [], ""
    scanned = 0
    for mk in ("KOSPI", "KOSDAQ"):
        for s in fetch(mk):
            scanned += 1
            traded_at = max(traded_at, s.get("localTradedAt") or "")
            close = num(s.get("closePrice"))
            prev = close - num(s.get("compareToPreviousClosePrice"))
            if prev <= 0 or close <= 0:
                continue
            t = tick(prev)
            lim_up = math.floor(prev * 1.3 / t) * t
            lim_dn = math.ceil(prev * 0.7 / t) * t
            item = {"name": s["stockName"], "code": s["itemCode"], "market": mk,
                    "close": close, "ratio": float(s.get("fluctuationsRatio") or 0),
                    "value": num(s.get("accumulatedTradingValue"))}  # 단위: 백만원
            if close == lim_up:
                upper.append(item)
            elif close == lim_dn:
                lower.append(item)
    upper.sort(key=lambda z: -z["value"])
    lower.sort(key=lambda z: -z["value"])
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    data = {"date": (traded_at[:10] or now.date().isoformat()),
            "collected_at": now.isoformat(timespec="minutes"),
            "scanned": scanned, "upper": upper, "lower": lower}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"market: scanned {scanned}, upper {len(upper)}, lower {len(lower)}, date {data['date']}")

if __name__ == "__main__":
    main()
