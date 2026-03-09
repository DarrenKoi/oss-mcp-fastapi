# FastAPI 서버 및 FTP Proxy 사용 가이드

## 목적

이 문서는 팀원이 이 저장소의 FastAPI 서버를 빠르게 띄우고, 현재 구현된 `ftp-proxy` API와 Python 클라이언트를 바로 사용할 수 있도록 정리한 실무용 가이드입니다.  
특히 `app/common/ftp_proxy/` 기준 현재 구조와 호출 방법을 중심으로 설명합니다.

## 현재 기준 위치

- FastAPI 엔트리포인트: `app/main.py`
- FTP Proxy 라우터: `app/common/ftp_proxy/router_v1.py`
- 직접 FTP 클라이언트: `app/common/ftp_proxy/ftp_direct_client.py`
- FastAPI용 어댑터: `app/common/ftp_proxy/ftp_proxy_server.py`
- HTTP 클라이언트 SDK: `app/common/ftp_proxy/ftp_proxy_client.py`
- 배치 다운로드 클라이언트: `app/common/ftp_proxy/ftp_batch_client.py`
- 서버 내부 배치 다운로더: `app/common/ftp_proxy/ftp_batch_downloader.py`

## 서버 실행

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

자동 리로드가 필요하면:

```bash
RELOAD=true python run.py
```

기동 확인:

```bash
curl http://localhost:8000/health
```

정상 응답 예시:

```json
{"status":"ok"}
```

## FTP Proxy 개요

`ftp-proxy`는 FastAPI 서버가 FTP 서버 앞단에서 목록 조회, 파일 다운로드, 파일 업로드, 다중 호스트 배치 다운로드를 대신 수행해 주는 기능입니다.

기본 흐름은 아래와 같습니다.

1. 사용자는 HTTP로 `/ftp-proxy/v1/*` 엔드포인트를 호출합니다.
2. 라우터는 `FTPProxyServer`를 생성합니다.
3. `FTPProxyServer`는 `FTPDirectClient`를 기반으로 실제 FTP 서버에 접속합니다.
4. Python 코드에서 직접 붙고 싶으면 `FTPProxyClient`, `FTPBatchClient`를 사용합니다.

## 현재 엔드포인트

| 메서드 | 경로 | 용도 |
| --- | --- | --- |
| `GET` | `/ftp-proxy/v1/list` | 원격 디렉토리 목록 조회 |
| `GET` | `/ftp-proxy/v1/download` | 단일 파일 다운로드 |
| `POST` | `/ftp-proxy/v1/upload` | 단일 파일 업로드 |
| `POST` | `/ftp-proxy/v1/batch-download` | 여러 FTP 호스트에서 같은 파일 일괄 다운로드 |
| `POST` | `/ftp-proxy/v1/batch-download/stream` | 배치 다운로드 진행 상황을 SSE로 수신 |

## 공통 파라미터

`list`, `download`, `upload`는 아래 FTP 접속 파라미터를 공통으로 사용합니다.

| 이름 | 타입 | 기본값 | 설명 |
| --- | --- | --- | --- |
| `host` | `str` | 필수 | 대상 FTP 호스트 |
| `port` | `int` | `21` | FTP 포트 |
| `user` | `str` | `anonymous` | FTP 사용자 |
| `password` | `str` | `""` | FTP 비밀번호 |
| `timeout` | `int` | `30` | 연결/응답 타임아웃 초 |
| `encoding` | `str \| null` | `null` | 서버 인코딩 강제 지정 |

`encoding`은 꼭 필요할 때만 넘깁니다.  
한글 파일명이 깨지면 대상 FTP 서버 설정에 맞춰 `utf-8`, `cp949` 등을 지정합니다.

## 1. 디렉토리 목록 조회

### 요청

`GET /ftp-proxy/v1/list`

추가 파라미터:

| 이름 | 타입 | 기본값 | 설명 |
| --- | --- | --- | --- |
| `path` | `str` | `/` | 조회할 원격 디렉토리 경로 |

### curl 예시

```bash
curl "http://localhost:8000/ftp-proxy/v1/list?host=10.10.10.15&user=fab&password=secret&path=/recipes"
```

인코딩이 필요한 경우:

```bash
curl "http://localhost:8000/ftp-proxy/v1/list?host=10.10.10.15&user=fab&password=secret&path=/recipes&encoding=cp949"
```

### 응답 형태

```json
{
  "path": "/recipes",
  "entries": [
    {
      "name": "logs",
      "permissions": null,
      "size": null,
      "date": null,
      "is_dir": true,
      "source": "mlsd"
    },
    {
      "name": "report.csv",
      "permissions": "664",
      "size": 128,
      "date": "2026-03-08 14:31:00",
      "is_dir": false,
      "source": "mlsd"
    }
  ],
  "strategy": "mlsd_path",
  "attempts": [
    {
      "strategy": "mlsd_path",
      "status": "ok",
      "entry_count": 2
    }
  ]
}
```

### 알아둘 점

