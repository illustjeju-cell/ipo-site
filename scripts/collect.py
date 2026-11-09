# -*- coding: utf-8 -*-
"""공모주 나침반 수집기 — OpenDART 공시 기반.

증권신고서(지분증권) 공시를 모아 종목별로 묶고, 가장 최신 신고서 원본에서
청약 일정·공모가·주관사·수요예측 결과를 뽑아 data/ipos.json 으로 저장한다.
파싱이 빗나간 경우를 눈으로 확인할 수 있게 종목마다 debug 발췌를 함께 남긴다.
"""
import io, json, os, re, sys, time, zipfile, datetime, urllib.request, urllib.parse
from collections import Counter

KEY = os.environ["OPENDART_KEY"]
BASE = "https://opendart.fss.or.kr/api"
UA = {"User-Agent": "Mozilla/5.0"}
LOOKBACK_DAYS = 60
MAX_DOCS = 500
PARSER_VER = 8

def get_json(path, params):
    q = urllib.parse.urlencode({"crtfc_key": KEY, **params})
    req = urllib.request.Request(f"{BASE}{path}?{q}", headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def get_doc_text(rcept_no):
    q = urllib.parse.urlencode({"crtfc_key": KEY, "rcept_no": rcept_no})
    req = urllib.request.Request(f"{BASE}/document.xml?{q}", headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
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

def parse_fields(text, allow_final=False, is_result=False):
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
    # 확정공모가 (v6): 확정 단계 문서(발행조건확정 정정·실적보고서)에서만 뽑는다.
    # 최초·일반 정정 문서의 "확정공모가 N원"은 수수료 계산 예시 등 가정 문장이라 밴드 상한을 집는 오작동이 실측됨 (에이엘로봇 실제 15,700 vs 오추출 17,600).
    if allow_final:
        direct = None
        m = re.search(r"확정공모가[^\d]{0,120}?([\d,]{3,})\s*원\s*(?:으로|로)\s*결정", text)
        if m: direct = int(m.group(1).replace(",", ""))
        if direct is None and is_result:
            m = re.search(r"(?:최종\s*)?발행가액[^\d]{0,20}([\d,]{3,})\s*원", text)
            if m: direct = int(m.group(1).replace(",", ""))
        if direct is None:
            for hit in list(re.finditer("확정공모가", text))[:8]:
                w = text[hit.start():hit.start() + 350]
                if any(g in w for g in ("경우", "가정", "상한인", "하한인")): continue
                mm = (re.search(r"확정공모가액?\s*(?:은|는|이|가)?\s*(?:금\s*)?([\d,]{3,})\s*원", w)
                      or re.search(r"1주당\s*확정공모가[^\d]{0,20}([\d,]{3,})\s*원", w))
                if mm: direct = int(mm.group(1).replace(",", "")); break
        # 교차검증 (v8): '인수금액'이 처음 나오는 위치부터 끝까지의 표에서 '보통주 주식수 총액' 쌍을 모아
        # 단가로 역산하고 최빈값을 쓴다. v7은 문서 첫 매치만 써서 앞부분 예정표(밴드 하한 기준)에 걸려
        # 확정가 전 건이 하한으로 쏠렸다. 인수표 이후의 표(인수·청약 안내)는 확정 조건으로 다시 쓰인 값이다.
        region = text
        ai = text.find("인수금액")
        if ai >= 0: region = text[ai:]
        vals = []
        for mi in re.finditer(r"보통주\s+([\d,]{3,})\s*주?\s+([\d,]{7,})\s*원?", region):
            sh = int(mi.group(1).replace(",", "")); tot = int(mi.group(2).replace(",", ""))
            if sh and tot % sh == 0:
                v = tot // sh
                if 100 <= v <= 2000000: vals.append(v)
        mode_imp = None
        if vals:
            v, c = Counter(vals).most_common(1)[0]
            if ai >= 0 or c >= 2: mode_imp = v
        if mode_imp is not None: f["price_final"] = mode_imp
        elif direct is not None: f["price_final"] = direct
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
    # 실적보고서: 일반청약 경쟁률 ('청약' 맥락 윈도우의 첫 비율)
    if is_result:
        for hit in list(re.finditer("경쟁률", text))[:20]:
            w = text[max(0, hit.start() - 200):hit.start() + 200]
            if "청약" not in w: continue
            r = ratio_in(w)
            if r: f["sub_ratio"] = r; break
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
    total_c = None
    for page in range(1, 121):
        d = get_json("/list.json", {"bgn_de": bgn, "end_de": end, "pblntf_ty": "C",
                                    "page_no": page, "page_count": 100})
        if d.get("status") != "000":
            print("list error:", d.get("status"), d.get("message"), flush=True); break
        total_c = int(d.get("total_count", 0))
        filings += d.get("list") or []
        if page * 100 >= total_c: break
    print("filings(all C):", len(filings), "of total", total_c, flush=True)
    # 상세유형 코드에 의존하지 않고 보고서명으로 거른다 (실측: 코드 필터가 채무증권을 섞어 반환함).
    # v6: 증권발행실적보고서도 포함 — 확정가·청약 결과의 최종 출처다 (제목에 '지분증권'이 없어 v5까지 누락됨).
    filings = [f for f in filings if "지분증권" in (f.get("report_nm") or "") or "증권발행실적보고서" in (f.get("report_nm") or "")]
    print("filings(지분증권+실적):", len(filings), flush=True)
    by_corp = {}
    for it in filings:
        by_corp.setdefault(it["corp_code"], []).append(it)
    # v7: 종목은 지분증권 신고서가 있는 회사만 만든다. 실적보고서만 있는 회사(상장사·금융사 발행 등)는
    # 공모주가 아니므로 제외하고, 실적보고서는 해당 종목의 병합 문서로만 쓴다.
    # (v6 실측: 실적 단독 종목 109개가 섞여 문서 예산을 잠식하고 진짜 종목이 빈칸이 됐다.)
    by_corp = {cc: fs for cc, fs in by_corp.items()
               if any("지분증권" in (x.get("report_nm") or "") for x in fs)}
    print("items 대상(지분증권 보유):", len(by_corp), flush=True)
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
    t0 = time.time()
    # v7: 2단계 파싱. 1차는 전 종목 대표 문서만 읽어 문서 상한에 중간 종목이 굶는 일을 막고,
    # 2차는 핵심 필드가 빈 종목만 추가 문서(정정·실적)를 병합한다.
    prepared = []
    for corp_code, fs in by_corp.items():
        fs.sort(key=lambda x: x["rcept_no"])
        def rank(x):
            nm = x["report_nm"]
            return (3 if "증권발행실적보고서" in nm else
                    2 if "발행조건확정" in nm else
                    1 if "기재정정" in nm or "첨부정정" in nm else 0, x["rcept_no"])
        main_f = max(fs, key=rank)
        item = {"corp_code": corp_code, "corp_name": main_f["corp_name"],
                "stage": "확정" if ("발행조건확정" in main_f["report_nm"] or "증권발행실적보고서" in main_f["report_nm"]) else "예정",
                "rcept_no": main_f["rcept_no"], "rcept_dt": main_f["rcept_dt"],
                "dart_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={main_f['rcept_no']}",
                "filings": len(fs),
                "filings_nm": [x["report_nm"] for x in fs]}
        items.append(item)
        old = cache.get(corp_code)
        if old and old.get("rcept_no") == main_f["rcept_no"] and not old.get("error") and old.get("pv") == PARSER_VER:
            for k, v in old.items():
                if k not in item: item[k] = v
            reused += 1
            prepared.append(None)
        else:
            prepared.append({"item": item, "ranked": sorted(fs, key=rank, reverse=True),
                             "rank": rank, "fields": {}, "debug": None, "err": None})
    print("docs reused:", reused, flush=True)
    for pass_no in (1, 2):
        for ci, p in enumerate(prepared):
            if p is None: continue
            if ci and ci % 20 == 0:
                print(f"progress(pass{pass_no}): corp {ci}/{len(prepared)} docs={docs} elapsed={time.time() - t0:.0f}s", flush=True)
            if docs >= MAX_DOCS: break
            if pass_no == 1:
                targets = p["ranked"][:1]
            else:
                f = p["fields"]
                if f.get("sub_start") and f.get("price_low") and f.get("price_final") and f.get("demand_ratio"): continue
                targets = [x for x in p["ranked"][1:] if p["rank"](x)[0] >= 1][:2]
            for rf in targets:
                if docs >= MAX_DOCS: break
                td = time.time()
                try:
                    text = get_doc_text(rf["rcept_no"])
                    docs += 1
                except Exception as e:
                    p["err"] = f"{type(e).__name__}: {e}"
                    continue
                if time.time() - td > 20:
                    print(f"slow doc: {p['item']['corp_name']} {rf['rcept_no']} {time.time() - td:.0f}s len={len(text)}", flush=True)
                if p["debug"] is None: p["debug"] = debug_excerpts(text)
                pf = parse_fields(text, allow_final=p["rank"](rf)[0] >= 2,
                                  is_result="증권발행실적보고서" in rf["report_nm"])
                for k, v in pf.items():
                    if k not in p["fields"]: p["fields"][k] = v
                if p["fields"].get("demand_ratio") and p["fields"].get("price_final"): break
    for p in prepared:
        if p is None: continue
        item = p["item"]
        if p["fields"]:
            item.update(p["fields"])
            if p["debug"] is not None: item["debug"] = p["debug"]
            if p["fields"].get("price_final"): item["stage"] = "확정"
            item["pv"] = PARSER_VER
        elif p["err"]:
            item["error"] = p["err"]
    items.sort(key=lambda x: (x.get("sub_start") is None, x.get("sub_start") or "9999", x["corp_name"]))
    out = {"updated": datetime.datetime.now().isoformat(timespec="seconds"), "items": items}
    os.makedirs("data", exist_ok=True)
    with open("data/ipos.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print("items:", len(items), "| docs parsed:", docs, f"| elapsed={time.time() - t0:.0f}s", flush=True)

if __name__ == "__main__":
    main()
