"""member_info 직원 디렉터리 검색 모듈.

OpenSearch 의 `member_info` 인덱스(EMP_NO 키, nori 분석 통합 검색)를 LLM/RAG 가 도구처럼
부를 수 있도록 FastAPI 엔드포인트로 노출한다. 실제 검색 로직은 `member_info_server.py`
의 `MemberInfoServer` 가 담당하고, `router_v1.py` 는 얇은 라우터로 그 위에 얹힌다.
"""