- `entries`는 항상 목록 배열입니다.
- `strategy`는 실제로 어떤 방식으로 목록 조회에 성공했는지 보여줍니다.
- `attempts`에는 실패한 폴백 시도까지 남을 수 있습니다.
- 서버마다 응답 형식이 달라서 `permissions`, `date`, `facts`, `link_target` 같은 필드는 일부만 올 수 있습니다.

## 2. 파일 다운로드

### 요청

`GET /ftp-proxy/v1/download`

추가 파라미터:

| 이름 | 타입 | 기본값 | 설명 |
| --- | --- | --- | --- |
| `path` | `str` | 필수 | 다운로드할 원격 파일 경로 |

### curl 예시

```bash
curl -L \
  "http://localhost:8000/ftp-proxy/v1/download?host=10.10.10.15&user=fab&password=secret&path=/recipes/report.csv" \
  -o report.csv
```

### 동작 메모

- 응답은 `application/octet-stream`으로 내려옵니다.
- `Content-Disposition` 파일명은 요청한 경로의 마지막 파일명을 기준으로 잡힙니다.
- 다운로드 스트림 시작 전에 권한 오류나 연결 오류가 나면 `502`로 반환됩니다.

## 3. 파일 업로드

### 요청

`POST /ftp-proxy/v1/upload`

추가 파라미터:

| 이름 | 타입 | 기본값 | 설명 |
| --- | --- | --- | --- |
| `path` | `str` | 필수 | 업로드할 원격 디렉토리 |
| `file` | multipart file | 필수 | 업로드할 로컬 파일 |

중요:

- `path`는 파일 경로가 아니라 원격 디렉토리입니다.
- 실제 저장 파일명은 업로드한 multipart 파일명을 사용합니다.

### curl 예시

```bash
curl -X POST \
  "http://localhost:8000/ftp-proxy/v1/upload?host=10.10.10.15&user=fab&password=secret&path=/recipes" \
  -F "file=@./report.csv"
```

### 응답 예시

```json
{
  "status": "uploaded",
  "remote_path": "/recipes/report.csv"
}
```

## 4. 배치 다운로드

여러 FTP 호스트에서 같은 원격 파일을 한 번에 수집할 때 사용합니다.

### 요청

`POST /ftp-proxy/v1/batch-download`

본문(JSON):

| 이름 | 타입 | 기본값 | 설명 |
| --- | --- | --- | --- |
| `hosts` | `list[str]` | 필수 | 대상 FTP 호스트 목록 |
| `remote_path` | `str` | 필수 | 각 호스트에서 가져올 동일한 원격 파일 경로 |
| `base_dir` | `str` | 필수 | 로컬 저장 기준 디렉토리 |
| `port` | `int` | `21` | FTP 포트 |
| `user` | `str` | `anonymous` | FTP 사용자 |
| `password` | `str` | `""` | FTP 비밀번호 |
| `timeout` | `int` | `30` | 타임아웃 초 |
| `encoding` | `str \| null` | `null` | FTP 인코딩 |
| `max_workers` | `int` | `4` | 동시 작업 수, 서버에서 최대 `8`로 제한 |

저장 구조:

```text
{base_dir}/{host}/{filename}
```

예:

```text
/data/downloads/10.10.10.15/report.csv
/data/downloads/10.10.10.16/report.csv
```

### curl 예시

```bash
curl -X POST "http://localhost:8000/ftp-proxy/v1/batch-download" \
  -H "Content-Type: application/json" \
  -d '{
    "hosts": ["10.10.10.15", "10.10.10.16"],
    "remote_path": "/recipes/report.csv",
    "base_dir": "/tmp/ftp-batch",
    "user": "fab",
    "password": "secret",
    "max_workers": 4
  }'
```

### 응답 예시

```json
{
  "total": 2,
  "succeeded": 1,
  "failed": 1,
  "elapsed_seconds": 1.42,
  "results": [
    {
      "host": "10.10.10.15",
      "status": "success",
      "local_path": "/tmp/ftp-batch/10.10.10.15/report.csv",
      "error": null,
      "elapsed_seconds": 0.52
    },
    {
      "host": "10.10.10.16",
      "status": "failed",
      "local_path": null,
      "error": "550 File not found",
      "elapsed_seconds": 0.49
    }
  ]
}
```

## 5. 배치 다운로드 진행 상황 스트리밍

긴 배치 작업은 SSE 엔드포인트를 사용하면 호스트별 완료 이벤트를 받을 수 있습니다.

### 요청

`POST /ftp-proxy/v1/batch-download/stream`

요청 본문은 `batch-download`와 동일합니다.

### SSE 이벤트 형태

진행 이벤트:

```text
event: progress
data: {"host":"10.10.10.15","status":"success","local_path":"/tmp/ftp-batch/10.10.10.15/report.csv","error":null,"elapsed_seconds":0.52}
```

종료 이벤트:

```text
event: done
data: {"total":2,"succeeded":1,"failed":1,"elapsed_seconds":1.42}
```

## Python에서 사용하는 방법

### 1. 단일 FTP 작업: `FTPProxyClient`

`FTPProxyClient`는 비동기 HTTP 클라이언트입니다.  
즉, `await`로 호출해야 합니다.

