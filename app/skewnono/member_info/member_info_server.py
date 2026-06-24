"""`member_info` 인덱스를 검색하는 서버측 서비스 클래스.

FastAPI 서버 안에서 도는 worker 다(가이드의 `*_server.py` 규칙). 라우터(router_v1.py)는
이 클래스를 만들어 호출만 하고, 실제 OpenSearch 질의·정형화는 여기서 한다. 검색 형태는
flask_modules 의 member_info_search 예제에서 가져왔지만, 이 저장소는 ops_store 에 의존하지
않으므로 opensearch-py 를 직접 쓴다.

접속 정보는 절대 하드코딩하지 않는다(OFFICE.md). OPENSEARCH_* 환경 변수로 받고, 집에서는
실제 클러스터 없이 가짜 client 를 주입해 mock-first 로 검증한다(테스트에서 client= 주입).

검색 설계 메모(인덱스는 ops_index_mgmt/member_info.py 가 만든다):
  - search_all : 이름·부서·파트·직무·RESP_CONT 가 모두 copy_to 되는 통합 nori 필드.
    구글식 한 칸 검색이 여기를 친다.
  - facet 필드(CENTRIC/WGRP_NAM/PLACE_OF_WORK/전화번호 등)는 인덱스에 명시 매핑이 없어
    dynamic template 로 keyword(정확일치)가 된다. search_all 에는 안 들어가므로 term
    필터로만 좁히고, 검색 결과 _source 안에서 그대로 읽어 context 로 쓴다.
  - 사용자 원문을 query_string/simple_query_string 으로 넘기지 않는다. match/match_phrase/
    term 만 써서 특수문자가 연산자로 해석되지 않게 한다.
"""

import os
from typing import Any

from opensearchpy import OpenSearch
from opensearchpy.exceptions import NotFoundError

INDEX_NAME = "member_info"
SEARCH_ALL_FIELD = "search_all"

# 정확일치(term)로 거는 facet 필드들 — 모두 keyword.
DEPT_FIELD = "DEPT_NAME_KOR"
PART_FIELD = "PART_NAME_KO"
CAMPUS_FIELD = "CENTRIC"
WORK_PLACE_FIELD = "PLACE_OF_WORK"
WORK_GROUP_FIELD = "WGRP_NAM"
LEVEL_FIELD = "RESV014"

# 검색 결과로 돌려줄 context 필드 — 원본 응답 전체가 아니라 한 사람을 설명할 만큼만 추린다.
CONTEXT_FIELDS = (
    "EMP_NO",         # 사번 (_id, 정확 조회 키)
    "NAME_KOR",       # 이름
    "RESV014",        # 직원 레벨
    "DEPT_NAME_KOR",  # 부서
    "PART_NAME_KO",   # 파트
    "JOB_NAME_KOR",   # 직무
    "RESP_CONT",      # 담당 업무(자유 서술)
    "CENTRIC",        # 근무 캠퍼스
    "PLACE_OF_WORK",  # 근무 위치
    "WGRP_NAM",       # 근무 형태(유연근무 / 교대 근무)
    "OFFICE_TEL_NO",  # 사무실 전화
    "MOBILE_TEL_NO",  # 휴대전화
)

# 한 번에 돌려주는 인원 상한 — LLM 이 큰 size 를 부르면 context 가 폭발하므로 막는다.
MAX_SIZE = 50


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def client_from_env() -> OpenSearch:
    """OPENSEARCH_* 환경 변수만으로 OpenSearch client 를 만든다(호스트 하드코딩 금지).

    여기서는 연결을 '구성'만 한다 — opensearch-py 는 실제 요청 시점에야 접속하므로 이
    함수를 불러도 클러스터가 떠 있을 필요는 없다.
    """
    host = os.environ.get("OPENSEARCH_HOST", "localhost")
    port = int(os.environ.get("OPENSEARCH_PORT", "9200"))
    user = os.environ.get("OPENSEARCH_USER")
    password = os.environ.get("OPENSEARCH_PASSWORD")
    return OpenSearch(
        hosts=[{"host": host, "port": port}],
        http_auth=(user, password) if user else None,
        use_ssl=_env_bool("OPENSEARCH_USE_SSL", False),
        verify_certs=_env_bool("OPENSEARCH_VERIFY_CERTS", False),
        ssl_show_warn=_env_bool("OPENSEARCH_SSL_SHOW_WARN", False),
    )


