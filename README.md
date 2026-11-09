# 공모주 나침반 (ipo.acoustic42.com)

OpenDART 공시(증권신고서 지분증권)를 수집해 공모주 청약 일정·공모가·수요예측 결과를 정적 사이트로 발행한다.

- `scripts/collect.py` — OpenDART 수집·파싱 → `data/ipos.json` (환경변수 `OPENDART_KEY` 필요)
- `scripts/build.py` — `data/ipos.json` → `dist/` 정적 사이트
- 워크플로 `.github/workflows/update.yml` — 하루 4회 + 수동 실행, GitHub Pages 배포
- 파싱 점검용 페이지: `/debug.html`
