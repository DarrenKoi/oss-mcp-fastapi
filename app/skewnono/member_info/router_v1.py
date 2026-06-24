"""member_info 검색 API (v1).

가이드 규칙대로 라우터는 얇게 두고, 실제 일은 MemberInfoServer 가 한다. 엔드포인트마다
operation_id/summary/description 을 또렷이 달아 두는데, 이게 곧 LLM 이 읽는 '도구 설명'이
된다 — 나중에 fastapi-mcp 같은 어댑터로 이 FastAPI 앱을 감싸면 각 엔드포인트가 그대로
MCP 도구로 노출된다.

서버 인스턴스는 get_server() 의존성으로 주입한다. 운영에서는 환경 변수로 만든 단일
인스턴스를 재사용하고, 테스트에서는 app.dependency_overrides 로 가짜 client 를 끼운
MemberInfoServer 를 주입해 실제 OpenSearch 없이 검증한다(OFFICE.md: mock-first).
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.skewnono.member_info.member_info_server import MemberInfoServer

router = APIRouter(
    prefix="/skewnono/member_info/v1",
    tags=["SKEWNONO member_info"],
)

_server: MemberInfoServer | None = None


def get_server() -> MemberInfoServer:
    # 환경 변수로 만든 단일 인스턴스를 재사용한다(요청마다 재접속 금지). opensearch-py
    # 연결 풀은 스레드 안전하므로 동시 요청에서 공유해도 된다.
    global _server
    if _server is None:
        _server = MemberInfoServer()
    return _server


@router.get("/health")
def health() -> dict[str, str]:
    return {"service": "skewnono", "module": "member_info", "version": "v1", "status": "ok"}


@router.get(
    "/search",
    operation_id="member_info_search",
    summary="직원 통합 검색(이름·부서·파트·직무·담당업무)",
    description=(
        "한 칸에 단어를 넣어 직원을 찾는 구글식 통합 검색. 단어는 공백·쉼표로 나뉘고 "
        "한국어 형태소 분석(nori)을 거친다. 어떤 사람을 막연히 찾을 때 먼저 쓴다. "
        "match_all=true(기본)는 모든 단어 필요(AND), false 는 하나만 맞아도 됨(OR). "
        "phrase=true 는 'CG6300' 같은 장비 코드를 정확히 매칭한다."
    ),
)
def member_info_search(
    q: str = Query(..., description="검색어. 예) 'VeritySEM 청주', '결함 분석'"),
    match_all: bool = Query(True, description="모든 단어 필요(AND). false 면 OR."),
    phrase: bool = Query(False, description="장비 코드 등 정확 구문 매칭."),
    size: int = Query(10, ge=1, description="돌려줄 인원 수(서버에서 최대 50)."),
    server: MemberInfoServer = Depends(get_server),
):
    try:
        members = server.search_members(q, match_all=match_all, phrase=phrase, size=size)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenSearch error: {e}")
    return {"count": len(members), "members": members}


@router.get(
    "/filter",
    operation_id="member_info_filter",
    summary="조건(부서·캠퍼스·근무형태·레벨 등)으로 직원 좁히기",
    description=(
        "정확히 아는 조건들로 좁혀 직원을 찾는다. facet(dept/part/campus/work_place/"
        "work_group/level)은 모두 정확 일치이며 서로 AND 로 묶인다. 준 것만 적용된다. "
        "text 를 함께 주면 통합 검색과 조합되고, 비우면 facet 만으로 거른다. "
        "'청주 캠퍼스의 계측기술팀 교대근무자'처럼 조건이 분명할 때 쓴다."
    ),
)
def member_info_filter(
    text: str | None = Query(None, description="통합 검색어(선택). 비우면 facet 만으로 거름."),
    dept: str | None = Query(None, description="부서명 정확히. 예) '계측기술팀'"),
    part: str | None = Query(None, description="파트명 정확히."),
    campus: str | None = Query(None, description="근무 캠퍼스(CENTRIC). 예) '청주'"),
    work_place: str | None = Query(None, description="근무 위치(PLACE_OF_WORK)."),
    work_group: str | None = Query(None, description="근무 형태(WGRP_NAM). 예) '교대 근무'"),
    level: str | None = Query(None, description="직원 레벨(RESV014) 코드."),
    match_all: bool = Query(True, description="text 가 있을 때 AND/OR. find 와 동일."),
    phrase: bool = Query(False, description="text 정확 구문 매칭."),
    size: int = Query(20, ge=1, description="돌려줄 인원 수(서버에서 최대 50)."),
    server: MemberInfoServer = Depends(get_server),
):
    try:
        members = server.filter_members(
            text=text,
            dept=dept,
            part=part,
            campus=campus,
            work_place=work_place,
            work_group=work_group,
            level=level,
            match_all=match_all,
            phrase=phrase,
            size=size,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenSearch error: {e}")
    return {"count": len(members), "members": members}


@router.get(
    "/member/{emp_no}",
    operation_id="member_info_lookup",
    summary="사번(EMP_NO)으로 한 명 정확 조회",
    description=(
        "사번을 이미 아는 경우의 가장 빠른 길(검색이 아니라 _id 단일 조회). "
        "해당 사번이 없으면 found=false 를 돌려준다. 이름으로 찾을 때는 /search 를 쓴다."
    ),
)
def member_info_lookup(
    emp_no: str,
    server: MemberInfoServer = Depends(get_server),
):
    try:
        member = server.get_member(emp_no)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenSearch error: {e}")
    if member is None:
        return {"found": False, "member": None}
    return {"found": True, "member": member}
