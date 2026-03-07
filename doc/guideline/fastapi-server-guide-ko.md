# FastAPI 서버 사용 가이드

## 목적

이 문서는 팀원이 이 저장소의 FastAPI 서버를 사용할 때 라우터 구조를 헷갈리지 않고, 새 서비스나 새 버전을 추가할 때 기존 엔드포인트를 깨뜨리지 않도록 돕기 위한 작업 기준입니다.

## 핵심 구조

- `app/main.py`는 `app/` 아래에서 파일명이 `router`로 시작하는 모든 모듈을 자동으로 찾아서 마운트합니다.
- 라우터 파일 이름은 역할에 맞춰 명확하게 나눕니다.
  - `router.py`: 버전이 없는 공통 또는 기본 라우트
  - `router_v1.py`, `router_v2.py`: 버전별 라우트
- 각 라우터 파일은 자기 자신이 담당하는 전체 URL prefix를 직접 선언해야 합니다.
  - 예시: `APIRouter(prefix="/oss/mtc/v1", tags=["OSS MTC"])`
- `v1.py`, `v2.py`처럼 버전 번호만 있는 파일명은 사용하지 않습니다.

## 폴더 구성 예시

```text
app/
  oss/
    router_v1.py
    aps/
      router_v1.py
      router_v2.py
    mtc/
      router.py
      router_v1.py
  common/
    ftp_proxy/
      ftp_proxy_server.py
      ftp_proxy_client.py
      router_v1.py
```

## 새 라우터 추가 방법

1. 서비스 폴더를 `app/` 아래에 만듭니다.
2. 버전이 필요하면 `router_v1.py`부터 추가합니다.
3. `APIRouter`의 `prefix`에 서비스 경로와 버전을 모두 포함합니다.
4. 실제 업무 로직은 가능하면 `*_server.py` 같은 별도 서비스 클래스로 분리합니다.
5. `app/main.py`에 수동 등록 코드를 추가하지 않습니다. 자동 탐색이 처리합니다.

## 작업 규칙

- 한 파일 안에 여러 API 버전을 섞지 않습니다.
- 버전이 올라가면 기존 `router_v1.py`를 수정해서 의미를 바꾸지 말고 `router_v2.py`를 새로 만듭니다.
- 단순 라우팅 외의 FTP, 외부 시스템 연동, 파일 처리 로직은 라우터에 직접 길게 작성하지 않습니다.
- 라우터 `tags`는 서비스 이름과 맞춰 Swagger 문서에서 구분되도록 유지합니다.

## 실행 방법

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

자동 리로드가 필요하면 아래처럼 실행합니다.

```bash
RELOAD=true python run.py
```

## 최소 확인 절차

라우터를 추가하거나 구조를 바꾼 뒤에는 아래 항목을 최소한 확인합니다.

1. 서버가 예외 없이 기동되는지 확인합니다.
2. `GET /health`가 정상 응답하는지 확인합니다.
3. 새로 추가한 버전 라우트가 의도한 경로로 열리는지 확인합니다.
   - 예시: `/ftp-proxy/v1/*`, `/oss/v1/*`, `/oss/mtc/v2/*`
4. 기존 버전 경로가 그대로 유지되는지 확인합니다.
5. Swagger UI에서 태그와 경로가 중복 없이 보이는지 확인합니다.

## 자주 하는 실수

- `router_v1.py` 안에서 `prefix="/v1"`만 선언하는 경우
  - 자동 탐색은 상위 `router.py`를 반드시 거친다고 가정하지 않으므로, 전체 prefix를 직접 선언해야 합니다.
- `router.py`에서 다른 버전 라우터를 다시 `include_router()` 하는 경우
  - 자동 탐색과 중복 마운트가 생길 수 있으므로 현재 구조에서는 권장하지 않습니다.
- 새 버전을 만들면서 기존 버전 파일을 덮어쓰는 경우
  - 클라이언트 호환성이 깨질 수 있으니 버전 파일은 분리해서 유지합니다.

## 권장 작업 흐름

1. 새 기능이 기존 API와 호환되면 현재 버전 파일에 엔드포인트를 추가합니다.
2. 비호환 변경이면 `router_v2.py`를 새로 만들고 새 prefix를 부여합니다.
3. 서버 기동 확인 후 필요한 엔드포인트를 직접 호출해 검증합니다.
4. 변경 내용을 문서와 팀 공지에 함께 반영합니다.