`proxy_url`을 생략하면 `FTP_PROXY_URL` 환경 변수를 먼저 보고,
없으면 로컬 기본값 `http://127.0.0.1:8000`을 사용합니다.

```python
import asyncio

from app.common.ftp_proxy.ftp_proxy_client import FTPProxyClient


async def main():
    client = FTPProxyClient(
        "http://localhost:8000",
        "10.10.10.15",
        ftp_user="fab",
        ftp_password="secret",
        ftp_timeout=30,
        ftp_encoding="cp949",
    )

    listing = await client.list_files_response("/recipes")
    print(listing["entries"])

    await client.download("/recipes/report.csv", "/tmp/report.csv")
    await client.upload("/tmp/report.csv", "/backup")


asyncio.run(main())
```

주요 메서드:

- `await client.list_files(path="/")`
- `await client.list_files_response(path="/")`
- `await client.download(remote_path, local_path)`
- `await client.upload(local_path, remote_dir)`

### 2. 다중 호스트 작업: `FTPBatchClient`

`FTPBatchClient`도 `proxy_url`을 생략하면 같은 `FTP_PROXY_URL`
환경 변수를 사용합니다.

```python
import asyncio

from app.common.ftp_proxy.ftp_batch_client import FTPBatchClient


async def main():
    client = FTPBatchClient(
        "http://localhost:8000",
        user="fab",
        password="secret",
        timeout=30,
        encoding="cp949",
    )

    summary = await client.batch_download(
        ["10.10.10.15", "10.10.10.16"],
        "/recipes/report.csv",
        "/tmp/ftp-batch",
        max_workers=4,
    )
    print(summary)


asyncio.run(main())
```

진행 이벤트가 필요하면:

```python
import asyncio

from app.common.ftp_proxy.ftp_batch_client import FTPBatchClient


async def on_progress(event: dict) -> None:
    print("progress:", event)


async def main():
    client = FTPBatchClient("http://localhost:8000")
    summary = await client.batch_download_stream(
        ["10.10.10.15", "10.10.10.16"],
        "/recipes/report.csv",
        "/tmp/ftp-batch",
        on_progress=on_progress,
    )
    print("done:", summary)


asyncio.run(main())
```

## 언제 무엇을 써야 하나

- 브라우저, curl, Postman, 외부 시스템 연동이면 `/ftp-proxy/v1/*` HTTP 엔드포인트를 사용합니다.
- FastAPI 서버를 이미 띄운 상태에서 Python 코드로 붙을 때는 `FTPProxyClient`를 사용합니다.
- 여러 FTP 장비에서 같은 파일을 모을 때는 `FTPBatchClient` 또는 `/ftp-proxy/v1/batch-download*`를 사용합니다.
- 서버 내부 구현을 고칠 때만 `FTPDirectClient`, `FTPProxyServer`, `FTPBatchDownloader`를 직접 다룹니다.

## 오류 처리 기준

- FTP 연결 실패, 인증 실패, 권한 오류 등은 라우터에서 기본적으로 `502`로 감싸서 반환합니다.
- 목록 조회 응답의 `attempts`를 보면 어떤 전략이 실패했는지 추적할 수 있습니다.
- 파일명이 깨지면 `encoding`을 먼저 확인합니다.
- 응답 속도가 너무 느리면 `timeout`, 대상 FTP 서버 상태, `max_workers` 설정을 같이 봅니다.

## 보안 및 운영 주의사항

- FTP 계정과 비밀번호를 코드에 하드코딩하지 않습니다.
- 샘플 문서나 로그에 실제 사내 FTP 비밀번호를 남기지 않습니다.
- 배치 다운로드의 `base_dir`는 충분한 디스크 공간이 있는 경로로 지정합니다.
- `max_workers`를 무작정 크게 올리지 않습니다. 현재 서버는 최대 `8`까지만 허용합니다.
- 한글 경로나 오래된 FTP 서버를 다룰 때는 인코딩 설정 차이로 결과가 달라질 수 있습니다.

## 라우터 구조 규칙

`ftp-proxy` 외의 새 라우터를 추가할 때는 현재 서버 규칙도 같이 지킵니다.

- `app/main.py`는 `app/` 아래에서 파일명이 `router`로 시작하는 모듈을 자동 등록합니다.
- `router.py`, `router_v1.py`, `router_v2.py`처럼 파일명을 맞춥니다.
- 각 라우터는 자기 자신이 담당하는 전체 prefix를 직접 선언합니다.
- 예외적인 파일명만 `app/main.py`의 `MANUAL_ROUTER_MODULES`에 수동 등록합니다.

예:

```python
router = APIRouter(prefix="/ftp-proxy/v1", tags=["FTP Proxy"])
```

## 최소 확인 절차

1. 서버가 정상 기동되는지 확인합니다.
2. `GET /health`가 `200`을 반환하는지 확인합니다.
3. `GET /ftp-proxy/v1/list`를 한 번 호출해 접속과 목록 조회가 되는지 확인합니다.
4. 필요하면 `download`, `upload`, `batch-download`를 실제 대상 또는 테스트 FTP로 검증합니다.
5. 변경 후에는 이 문서와 관련 팀 공지를 같이 갱신합니다.
