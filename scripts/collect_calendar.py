# -*- coding: utf-8 -*-
"""주식 캘린더 수집기 (프로토타입 v1) — OpenDART 공시 기반.

공모주(collect.py)와 별도로, 인접 일정형 소재를 모은다:
- dividend  배당: '배당결정' 공시 원문에서 배당기준일·주당배당금 파싱
- meeting   주주총회: '주주총회소집' 공시 원문에서 총회일 파싱
- earnings  실적: '잠정실적'·'매출액또는손익구조' 공시는 발표 자체가 이벤트라
            공시 접수일을 이벤트 날짜로 기록 (원문 파싱 없음)

출력: data/calendar.json {"updated", "meta": {...}, "events": [...]}
meta에는 유형별 검색량·키워드 히트·문서 파싱 수를 남겨 첫 실행에서
분류(pblntf_ty) 가정이 맞는지 눈으로 검증할 수 있게 한다.

정확도 원칙: 날짜는 구조 키워드(배당기준일·주주총회일 등) 근처에서만 뽑고,
못 뽑으면 이벤트를 만들지 않는다. 틀린 날짜는 없는 날짜보다 나쁘다.
"""
import io, json, os, re, sys, time, zipfile, datetime, urllib.request, urllib.parse

KEY = os.environ["OPENDART_KEY"]
BASE = "https://opendart.fss.or.kr/api"
UA = {"User-Agent": "Mozilla/5.0"}
PARSER_VER = 3

# 공시 분류 가정 (v1에서 실측 검증): B 주요사항·E 기타·I 거래소공시
SEARCH_TYPES = ["B", "E", "I"]
LOOKBACK_DAYS = 14          # 이 기간의 '공시'에서 미래 일정을 뽑는다
MAX_PAGES_PER_TYPE = 400    # 유형당 목록 페이지 상한 (100건/페이지)
MAX_DOCS = 150              # 원문 다운로드 상한 (배당·주총만; 최신 접수 순)
EVENT_MIN_OFFSET = -3       # 오늘 기준 -3일 지난 일정까지 유지
EVENT_MAX_OFFSET = 150      # 오늘 기준 +150일 일정까지

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
    names.sort(key=lambda n: -zf.getinfo(n).file_size)
    xml = "\n".join(zf.read(n).decode("utf-8", "replace") for n in names)
    t = re.sub(r"<[^>]+>", " ", xml)
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", t)

# ---------- 날짜 파싱 ----------
DATE_RES = [
    re.compile(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일"),
    re.compile(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})"),
]

def norm_date(y, m, d):
    try:
        return datetime.date(int(y), int(m), int(d)).isoformat()
    except ValueError:
        return None

def dates_in(s):
    out = []
    for rx in DATE_RES:
        for y, m, d in rx.findall(s):
            v = norm_date(y, m, d)
            if v: out.append(v)
    return out

def window(text, kw, size=350, nth=0):
    idxs = [m.start() for m in re.finditer(re.escape(kw), text)]
    if len(idxs) <= nth: return ""
    i = idxs[nth]
    return text[i:i + size]

def date_near(text, keywords, size=350):
    """키워드 윈도우들의 날짜 중 마지막 윈도우의 첫 날짜.
    기재정정 문서에서는 앞부분 정정대조표에 '정정전' 옛 날짜가 먼저 나오므로
    첫 윈도우를 집으면 변경 전 날짜를 잡는 사고가 난다 (v1 실측: 비투엔·화일약품).
    본문 표는 문서 뒤쪽에 다시 실리므로 마지막 윈도우가 정본이다."""
    for kw in keywords:
        found = None
        for nth in range(8):
            w = window(text, kw, size, nth)
            if not w: break
            ds = dates_in(w)
            if ds: found = ds[0]
        if found: return found
    return None

def first_date_near(text, keywords, size=350):
    """키워드 첫 윈도우의 첫 날짜 (구간 안에서는 첫 등장이 정본)."""
    for kw in keywords:
        w = window(text, kw, size)
        if w:
            ds = dates_in(w)
            if ds: return ds[0]
    return None