def _text_clauses(text: str, *, phrase: bool = False) -> list[dict[str, Any]]:
    """search_all 한 필드에 대한 '단어별' match(또는 match_phrase) 절 목록.

    text 를 공백·쉼표로 나눠 각 단어를 한 절로 만든다. phrase=True 면 match_phrase 라
    "CG6300" 같은 장비 코드의 토큰이 흩어지지 않고 붙어서 매칭된다.
    """
    query_type = "match_phrase" if phrase else "match"
    terms = [term for term in text.replace(",", " ").split() if term]
    return [{query_type: {SEARCH_ALL_FIELD: term}} for term in terms]


def _record(source: dict[str, Any]) -> dict[str, Any]:
    """한 사람의 _source 에서 context 필드만 골라 평평한 dict 로(없는 값은 생략)."""
    return {
        field: source[field]
        for field in CONTEXT_FIELDS
        if source.get(field) is not None
    }


class MemberInfoServer:
    """`member_info` 인덱스 검색을 캡슐화한다.

    client 를 주지 않으면 환경 변수로 새로 만든다(운영). 테스트에서는 가짜 client 를 주입해
    실제 클러스터 없이 질의 본문과 정형화를 검증한다.
    """

    def __init__(self, client: OpenSearch | None = None, index: str = INDEX_NAME):
        self.client = client if client is not None else client_from_env()
        self.index = index

    def _run(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        """검색 본문을 실행하고 hit 들을 context 레코드 목록으로 정형화한다."""
        response = self.client.search(index=self.index, body=body)
        return [_record(hit["_source"]) for hit in response["hits"]["hits"]]

    def search_members(
        self,
        text: str,
        *,
        match_all: bool = True,
        phrase: bool = False,
        size: int = 10,
    ) -> list[dict[str, Any]]:
        """구글식 통합 검색: search_all 한 필드에서 여러 단어를 찾는다.

        match_all=True(기본)면 모든 단어 필요(AND), False 면 하나만 맞아도 됨(OR).
        phrase=True 면 각 단어를 match_phrase 로 정확 매칭한다.
        """
        clauses = _text_clauses(text, phrase=phrase)
        key = "must" if match_all else "should"
        body = {"query": {"bool": {key: clauses}}, "size": min(size, MAX_SIZE)}
        return self._run(body)

    def filter_members(
        self,
        *,
        text: str | None = None,
        dept: str | None = None,
        part: str | None = None,
        campus: str | None = None,
        work_place: str | None = None,
        work_group: str | None = None,
        level: str | None = None,
        match_all: bool = True,
        phrase: bool = False,
        size: int = 20,
    ) -> list[dict[str, Any]]:
        """통합 검색(text)과 정확일치 facet 들을 한 질의로 조합한다.

        준 facet 만 적용되며 서로 AND(term filter)로 묶인다. text 를 비우면 facet 만으로
        거르는 순수 필터가 된다.
        """
        facets = {
            DEPT_FIELD: dept,
            PART_FIELD: part,
            CAMPUS_FIELD: campus,
            WORK_PLACE_FIELD: work_place,
            WORK_GROUP_FIELD: work_group,
            LEVEL_FIELD: level,
        }
        filter_clauses = [
            {"term": {field: value}}
            for field, value in facets.items()
            if value is not None
        ]

        bool_clause: dict[str, Any] = {}
        if filter_clauses:
            bool_clause["filter"] = filter_clauses
        if text:
            text_clauses = _text_clauses(text, phrase=phrase)
            if match_all:
                bool_clause["must"] = text_clauses  # 모든 단어 필요(AND)
            else:
                # OR 는 nested bool(should 만)로 감싸 must 에 넣는다. should 를 filter 와 같은
                # 층에 두면 minimum_should_match 가 1→0 으로 풀려 '하나 이상 맞아야 함'이
                # 사라지고 facet 만으로 다 통과해 버리는 게 OpenSearch 의 함정이다.
                bool_clause["must"] = [{"bool": {"should": text_clauses}}]

        body = {"query": {"bool": bool_clause}, "size": min(size, MAX_SIZE)}
        return self._run(body)

    def get_member(self, emp_no: str) -> dict[str, Any] | None:
        """EMP_NO(=_id)로 한 명을 정확 조회한다. 없는 사번이면 None.

        검색이 아니라 _id 단일 GET 이라 가장 빠르다. emp_no 는 적재 때 _id 를 만든 방식과
        맞추려 str 로 변환한다.
        """
        try:
            response = self.client.get(index=self.index, id=str(emp_no))
        except NotFoundError:
            return None
        return _record(response["_source"])
