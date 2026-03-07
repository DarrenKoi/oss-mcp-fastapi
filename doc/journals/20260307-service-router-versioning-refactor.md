## 1. 진행 사항
- `app/` 기준 서비스 분리를 시작하기 위해 `app/oss/`, `app/mcp/`, `app/skewnono/` 패키지를 추가하고 각 패키지의 `router.py`를 FastAPI 앱에 연결했다.
- `app/oss/` 아래에 `app/oss/mtc/`, `app/oss/aps/`, `app/oss/dec/`를 추가해 OSS 하위 서비스를 독립 패키지로 분리했다.
- `app/main.py`의 하드코딩 라우터 등록을 제거하고 `pkgutil.walk_packages`로 `app/**/router.py`를 재귀 탐색해 자동 등록하도록 변경했다.
- API 버저닝 전략을 suffix 방식으로 통일하기 위해 각 서비스 패키지의 `router.py`가 `v1.py`를 포함하도록 리팩터링했다.
- `app/common/ftp_proxy/ftp_proxy_client.py`의 호출 URL을 `/ftp-proxy/v1/*` 경로로 수정해 서버 라우팅과 맞췄다.
- 검증용으로 `python3 -m compileall app`, `.venv/bin/python -c 'from app.main import app; ...'`를 실행해 import 및 라우트 등록 결과를 확인했다.
- 작업 중 생성한 변경을 검증 후 커밋/푸시했고, 주요 커밋은 `85de01d`, `47be08e`, `047eb83`, `5f01e77`이다.

## 2. 수정 내용
- 엔트리포인트 변경: `app/main.py`
- 서비스 패키지 추가: `app/oss/__init__.py`, `app/mcp/__init__.py`, `app/skewnono/__init__.py`
- 서비스 라우터 추가 및 리팩터링: `app/oss/router.py`, `app/mcp/router.py`, `app/skewnono/router.py`
- OSS 하위 서비스 추가: `app/oss/mtc/__init__.py`, `app/oss/mtc/router.py`, `app/oss/mtc/v1.py`, `app/oss/aps/__init__.py`, `app/oss/aps/router.py`, `app/oss/aps/v1.py`, `app/oss/dec/__init__.py`, `app/oss/dec/router.py`, `app/oss/dec/v1.py`
- 버전 모듈 추가: `app/oss/v1.py`, `app/mcp/v1.py`, `app/skewnono/v1.py`, `app/common/ftp_proxy/v1.py`
- FTP 프록시 라우터 분리: `app/common/ftp_proxy/router.py`
- FTP 클라이언트 경로 수정: `app/common/ftp_proxy/ftp_proxy_client.py`
- 작업 지침 문서 갱신: `AGENTS.md`, `CLAUDE.md`
- 프로젝트 메모리 파일 생성: `MEMORY.md`

## 3. 다음 단계
- 없음

## 4. 메모리 업데이트
- `MEMORY.md`를 새로 생성했다.
- `app/main.py`는 `app/**/router.py`를 자동 탐색해 마운트한다는 규칙을 기록했다.
- 서비스 패키지의 `router.py`가 `v1.py`, `v2.py` 같은 버전 모듈을 조합하고 URL은 `/service/.../v1` suffix 방식으로 유지한다는 규칙을 기록했다.
- `app/oss/` 아래의 `mtc`, `aps`, `dec` 하위 서비스 구조와 FTP 클라이언트가 `/ftp-proxy/v1/*`를 따라야 한다는 점을 기록했다.