def section_date(text, section_re, kw, seg_len):
    """본문 섹션(결의·결정 표)의 날짜를 뒤에서부터 찾는다.
    정정 문서는 정정대조표 뒤에 본문 표가 통째로 다시 실리므로 마지막 섹션이
    정본이고, 일반 문서의 뒤쪽 안내문(전자투표 일시 등)에 속지 않기 위해
    '첫 윈도우'(v1)·'마지막 윈도우'(v2) 대신 섹션 기준 탐색을 쓴다.
    (v2 실측: 한전 본문 12-07을 뒤쪽 안내 날짜 12-11로 오독한 사고.)"""
    starts = [m.start() for m in re.finditer(section_re, text)]
    for s in reversed(starts):
        d = first_date_near(text[s:s + seg_len], [kw], 400)
        if d: return d
    return None

# ---------- 종류별 파싱 ----------
def parse_dividend(text):
    """배당결정 원문 → {date: 배당기준일, dps: 주당배당금(보통주 우선)}"""
    f = {}
    d = section_date(text, r"배당\s*결정", "배당기준일", 2500)
    if not d: d = date_near(text, ["배당기준일", "기준일"], 300)
    if d: f["date"] = d
    # 주당배당금: '1주당 배당금' 표 구간(시가배당률 항목 앞까지)만 본다.
    # v1 실측 교정: 표기는 '보통주식'이 많고, 구간을 안 자르면 발행주식수 같은
    # 큰 숫자를 집는 사고가 난다 (이지스밸류플러스리츠 111억 오값).
    w = ""
    for kw in ("1주당 배당금", "주당배당금", "주당 배당금", "1주당배당금"):
        w = window(text, kw, 500)
        if w: break
    if w:
        cut = w.find("시가배당률")
        if cut > 0: w = w[:cut]
        m = re.search(r"보통주식?\s*[:：]?\s*([\d,]{2,})", w) or re.search(r"([\d,]{2,})\s*원", w)
        if m:
            v = int(m.group(1).replace(",", ""))
            if 10 <= v <= 1000000: f["dps"] = v
    return f

def parse_meeting(text):
    """주총 소집 원문 → {date: 주주총회일}"""
    f = {}
    d = section_date(text, r"주주총회소집\s*(결의|공고)", "일시", 900)
    if not d: d = first_date_near(text, ["주주총회일", "일시"], 300)
    if d: f["date"] = d
    return f

PARSERS = {"dividend": parse_dividend, "meeting": parse_meeting}

def classify(report_nm):
    nm = report_nm or ""
    if "배당결정" in nm: return "dividend"
    if "주주총회소집" in nm: return "meeting"
    # 잠정실적의 실제 보고서명은 '연결재무제표기준영업(잠정)실적(공정공시)' 형태가
    # 대부분이라 '잠정실적' 부분일치만으로는 못 잡는다 (v1 실측: 잠정 히트 0건).
    if "매출액또는손익구조" in nm: return "earnings"
    if "잠정" in nm and "실적" in nm: return "earnings"
    return None

def debug_excerpt(text, keywords):
    for kw in keywords:
        i = text.find(kw)
        if i >= 0: return text[max(0, i - 60):i + 240]
    return ""

