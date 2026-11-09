# -*- coding: utf-8 -*-
"""공모주 나침반 수집기 — OpenDART 공시 기반.

증권신고서(지분증권) 공시를 모아 종목별로 묶고, 가장 최신 신고서 원본에서
청약 일정·공모가·주관사·수요예측 결과를 뽑아 data/ipos.json 으로 저장한다.
파싱이 빗나간 경우를 눈으로 확인할 수 있게 종목마다 debug 발췌를 함께 남긴다.
"""
import io, json, os, re, sys, zipfile, datetime, urllib.request, urllib.parse

KEY = os.environ["OPENDART_KEY"]
BASE = "https://opendart.fss.or.kr/api"
UA = {"User-Agent": "Mozilla/5.0"}
LOOKBACK_DAYS = 60
MAX_DOCS = 300
PARSER_VER = 4

def get_json(path, params):
    q = urllib.parse.urlencode({"crtfc_key": KEY, **params})
    req = urllib.request.Request(f"{BASE}{path}?{q}", headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def get_doc_text(rcept_no):
    q = urllib.parse.urlencode({"crtfc_key": KEY, "rcept_no": rcept_no})
    req = urllib.request.Request(f"{BASE}/document.xml?{q}", headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    zf = zipfile.ZipFile(io.BytesIO(raw))
    names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
    name = max(names, key=lambda n: zf.getinfo(n).file_size)
    xml = zf.read(name).decode("utf-8", "replace")
    t = re.sub(r"<[^>]+>", " ", xml)
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", t)

DATE_RE = re.compile(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일")
def dates_in(s):
    return [f"{y}-{int(m):02d}-{int(d):02d}" for y, m, d in DATE_RE.findall(s)]

def window(text, kw, size=350, nth=0):
    idxs = [m.start() for m in re.finditer(re.escape(kw), text)]
    if len(idxs) <= nth: return ""
    i = idxs[nth]
    return text[i:i + size]

def first_num(s, unit="원"):
    m = re.search(r"([\d,]{3,})\s*" + unit, s)
    return int(m.group(1).replace(",", "")) if m else None

def parse_fields(text):
    f = {}
    # 청약일: '청약기일' 뒤에서 날짜 범위(DATE ~ DATE)를 먼저 찾고, 없으면 첫 날짜 하루
    w = window(text, "청약기일", 500) or window(text, "청약일", 500)
    m = re.search(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일\s*[~∼\-]\s*(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", w)
    if m:
        f["sub_start"] = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        f["sub_end"] = f"{m.group(4)}-{int(m.group(5)):02d}-{int(m.group(6)):02d}"
    else:
        ds = dates_in(w)
        if ds: f["sub_start"] = f["sub_end"] = ds[0]
    # 수요예측일
    w = window(text, "수요예측일") or window(text, "수요예측기간")
    ds = dates_in(w)
    if ds: f["demand_start"], f["demand_end"] = ds[0], ds[-1]
    # 상장일
    w = window(text, "상장예정일") or window(text, "상장일")
    ds = dates_in(w)
    if ds: f["listing_date"] = ds[0]
    # 희망공모가 밴드: 목차에 먼저 걸리므로 여러 등장 위치를 스캔한다
    band = None
    for kw in ("희망공모가", "공모희망가액", "희망공모가액"):
        for nth in range(8):
            w = window(text, kw, 350, nth)
            if not w: break
            m = re.search(r"([\d,]{3,})\s*원\s*[~∼\-]\s*([\d,]{3,})\s*원", w)
            if m: band = (int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))); break
        if band: break
    if band: f["price_low"], f["price_high"] = band
    # 확정공모가: 명시 패턴 우선, 여러 등장 위치 스캔
    for nth in range(8):
        w = window(text, "확정공모가", 350, nth)
        if not w: break
        m = (re.search(r"최저가액인\s*([\d,]{3,})\s*원", w)
             or re.search(r"확정공모가액?\s*(?:은|는|이|가)?\s*(?:금\s*)?([\d,]{3,})\s*원", w)
             or re.search(r"1주당\s*확정공모가[^\d]{0,20}([\d,]{3,})\s*원", w))
        if m: f["price_final"] = int(m.group(1).replace(",", "")); break
    # 공모주식수
    w = window(text, "공모주식수") or window(text, "모집주식수") or window(text, "공모할 주식수")
    m = re.search(r"([\d,]{3,})\s*주", w)
    if m: f["shares"] = int(m.group(1).replace(",", ""))
    # 대표주관회사: '대표주관회사' 바로 뒤 회사명, 안 되면 인수표의 '대표 ○○증권'
    m = re.search(r"대표주관회사\s*(?:\(주\)|㈜)?\s*([가-힣A-Za-z]{2,12}(?:증권|은행))", text)
    if not m: m = re.search(r"대표\s+([가-힣A-Za-z]{2,12}(?:증권|은행))", text)
    if m: f["underwriter"] = m.group(1).strip()
    # 수요예측 경쟁률 (v4): '수요예측 결과' 섹션을 앵커로 우선 탐색하고,
    # 없으면 '경쟁률' 전 출현 위치에서 수요예측·기관 맥락이 있는 것만 스캔한다
    r = find_demand_ratio(text)
    if r: f["demand_ratio"] = r
    # 의무보유확약 비율
    w = window(text, "의무보유확약")
    m = re.search(r"([\d.]+)\s*%", w)
    if m: f["lockup_pct"] = float(m.group(1))
    return f

def ratio_in(w):
    for pat in (r"([\d,]+\.?\d*)\s*[:：]\s*1(?![\d])", r"([\d,]+\.?\d*)\s*대\s*1(?![\d])"):
        for m in re.finditer(pat, w):
            try: v = float(m.group(1).replace(",", ""))
            except ValueError: continue
            if 1 < v < 100000: return v
    return None

def find_demand_ratio(text):
    # 1) '수요예측 결과' 섹션 앵커 — 결과 표가 이 뒤에 붙는다
    for m in re.finditer(r"수요예측\s*결과", text):
        r = ratio_in(text[m.start():m.start() + 1800])
        if r: return r
    # 2) '경쟁률' 전 출현 스캔 — 수요예측·기관 맥락이 있는 윈도우만
    for m in list(re.finditer("경쟁률", text))[:60]:
        w = text[max(0, m.start() - 300):m.start() + 300]
        if "수요예측" not in w and "기관" not in w: continue
        r = ratio_in(w)
        if r: return r
    return None

def debug_excerpts(text):
    out = {}
    for kw in ("청약기일", "희망공모가", "확정공모가", "수요예측", "대표주관회사"):
        i = text.find(kw)
        if i >= 0: out[kw] = text[max(0, i - 60):i + 240]
    i = text.find("수요예측 결과")
    if i >= 0: out["수요예측결과"] = text[i:i + 600]
    out["_경쟁률수"] = str(len(re.findall("경쟁률", text)))
    return out

def main():
    today = datetime.date.today()
    bgn = (today - datetime.timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    filings = []
    for page in range(1, 41):
        d = get_json("/list.json", {"bgn_de": bgn, "end_de": end, "pblntf_ty": "C",
                                    "page_no": page, "page_count": 100})
        if d.get("status") != "000":
            print("list error:", d.get("status"), d.get("message")); break
        filings += d.get("list") or []
        if page * 100 >= int(d.get("total_count", 0)): break
    print("filings(all C):", len(filings))
    # 상세유형 코드에 의존하지 않고 보고서명으로 지분증권만 거른다 (실측: 코드 필터가 채무증권을 섞어 반환함)
    filings = [f for f in filings if "지분증권" in (f.get("report_nm") or "")]
    print("filings(지분증권):", len(filings))
    by_corp = {}
    for it in filings:
        by_corp.setdefault(it["corp_code"], []).append(it)
    # 지난 실행 결과 캐시: 접수번호가 같은 종목은 파싱 결과를 재사용한다
    cache = {}
    try:
        prev = json.load(open("data/ipos.json", encoding="utf-8"))
        cache = {x["corp_code"]: x for x in prev.get("items", [])}
    except Exception:
        pass
    items = []
    docs = 0
    reused = 0
    for corp_code, fs in by_corp.items():
        fs.sort(key=lambda x: x["rcept_no"])
        def rank(x):
            nm = x["report_nm"]
            return (2 if "발행조건확정" in nm else 1 if "기재정정" in nm or "첨부정정" in nm else 0, x["rcept_no"])
        main_f = max(fs, key=rank)
        item = {"corp_code": corp_code, "corp_name": main_f["corp_name"],
                "stage": "확정" if "발행조건확정" in main_f["report_nm"] else "예정",
                "rcept_no": main_f["rcept_no"], "rcept_dt": main_f["rcept_dt"],
                "dart_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={main_f['rcept_no']}",
                "filings": len(fs)}
        old = cache.get(corp_code)
        if old and old.get("rcept_no") == main_f["rcept_no"] and not old.get("error") and old.get("pv") == PARSER_VER:
            for k, v in old.items():
                if k not in item: item[k] = v
            reused += 1
        elif docs < MAX_DOCS:
            # v4: 대표 문서 1개만 보지 않고 상위 3개 공시를 병합한다.
            # 수요예측 경쟁률·확정가는 최초 신고서가 아닌 정정(발행조건확정)에만 있는 경우가 많다.
            ranked = sorted(fs, key=rank, reverse=True)[:3]
            merged = {}
            first_debug = None
            last_err = None
            for rf in ranked:
                if docs >= MAX_DOCS: break
                try:
                    text = get_doc_text(rf["rcept_no"])
                    docs += 1
                except Exception as e:
                    last_err = f"{type(e).__name__}: {e}"
                    continue
                if first_debug is None: first_debug = debug_excerpts(text)
                for k, v in parse_fields(text).items():
                    if k not in merged: merged[k] = v
                if merged.get("demand_ratio") and merged.get("price_final"): break
            if merged:
                item.update(merged)
                if first_debug is not None: item["debug"] = first_debug
                if merged.get("price_final"): item["stage"] = "확정"
                item["pv"] = PARSER_VER
            elif last_err:
                item["error"] = last_err
        items.append(item)
    print("docs reused:", reused)
    items.sort(key=lambda x: (x.get("sub_start") is None, x.get("sub_start") or "9999", x["corp_name"]))
    out = {"updated": datetime.datetime.now().isoformat(timespec="seconds"), "items": items}
    os.makedirs("data", exist_ok=True)
    with open("data/ipos.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print("items:", len(items), "| docs parsed:", docs)

if __name__ == "__main__":
    main()
