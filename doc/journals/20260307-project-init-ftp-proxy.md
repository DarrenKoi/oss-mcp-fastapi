# 2026-03-07: 프로젝트 초기 셋업 및 FTP Proxy 구현

## 1. 진행 사항

- GitHub 리포지토리 생성 (`DarrenKoi/oss-mcp-fastapi`, public)
- Git 초기화 및 `origin` 리모트 연결 (SSH 프로토콜)
- FastAPI 프로젝트 스캐폴딩 구성
- FTP Proxy 모듈 구현 (`app/common/ftp_proxy/`)
- API 라우터에 `/v1` 버전 프리픽스 적용
- `doc/journals/` 디렉토리 생성 및 FTP Proxy 개발 저널 작성

## 2. 수정 내용

### 새로 생성된 파일
- `.gitignore` — Python 기본 제외 패턴
- `requirements.txt` — fastapi, uvicorn, gunicorn, python-multipart
- `app/__init__.py`
- `app/main.py` — FastAPI 앱 엔트리포인트, 헬스체크 엔드포인트, v1 라우터 등록
- `app/common/__init__.py`
- `app/common/ftp_proxy/__init__.py`
- `app/common/ftp_proxy/ftp_client.py` — `ftplib` 기반 FTP 연결 컨텍스트 매니저, `list_dir()`, `download_stream()`, `upload_file()` 함수
- `app/common/ftp_proxy/router.py` — 3개 API 엔드포인트 (`/v1/ftp-proxy/list`, `/v1/ftp-proxy/download`, `/v1/ftp-proxy/upload`)
- `doc/journals/ftp_proxy.md` — FTP Proxy 모듈 개발 기록

### 수정된 파일
- `app/main.py` — `include_router`에 `prefix="/v1"` 추가

## 3. 다음 단계

- 가상환경(venv) 셋업 및 의존성 설치
- FTP 서버 대상 실제 연동 테스트
- 스케줄러를 통한 백그라운드 태스크 기능 추가
- 추가 웹 애플리케이션 모듈 개발 (사용자 요구사항에 따라)

## 4. 메모리 업데이트

신규 프로젝트이므로 MEMORY.md 초기 작성 진행.
