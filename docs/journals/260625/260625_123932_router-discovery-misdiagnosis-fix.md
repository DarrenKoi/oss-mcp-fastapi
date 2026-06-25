# 라우터 자동발견 "BUG-1" 오진 정정 + 테스트 자동화 (2026-06-25)

저널을 점검해 다음 할 일을 정리하던 중, 최우선 블로커로 적혀 있던 **BUG-1
(실서버가 `/health` 외 라우터를 하나도 등록하지 않는다)** 을 재조사한 세션이다.
결론부터: **BUG-1 은 버그가 아니라 오진이었다.** 진짜 문제는 테스트/진단이 쓰던
판별식이었고, 그걸 자동 적응형(auto-adapt) 테스트로 교체했다.

## 1. 진행 사항

- `docs/journals/` 의 저널들을 점검해 미결 작업을 정리(BUG-1, member_info 후속 등).
- BUG-1 을 체계적으로 재조사:
  - 환경부터 정리 — 기존 `.venv` 가 Python 3.14 + 깨진 의존성이라 `python3.11 -m venv .venv --clear`
    로 3.11 환경을 새로 만들고 `requirements.txt` 설치.
  - `uvicorn app.main:app` 의 전역 `app` 에 `TestClient` 로 직접 요청 → 모든 라우터가 정상
    응답함을 확인(`/oss/v1/health`·`/mcp/v1/health`·`/oss/mtc/v1/health`·
    `/skewnono/member_info/v1/health` → 200, `/ftp-proxy/v1/list` → 422 = 라우팅 정상).
  - 저널의 가설(`walk_packages` partial-init + ImportError 삼킴)을 `onerror` 주입·
    `import_module`/`FastAPI.include_router`/실행횟수 카운터로 차례로 검증 → **모두 반증**.
  - 진짜 원인 규명: FastAPI 0.138.0 에서 `include_router()` 가 하위 라우터를 `app.routes`
    에 `fastapi.routing._IncludedRouter` 마운트 객체로 보관하고 자식 라우트를 최상위
    `APIRoute` 로 펼치지 않음 → `isinstance(route, APIRoute)` 판별식이 포함 라우트를
    전부 걸러 내어 "비어 보였던" 것(저널 작성자와 테스트가 동일한 잘못된 자[尺]를 사용).
- 공유 저장소 컨벤션 방향을 사용자와 합의: **auto-adapt** (라우터 추가 시 테스트 수정 불필요,
  서비스별 `/health` 강제 없음).
- 재작성한 테스트가 실제로 자동 적응하는지 검증: 임시 `app/scratch_demo/router_v1.py`
  (`/ping`, `/health` 없음)를 넣어도 테스트 수정 없이 통과함을 확인 후 삭제.
- 변경분 커밋·푸시(`main`, `7e826b7`).
- `codex:rescue` 로 무결성 교차검증 → 결함 없음(아래 5절).

## 2. 수정 내용

- **`tests/test_router_discovery.py` (수정, 커밋 `7e826b7`)** — 유일한 실제 코드 변경.
  - 제거: 깨진 `isinstance(route, APIRoute)` 판별, 고정 prefix 집합 단언
    (`test_discover_routers_loads_versioned_router_modules`), 서비스별 `/health` JSON 단언
    (`test_app_exposes_health_and_versioned_routes`).
  - 추가: `test_app_boots_and_health_ok` (앱 부팅 + 앱 레벨 `/health`),
    `test_every_discovered_router_is_mounted` — `discover_routers()` 로 발견된 **모든**
    라우터의 모든 라우트가 실제 마운트돼 라우팅되는지 Starlette `route.matches()` 로 검사
    (핸들러 미호출 → FTP/OpenSearch 부작용 없음, 경로 파라미터는 더미로 치환).
    빈 결과 시 공허한 통과를 막는 `assert routers` 가드 포함.
  - 유지: `is_router_module` 단위 테스트, sample_app 기반 메커니즘 테스트 2종.
- **`docs/journals/20260625-bugs-to-fix.md` (수정)** — BUG-1 을 "오진으로 판명" 으로 정정.
  원본 분석은 경고와 함께 하단에 보존, 상단에 ✅ 결론·진짜 원인·Codex 교차검증 추가.
- `app/main.py` 는 **건드리지 않음**(라우터 자동발견 로직은 원래 정상). 디버깅 중 임시
  계측을 넣었다가 사용자 워킹트리 원본(scheduler lifespan 포함)으로 복원.

## 3. 다음 단계

- member_info 후속(BUG-1 과 무관, 기존 핸드오프대로):
  1. 실제 사무실 OpenSearch 로 `/skewnono/member_info/v1/search` 등을 호출해 인덱스/
     필드명(`PART_NAME_KO`, `RESV014`, `CENTRIC`, `WGRP_NAM`) 검증.
  2. 필요 시 office 사용자용 `member_info_client.py` SDK 추가(ftp-proxy 패턴).
  3. MCP 도구 노출 방식 결정(`fastapi-mcp` 어댑터 vs 별도 MCP 서버) — 팀 합의 필요.
- 워킹트리에 미커밋 상태로 남은 사용자 작업(`app/main.py` scheduler lifespan,
  `requirements.txt`, `app/common/scheduler/`)은 이번 세션 범위 밖 — 별도로 마무리·커밋 필요.

## 4. 메모리 업데이트

`MEMORY.md` 에 라우터 자동발견 컨벤션 1줄 추가(테스트 auto-adapt, `/health` 비강제,
`router*.py` + module-level `router=APIRouter` 만이 유일 계약).

## 5. Codex 교차검증 결과 (commit 7e826b7)

- CLAIM 1 — PASS: 발견 라우터 0개일 때 `assert routers` 로 공허한 통과 불가.
- CLAIM 2 — WARN(결함 아님): `route.matches()` 는 URL 매칭만 하고 핸들러 미호출.
  sample_app 스모크 테스트만 `TestClient` 로 실제 호출(의도된 통합 검사).
- CLAIM 3 — PASS: `app/main.py` 와 테스트가 같은 `discover_routers()` 사용 → 새
  `router*.py` 추가 시 테스트 수정 불필요(auto-adapt 성립).
- CLAIM 4 — PASS: 라우터 자동발견·마운트 회귀 없음.
- 결론: **수정 필요한 결함 없음.** 전체 스위트 67 passed.
