# member_info MCP 어댑터 연결

- 날짜: 2026-06-30 10:13:30
- 커밋: `2f95c37` Mount fastapi-mcp adapter exposing member_info as MCP tools
- 선행 저널: `docs/journals/20260625-member-info-mcp-handoff.md` (이번 작업의 준비 단계)

## 1. 진행 사항

- **"member_info mcp 잘 설정됐나?" 질문 진단**: `app/skewnono/member_info/` 모듈을 살펴
  실제 MCP 서버는 아직 없고, REST 엔드포인트만 *MCP-ready* 상태임을 확인.
  - `member_info_server.py`의 `MemberInfoServer` (search/filter/lookup, OpenSearch, env 기반 설정, client 주입 가능)
  - `router_v1.py`의 세 엔드포인트가 또렷한 `operation_id` + `description`을 갖고 있음 (MCP 도구 설명으로 쓰일 메타데이터)
  - `requirements.txt`에 mcp 라이브러리 없음, `app/main.py`에 MCP 트랜스포트 mount 없음
  - `app/mcp/router_v1.py`는 `/mcp/v1/health` 스텁일 뿐 실제 MCP 서버 아님
  - 앱 타이틀이 "Internal MCP FastAPI Server"였지만 실제 MCP 프로토콜 계층은 부재
- **fastapi-mcp 0.4.0 도입 결정 및 검증**: context7로 최신 API 확인 (`FastApiMCP(app)` + `mount_http()`,
  `include_operations`/`include_tags` 필터). venv에 설치해 `mount_http`, `include_operations` 시그니처 직접 확인.
- **MCP 어댑터 연결 및 노출 범위 큐레이션**: 처음엔 `include_tags=["SKEWNONO member_info"]`로 했으나
  같은 라우터의 `/health` 스텁까지 4번째 도구로 새어 들어옴(LLM 컨텍스트 낭비). `include_operations`
  명시 화이트리스트로 전환해 의도한 3개 도구만 노출.
- **검증**: 전체 테스트 67개 통과(라우터 자동탐색 테스트 영향 없음 — MCP mount는 `router*` 모듈이 아닌
  앱 레벨), uvicorn 기동 정상, `/mcp`로 MCP `initialize` 핸드셰이크 성공
  (`serverInfo: "Internal MCP FastAPI Server"`, tools capability 광고됨, 3개 도구만 등록).
- **커밋 & 푸시**: 검증 통과 후 자동 커밋 정책에 따라 `main`에 푸시.

## 2. 수정 내용

- `app/main.py`
  - `from fastapi_mcp import FastApiMCP` import 추가
  - `MCP_INCLUDE_OPERATIONS` 튜플 추가 (`member_info_search`, `member_info_filter`, `member_info_lookup`)
  - 라우터 include 루프 **뒤**에 `FastApiMCP(app, name=..., include_operations=...)` 생성 후 `mcp.mount_http()` 호출
    (FastApiMCP는 OpenAPI 스키마를 읽으므로 라우터 등록 이후에 만들어야 도구가 잡힘)
- `requirements.txt`
  - `fastapi-mcp>=0.4.0` 추가

## 3. 노출된 MCP 도구

| 도구 (operation_id) | 엔드포인트 |
|---|---|
| `member_info_search` | `GET /skewnono/member_info/v1/search` |
| `member_info_filter` | `GET /skewnono/member_info/v1/filter` |
| `member_info_lookup` | `GET /skewnono/member_info/v1/member/{emp_no}` |

MCP HTTP 트랜스포트 경로: `/mcp`

## 4. 다음 단계

아래는 후보일 뿐, 진행 전 사용자 확인 필요:

- **노출 범위 정책 확정**: 현재는 operation_id 명시 화이트리스트(큐레이션 우선). 향후 `SKEWNONO member_info`
  태그 기반 auto-join을 원하면 `include_tags`로 전환 + health 엔드포인트에 별도 operation_id 부여 후
  `exclude_operations` 처리 필요. 어느 정책을 표준으로 할지 결정.
- **인증**: 사내망 전용이지만 fastapi-mcp의 `auth_config`로 MCP mount에 인증을 걸지 여부.
- **다른 서비스 노출 여부**: 다른 패키지 엔드포인트도 MCP 도구로 낼지.
- **MCP 도구 테스트 추가**: `/mcp` initialize / tools/list 응답을 검증하는 테스트를 테스트 스위트에 넣을지.
- **`app/mcp/router_v1.py` 스텁 정리**: 이름이 혼동을 줄 수 있어 정리/제거 검토.

## 5. 메모리 업데이트

`MEMORY.md`에 다음을 반영함 (새 아키텍처 패턴 — MCP 노출 계층 추가):

- member_info 모듈이 fastapi-mcp로 실제 MCP 도구화됨 (`/mcp` HTTP 트랜스포트)
- 노출 범위는 `app/main.py`의 `MCP_INCLUDE_OPERATIONS` operation_id 화이트리스트로 제어
- FastApiMCP 생성은 라우터 include 이후에 위치해야 함