def main():
    today = datetime.date.today()
    bgn = (today - datetime.timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    meta = {"parser_ver": PARSER_VER, "window": f"{bgn}~{end}", "types": {}}
    hits = []  # (type, filing)
    for ty in SEARCH_TYPES:
        total_c = None
        rows = []
        for page in range(1, MAX_PAGES_PER_TYPE + 1):
            d = get_json("/list.json", {"bgn_de": bgn, "end_de": end, "pblntf_ty": ty,
                                        "page_no": page, "page_count": 100})
            if d.get("status") != "000":
                print(f"list error ty={ty}:", d.get("status"), d.get("message"), flush=True); break
            total_c = int(d.get("total_count", 0))
            rows += d.get("list") or []
            if page * 100 >= total_c: break
        by_kind = {}
        for f in rows:
            k = classify(f.get("report_nm"))
            if k:
                by_kind[k] = by_kind.get(k, 0) + 1
                hits.append((k, f))
        meta["types"][ty] = {"total": total_c, "fetched": len(rows), "hits": by_kind}
        print(f"ty={ty} total={total_c} fetched={len(rows)} hits={by_kind}", flush=True)
    print("keyword hits:", len(hits), flush=True)

    lo = (today + datetime.timedelta(days=EVENT_MIN_OFFSET)).isoformat()
    hi = (today + datetime.timedelta(days=EVENT_MAX_OFFSET)).isoformat()
    events = {}
    docs = 0
    t0 = time.time()
    # 실적은 원문 없이 접수일이 곧 발표일
    for kind, f in hits:
        if kind != "earnings": continue
        rd = f"{f['rcept_dt'][:4]}-{f['rcept_dt'][4:6]}-{f['rcept_dt'][6:8]}"
        ev = {"type": "earnings", "corp_code": f["corp_code"], "corp_name": f["corp_name"],
              "date": rd, "rcept_no": f["rcept_no"], "rcept_dt": f["rcept_dt"],
              "report_nm": f["report_nm"],
              "dart_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={f['rcept_no']}"}
        events[(f["corp_code"], "earnings", rd)] = ev
    # 배당·주총은 원문 파싱. 문서 상한 안에서 배당이 먼저 소진되지 않게
    # 배당 → 주총 순, 각 종류 안에서는 최신 접수 순 (정정본이 이긴다).
    todo = sorted([h for h in hits if h[0] in PARSERS],
                  key=lambda h: (0 if h[0] == "dividend" else 1, -int(h[1]["rcept_no"])))
    seen_corp_kind = set()
    for kind, f in todo:
        if docs >= MAX_DOCS: break
        ck = (f["corp_code"], kind)
        if ck in seen_corp_kind: continue
        try:
            text = get_doc_text(f["rcept_no"])
            docs += 1
        except Exception as e:
            print(f"doc error {f['corp_name']} {f['rcept_no']}: {type(e).__name__}: {e}", flush=True)
            continue
        pf = PARSERS[kind](text)
        d = pf.get("date")
        if not d or not (lo <= d <= hi):
            continue
        seen_corp_kind.add(ck)
        ev = {"type": kind, "corp_code": f["corp_code"], "corp_name": f["corp_name"],
              "date": d, "rcept_no": f["rcept_no"], "rcept_dt": f["rcept_dt"],
              "report_nm": f["report_nm"],
              "dart_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={f['rcept_no']}",
              "debug": debug_excerpt(text, ["배당기준일"] if kind == "dividend" else ["주주총회일", "일시"])}
        if kind == "dividend" and pf.get("dps"): ev["dps"] = pf["dps"]
        events[(f["corp_code"], kind, d)] = ev
    print(f"docs parsed: {docs} | events raw: {len(events)} | elapsed={time.time() - t0:.0f}s", flush=True)

    ev_list = sorted(events.values(), key=lambda x: (x["date"], x["type"], x["corp_name"]))
    # 급감 가드: 직전 유효 건수의 50% 미만이면 직전 미래 일정을 이어 붙인다 (jobs·ipo와 같은 장치)
    try:
        prev = json.load(open("data/calendar.json", encoding="utf-8"))
        prev_events = prev.get("events", [])
    except Exception:
        prev_events = []
    if prev_events and len(ev_list) < len(prev_events) * 0.5:
        have = {(e["corp_code"], e["type"], e["date"]) for e in ev_list}
        kept = [e for e in prev_events
                if (e["corp_code"], e["type"], e["date"]) not in have and e["date"] >= lo]
        if kept:
            print(f"carry-over: kept {len(kept)} prev events (new {len(ev_list)} < 50% of prev {len(prev_events)})", flush=True)
            ev_list = sorted(ev_list + kept, key=lambda x: (x["date"], x["type"], x["corp_name"]))
    meta["events"] = {k: sum(1 for e in ev_list if e["type"] == k)
                      for k in ("dividend", "earnings", "meeting")}
    out = {"updated": datetime.datetime.now().isoformat(timespec="seconds"),
           "meta": meta, "events": ev_list}
    os.makedirs("data", exist_ok=True)
    with open("data/calendar.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print("events final:", len(ev_list), meta["events"], flush=True)

if __name__ == "__main__":
    main()
