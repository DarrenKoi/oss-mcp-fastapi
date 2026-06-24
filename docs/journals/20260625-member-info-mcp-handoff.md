# member_info 검색 모듈 추가 — 핸드오프 (2026-06-25)

다른 저장소(flask_modules)에서 작업하던 세션이 이 저장소로 `member_info` 직원 검색
모듈을 옮겨 심었다. 이 문서는 **이 저장소에서 새 Claude Code 세션을 띄워 이어받을 때**
필요한 맥락을 정리한 핸드오프다. (코드는 이미 추가되어 있다.)

## 무엇을, 왜

OpenSearch 의 `member_info` 인덱스(직원 디렉터리: EMP_NO 키, nori 통합 검색)를 LLM/RAG 가
도구처럼 부를 수 있게 FastAPI 엔드포인트로 노출했다. 원본 검색 로직은 flask_modules 의
`ops_store/examples/member_info_search.py` 예제에서 가져왔으나, 이 저장소는 `ops_store` 에
의존하지 않으므로 `opensearch-py` 를 직접 쓰도록 포팅했다.

## 추가/수정한 파일

- `app/skewnono/member_info/__init__.py` — 패키지 설명.
- `app/skewnono/member_info/member_info_server.py` — 서버측 서비스 클래스 `MemberInfoServer`
  (가이드의 `*_server.py` 규칙). OpenSearch 질의·정형화를 담당. **접속 정보는 하드코딩하지
  않고 `OPENSEARCH_*` 환경 변수로 받는다(OFFICE.md).** `client=` 를 주입하면 가짜 client 로
  교체 가능(mock-first).
  - `search_members(text, match_all, phrase, size)` — search_all 통합 검색(AND/OR).
  - `filter_members(text, dept, part, campus, work_place, work_group, level, ...)` — 통합 검색 +
    정확일치 facet(term filter) 조합. facet 은 모두 keyword(인덱스 dynamic template).
  - `get_member(emp_no)` — EMP_NO(_id) 단일 GET, 없으면 None.
  - 결과는 원본 응답이 아니라 `CONTEXT_FIELDS` 만 추린 평평한 레코드(전화번호·근무지 포함).
    `MAX_SIZE=50` 으로 size 상한.
- `app/skewnono/member_info/router_v1.py` — 얇은 라우터. prefix `**/skewnono/member_info/v1**`.
  - `GET /health`
  - `GET /search?q=&match_all=&phrase=&size=` → 통합 검색
  - `GET /filter?text=&dept=&part=&campus=&work_place=&work_group=&level=&...` → 조건 좁히기
  - `GET /member/{emp_no}` → 단일 조회 (`{found, member}`)
  - 엔드포인트마다 `operation_id`/`summary`/`description` 을 또렷이 달았다. 이게 곧 LLM 이 읽는
    도구 설명이라, 나중에 `fastapi-mcp` 류로 앱을 감싸면 그대로 MCP 도구로 노출된다.
  - 서버 인스턴스는 `get_server()` 의존성으로 주입(테스트에서 `app.dependency_overrides` 로 교체).
  - OpenSearch 예외는 `502` 로 감싼다(ftp-proxy 라우터와 동일한 규칙).
- `requirements.txt` — `opensearch-py>=2.4.0` 추가.
- `tests/test_skewnono_member_info_home.py` — mock-first 테스트 8개(가짜 client 주입, 실제
  클러스터 불필요). 질의 본문(must/should/filter, OR nested-bool, size cap)과 응답 정형화를 검증.
- `tests/test_router_discovery.py` — 기대 prefix 집합에 `/skewnono/member_info/v1` 추가
  (이 테스트가 prefix 집합을 정확히 단언하므로 라우터를 더하면 같이 고쳐야 한다).

## 검증 결과

```bash
# 이 저장소엔 작동하는 venv 가 없어 임시로 .venv_verify 를 만들어 검증했다(아래 정리 항목 참고).
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt pytest

pytest tests/test_skewnono_member_info_home.py -q      # 8 passed
pytest tests/test_router_discovery.py -q               # 아래 ⚠️ 한 건만 실패(선재 버그)
```

- `member_info` 테스트 8개 전부 통과.
- `test_discover_routers_loads_versioned_router_modules` 통과(새 prefix 포함 확인) —
  `discover_routers()` 는 내 라우터를 정상 발견·import 한다.

## ⚠️ 선재 버그 (내 변경과 무관, 새 세션에서 우선 확인 요망)

`tests/test_router_discovery.py::test_app_exposes_health_and_versioned_routes` 가 실패한다.
**원인은 member_info 가 아니라 라우터 자동 등록 자체다:**

- `app/main.py` 가 import 시점에 도는 `for router in discover_routers(): app.include_router(router)`
  가 **`/health` 하나만 등록**한다. 즉 실서버(`uvicorn app.main:app`)도 지금은 `/health` 외
  아무 라우터(ftp-proxy 포함)도 서빙하지 않는다.
- 반면 `discover_routers()` 를 **직접 호출하면 8개 prefix 를 모두 정상 반환**한다(내 것 포함).
  각 `router*` 모듈도 개별 import 가 전부 성공한다.
- HEAD 의 커밋된 `app/main.py` 로도 동일하게 재현된다(전역 app 라우트가 `/health` 뿐).
  따라서 이 저장소의 워킹트리에는 `app/main.py` 로컬 수정(scheduler lifespan 추가)과
  미커밋 `app/common/scheduler/` 가 있는데, 그와 별개로 **import 타임 자동 등록이 비어
  나오는 문제**가 있다.

추정 방향(미확정): `walk_packages` 가 `app.main` 자기 자신을 import 하는 도중(부분 초기화
상태)에 호출되어, 첫 walk 결과가 비는 패턴일 수 있다. 새 세션에서 `app/main.py` 의
import-타임 등록 루프를 함수로 빼서 `lifespan` 안이나 명시 호출 시점으로 옮기는 식으로
재현·수정하면 좋겠다. **member_info 코드를 건드릴 필요는 없다.**

## 다음 단계 (제안)

1. 위 ⚠️ 자동 등록 버그를 먼저 진단·수정한다(서버가 라우터를 실제로 서빙하게).
2. 실제 OpenSearch(사무실)에서 `/skewnono/member_info/v1/search` 등을 한 번 호출해
   인덱스/필드명(특히 `PART_NAME_KO`, `RESV014`, `CENTRIC`, `WGRP_NAM`)을 확인한다.
3. 필요하면 office 사용자용 Python 클라이언트 SDK(`member_info_client.py`)를 ftp-proxy
   패턴대로 추가한다(현재는 server+router 만 있음).
4. "MCP 도구"로의 실제 노출 방식을 결정한다. 현재 저장소엔 MCP 라이브러리가 없고 전부
   FastAPI 라우터다. `fastapi-mcp` 같은 어댑터로 앱 전체를 감쌀지, 별도 MCP 서버를 둘지
   팀과 합의가 필요하다(엔드포인트 메타데이터는 이미 그에 맞춰 달아 둠).

## 정리 항목

- `.venv_verify/` 는 내가 검증용으로 만든 임시 venv 다. 표준 `.venv` 로 다시 만들고
  `.venv_verify/` 는 지워도 된다(이미 삭제했을 수 있음).
- 접속 정보는 절대 커밋하지 말 것. `OPENSEARCH_HOST/PORT/USER/PASSWORD/USE_SSL/
  VERIFY_CERTS/SSL_SHOW_WARN` 환경 변수로만 주입(OFFICE.md).
