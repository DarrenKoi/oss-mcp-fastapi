# Flask Web Server 내장형 FTP Proxy 제작 가이드

## 목적

이 문서는 `app/common/ftp_proxy/` 의 현재 아이디어를 바탕으로, 다른 LLM이 Flask 서버 안에 FTP proxy 기능을 내장해서 구현할 때 따라야 할 설계 기준을 정리한 문서다.

이번 문서의 목표는 일반적인 "Flask로 FTP API 만들기"가 아니다. 목표는 아래와 같다.

- FTP proxy 기능이 별도 서버가 아니라 실행 중인 Flask 웹 서버의 일부로 동작해야 한다.
- 사용자 코드에서는 Windows 와 Linux 를 구분해서 다른 클래스를 직접 호출하지 않아야 한다.
- 사용자 코드는 항상 같은 함수 이름과 같은 반환 구조를 사용해야 한다.
- Windows 에서는 Flask 서버의 FTP proxy 기능을 사용하고, Linux 에서는 직접 FTP 접속을 사용해야 한다.
- 두 경로 모두 최대한 같은 내부 FTP 동작과 같은 결과 계약을 공유해야 한다.

즉, 핵심은 Flask blueprint 기반 proxy 기능과 direct FTP client 를 따로 만드는 것이 아니라, 둘을 같은 사용자 경험으로 묶는 것이다.

## 먼저 고정해야 할 최종 그림

이 기능은 아래처럼 동작해야 한다.

1. Flask 웹 서버가 실행 중이다.
2. 그 서버 안에 `ftp_proxy` blueprint 가 등록되어 있다.
3. Windows 환경의 사용자 코드는 FTP 서버에 직접 붙지 않고, Flask 서버의 `/ftp-proxy/v1/*` 엔드포인트를 호출한다.
4. Linux 환경의 사용자 코드는 FTP 서버에 직접 붙는다.
5. 하지만 사용자 코드는 어느 쪽이든 같은 인터페이스를 사용한다.

따라서 구현은 아래 세 부분으로 나누는 것이 가장 안정적이다.

## 추천 3분할 구조

### 1. Shared FTP Core

공통 계약과 공통 FTP 로직을 둔다.

- 경로 정규화
- 공통 응답 모델
- 공통 예외 모델
- 직접 FTP 통신 구현
- 목록 조회 폴백 전략

이 부분이 가장 중요하다. direct 모드와 proxy 모드가 같은 결과를 내야 한다면, 실제 FTP 처리 규칙은 여기서 하나로 관리되어야 한다.

### 2. Flask Web Server Feature

실행 중인 Flask 앱에 blueprint 로 붙는 FTP proxy 기능이다.

- `Blueprint("ftp_proxy", ...)`
- `/ftp-proxy/v1/list`
- `/ftp-proxy/v1/download`
- `/ftp-proxy/v1/upload`
- 필요 시 `/ftp-proxy/v1/remove`
- 필요 시 batch / SSE

중요한 점은 이 blueprint 가 FTP 로직을 새로 구현하면 안 된다는 것이다. 반드시 Shared FTP Core 를 호출하는 HTTP 어댑터여야 한다.

### 3. Unified Client Layer

사용자 코드가 실제로 import 해서 쓰는 계층이다.

- `FTPProxyClient`
- `DirectFTPAsyncAdapter` 또는 direct facade
- `get_ftp_client()` 또는 `create_ftp_client()`

이 계층이 `platform.system()` 을 단 한 곳에서만 판단해야 한다.

즉, 사용자 코드는 이렇게만 써야 한다.

```python
client = get_ftp_client(...)
files = await client.list_files("/data")
await client.download("/data/a.txt", "/tmp/a.txt")
await client.upload("/tmp/a.txt", "/data")
await client.remove("/data/a.txt")
```

사용자 코드는 이 client 가 proxy 인지 direct 인지 몰라야 한다.

## 가장 중요한 설계 원칙

### 1. Flask proxy 기능은 별도 앱이 아니라 기존 웹 서버의 일부여야 한다

하지 말아야 할 것:

- FTP proxy 전용 Flask 앱을 따로 띄우는 것
- 메인 웹 서버와 FTP proxy 서버를 다른 프로세스로 분리하는 것
- 운영 시 "웹 서버 + FTP proxy 서버" 두 개를 항상 같이 띄우게 만드는 것

해야 할 것:

- 기존 Flask app factory 또는 초기화 지점에서 blueprint 를 등록한다
- 기존 설정, 로깅, 인증 체계를 가능한 한 재사용한다
- FTP proxy 는 웹 서버가 제공하는 한 기능으로 넣는다

예시:

```python
def create_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(ftp_proxy_bp)
    return app
```

이렇게 해야 Windows 환경에서는 그냥 "기존 웹 서버의 FTP 기능"을 쓰는 구조가 된다.

### 2. direct 와 proxy 는 같은 공통 계약을 따라야 한다

같은 함수 이름만 맞추는 것으로는 부족하다. 아래도 같아야 한다.

- 인자 구조
- 반환 구조
- 경로 정규화 규칙
- 예외 종류
- 성공/실패 의미

예를 들어 direct client 가 `ftplib` 예외를 그대로 던지고, proxy client 가 `HTTPStatusError` 를 던지면 사용자 경험은 같지 않다.

따라서 공통 프로토콜과 공통 예외를 먼저 정의해야 한다.

## 공통 인터페이스를 먼저 정의한다

다른 구현보다 먼저, 사용자 코드가 의존할 인터페이스를 고정해라.

권장 public surface:

```python
from pathlib import Path
from typing import Protocol, Any


class FTPClientProtocol(Protocol):
    async def list_files(self, path: str = "/") -> list[dict[str, Any]]: ...
    async def list_files_response(self, path: str = "/") -> dict[str, Any]: ...
    async def download(self, remote_path: str, local_path: str) -> Path: ...
    async def upload(self, local_path: str, remote_dir: str) -> dict[str, Any]: ...
    async def remove(self, remote_path: str) -> dict[str, Any]: ...
```

중요:

- public surface 는 async 하나로 통일하는 편이 좋다
- direct FTP 구현이 blocking 이어도 `asyncio.to_thread()` 로 감싸면 된다
- proxy client 는 원래 HTTP 호출이 async 이므로 같은 surface 에 잘 맞는다

이렇게 하면 Windows 와 Linux 모두 같은 `await client.method(...)` 형태를 쓸 수 있다.

## 공통 반환 구조도 먼저 고정한다

### 목록 조회

```json
{
  "path": "/data",
  "entries": [
    {
      "name": "a.txt",
      "permissions": "664",
      "size": 128,
      "date": "2026-03-09 09:00:00",
      "is_dir": false,
      "source": "mlsd"
    }
  ],
  "strategy": "mlsd_path",
  "attempts": []
}
```

### 업로드

```json
{
  "status": "uploaded",
  "remote_path": "/data/a.txt"
}
```

### 삭제

```json
{
  "status": "removed",
  "remote_path": "/data/a.txt"
}
```

### 실패

실패도 가능하면 공통 예외로 맞춘다.

예:

- `FTPClientError`
- `FTPAuthenticationError`
- `FTPNotFoundError`
- `FTPTransportError`

proxy client 는 HTTP 오류를 이 예외로 다시 변환하고, direct client 는 `ftplib` 오류를 같은 예외 계층으로 변환해야 한다.

## Part 1. Shared FTP Core 설계

이 부분은 direct 모드와 proxy 모드가 같이 써야 하는 공통 기반이다.

권장 파일 구성:

```text
app/common/ftp_proxy/
  ftp_path.py
  ftp_models.py
  ftp_errors.py
  ftp_client_protocol.py
  ftp_client_base.py
  ftp_direct_client.py
  ftp_direct_async_adapter.py
  ftp_proxy_client.py
  ftp_client_factory.py
  ftp_proxy_server.py
  router_v1.py
```

현재 저장소 구조와도 크게 어긋나지 않는다.

### 1-1. 경로 유틸리티는 반드시 분리한다

최소 함수:

- `normalize_remote_path(path, default="/")`
- `is_remote_absolute(path)`
- `join_remote_path(base_dir, raw_name)`
- `remote_basename(path, default="")`

반드시 유지해야 할 규칙:

- `\` 는 `/` 로 통일
- `C:\A\B` 같은 Windows 경로도 FTP 원격 경로로 해석 가능해야 함
- `C:` 는 `C:/` 로 정규화
- 빈 값은 기본값으로 치환
- basename 추출 시 디렉토리와 드라이브 루트 예외를 안전하게 처리

이 부분은 proxy/direct 결과 일치를 위해 필수다.

### 1-2. 목록 조회 폴백 전략은 공통 코어에만 둔다

실제 FTP 서버는 매우 제각각이다. 현재 구현의 가장 실무적인 부분은 목록 조회 폴백이다.

권장 순서:

1. `mlsd(path)`
2. `cwd(path)` 후 `mlsd()`
3. `cwd(path)` 후 `LIST`
4. `LIST path`
5. `cwd(path)` 후 `NLST`
6. `NLST path`

반드시 남겨야 하는 메타데이터:

- `strategy`
- `attempts`
- 실패 에러 문자열
- 성공 entry 수

이 로직은 Flask blueprint 안에 넣지 말고 `FTPDirectClient` 안에 둬야 한다.

이유:

- Linux direct 모드와 server-side proxy 모드가 같은 결과를 내야 하기 때문이다
- FTP 서버별 편차 대응을 한 군데서만 유지해야 한다

### 1-3. LIST 파서는 Unix 와 Windows 형식을 둘 다 지원한다

반드시 고려할 것:

- Unix 권한 문자열 파싱
- Windows `<DIR>` 형식 파싱
- `.` / `..` 제외
- 심볼릭 링크면 `link_target` 복원
- 파싱 실패 라인도 raw 로 보존

즉, 정보가 애매해도 항목을 버리지 말고 최대한 복원한다.

### 1-4. NLST 보강도 공통 코어에 둔다

`NLST` 는 이름만 주기 때문에 그대로 반환하면 정보가 부족하다. 현재 구현처럼 아래를 섞어 보강해야 한다.

- 가능하면 `MLST path`
- `MLST` 명령 미지원 여부를 연결 단위로 캐시
- `cwd(path)` 가능 여부로 디렉토리 판단
- `size(path)` 시도로 파일 크기 추정

이걸 공통 코어에서 처리해야 proxy/direct 결과가 최대한 일치한다.

### 1-5. download 는 스트리밍, upload 는 basename 정리

download:

- `TYPE I`
- `transfercmd("RETR ...")`
- `recv(8192)` 반복
- 전체 파일을 메모리에 올리지 않음

upload:

- 입력 `remote_dir`
- 입력 파일명은 basename 으로 정리
- `cwd(remote_dir)`
- `STOR filename`

이 규칙도 direct 와 proxy 가 공통으로 써야 한다.

### 1-6. remove 는 처음부터 공통 surface 에 포함해라

현재 코드에는 remove 가 없지만, 사용자 요구에는 포함되어 있다. 따라서 문서 단계에서부터 넣는 것이 맞다.

다만 주의할 점:

- FTP 에서 파일 삭제는 `delete()`
- 디렉토리 삭제는 `rmd()`

따라서 public method 를 `remove(remote_path)` 로 두더라도 내부 구현은 분기해야 한다.

권장 방법:

1. 가능하면 `MLST` 나 목록 정보를 통해 대상이 파일인지 디렉토리인지 확인
2. 파일이면 `delete`
3. 디렉토리면 `rmd`
4. 성공 시 동일한 응답 구조 반환

디렉토리 재귀 삭제까지 필요하면 `remove()` 에 무리하게 몰지 말고 별도 옵션 또는 별도 메서드로 분리하는 편이 낫다.

## Part 2. Flask Web Server Feature 설계

이 부분은 "실행 중인 Flask 서버 안에 들어가는 FTP proxy 기능"이다.

핵심은 HTTP 라우터가 FTP 처리를 직접 하지 않고, Shared FTP Core 를 호출한다는 점이다.

### 2-1. Blueprint 로 구현한다

예시:

```python
ftp_proxy_bp = Blueprint("ftp_proxy", __name__, url_prefix="/ftp-proxy/v1")
```

기존 Flask 앱 초기화 코드에서 등록한다.

하지 말아야 할 것:

- `if __name__ == "__main__"` 형태로 FTP proxy 전용 앱 실행 스크립트를 만드는 것
- web server 와 FTP proxy 를 별도 배포 단위로 보는 것

### 2-2. Blueprint 의 책임은 HTTP 어댑터 역할로 제한한다

라우터가 해야 할 일:

- query/body/form/multipart 파싱
- 기본값 적용
- 타입 검증
- `FTPProxyServer` 또는 공통 서비스 생성
- 공통 서비스 호출
- JSON/stream 응답 반환
- 예외를 공통 HTTP 오류로 변환

라우터가 하면 안 되는 일:

- FTP 폴백 전략 구현
- LIST 파싱
- FTP 연결 수명주기 관리 상세 구현
- 파일 저장 규칙의 핵심 결정

### 2-3. 서버용 어댑터를 둔다

권장 클래스:

- `FTPProxyServer`

역할:

- `FTPDirectClient` 를 감싸거나 상속해서 서버 로그를 추가
- 목록/다운로드/업로드/삭제의 시작, 성공, 실패를 기록
- 다운로드 전송 바이트 수 기록
- 업로드 파일 크기 기록

중요:

- Flask 라우터 안에서 로그 문자열을 조립하지 말고 서버 어댑터에서 통일한다

### 2-4. download 엔드포인트는 첫 청크를 먼저 확인한다

이 동작은 꼭 유지해야 한다.

문제:

- HTTP 스트리밍 응답은 헤더를 먼저 보내면 이후 JSON 오류로 바꾸기 어렵다

해결:

1. FTP download generator 생성
2. 첫 청크를 미리 `next()` 해서 확인
3. 이 단계에서 FTP 오류가 나면 아직 응답을 시작하지 않았으므로 정상적인 HTTP 오류를 반환
4. 성공하면 첫 청크 + 나머지 청크를 잇는 wrapper generator 로 Flask `Response` 생성

Flask 예시 개념:

```python
gen = server.download_stream(remote_path)
first_chunk = next(gen, None)

def body():
    if first_chunk is not None:
        yield first_chunk
    for chunk in gen:
        yield chunk
```

필요하면 `stream_with_context()` 를 함께 쓴다.

### 2-5. HTTP 엔드포인트는 공통 계약 중심으로 설계한다

최소 엔드포인트:

- `GET /ftp-proxy/v1/list`
- `GET /ftp-proxy/v1/download`
- `POST /ftp-proxy/v1/upload`
- `DELETE /ftp-proxy/v1/file`

삭제는 `DELETE /file?path=...` 같이 명시적으로 두는 편이 깔끔하다.

주의:

- 외부 HTTP 계약은 proxy 전용이지만, 결과 구조는 direct client 의 반환 구조와 맞아야 한다
- proxy client 는 HTTP 응답을 다시 공통 결과 형태로 정규화해야 한다

### 2-6. batch 와 SSE 는 base interface 와 분리해서 생각한다

배치 다운로드와 SSE 는 매우 유용하지만, 모든 사용자가 항상 공통으로 써야 하는 핵심 FTP 메서드는 아니다.

따라서 권장 방침은 아래와 같다.

- `list_files`, `download`, `upload`, `remove` 는 base `FTPClientProtocol` 에 넣는다
- `batch_download`, `batch_download_stream` 는 별도 확장 인터페이스 또는 proxy 전용 부가 기능으로 둔다

이렇게 해야 Linux direct 모드와 Windows proxy 모드의 공통 surface 를 무리하게 비대하게 만들지 않는다.

## Part 3. Unified Client Layer 설계

이 부분이 사용자 경험을 결정한다.

### 3-1. 사용자 코드는 factory 하나만 사용해야 한다

권장 함수:

- `get_ftp_client(...)`
- 또는 `create_ftp_client(...)`

이 함수가 아래를 결정한다.

- `platform.system() == "Windows"` 이면 `FTPProxyClient`
- `platform.system() == "Linux"` 이면 `DirectFTPAsyncAdapter`

중요:

- `platform.system()` 분기는 반드시 이 함수 안에만 둔다
- 비즈니스 코드 곳곳에 `if Windows` 를 흩뿌리지 않는다

예시:

```python
import platform


def get_ftp_client(...):
    system = platform.system()
    if system == "Windows":
        return FTPProxyClient(...)
    if system == "Linux":
        return DirectFTPAsyncAdapter(...)
    raise RuntimeError(f"Unsupported platform: {system}")
```

### 3-2. override 수단을 하나 두는 편이 좋다

사용자 요구는 Windows -> proxy, Linux -> direct 이지만, 실무에서는 테스트와 장애 대응 때문에 override 수단이 있으면 좋다.

권장:

- `FTP_CLIENT_MODE=proxy|direct`
- 설정이 있으면 platform 판단보다 우선

예:

```python
mode = os.getenv("FTP_CLIENT_MODE")
if mode == "proxy":
    ...
elif mode == "direct":
    ...
else:
    system = platform.system()
```

이건 기본 동작을 바꾸려는 것이 아니라, 테스트와 운영을 덜 위험하게 만들기 위한 안전장치다.

### 3-3. proxy client 와 direct client 는 같은 메서드명을 가져야 한다

예:

- `list_files`
- `list_files_response`
- `download`
- `upload`
- `remove`

그리고 반환값도 같아야 한다.

즉, direct client 는 `Path` 를 반환하는데 proxy client 는 dict 를 반환하면 안 된다. 같은 메서드는 같은 타입을 돌려줘야 한다.

### 3-4. proxy client 는 서버 응답을 다시 정규화한다

이건 현재 `FTPListResponseNormalizer` 가 하는 역할과 비슷하다.

이유:

- 서버 응답 키가 조금 바뀌더라도 사용자 코드가 깨지지 않게 하기 위해
- `entries/files/items/listing/data` 같은 차이를 흡수하기 위해
- path / strategy / attempts 를 공통 구조로 맞추기 위해

즉, proxy client 는 단순 HTTP wrapper 가 아니라 "공통 계약 보정 계층" 이어야 한다.

### 3-5. Linux direct 모드도 async surface 로 감싼다

`ftplib` 는 blocking 이다. 하지만 public interface 를 async 로 고정했다면 direct 모드도 async adapter 로 감싸야 한다.

권장:

- `FTPDirectClient` 는 sync 핵심 구현
- `DirectFTPAsyncAdapter` 는 `asyncio.to_thread()` 로 감싼 async facade

이렇게 하면 proxy client 와 direct client 가 같은 사용법을 갖게 된다.

## 추천 구현 순서

이 순서대로 만드는 것이 가장 안전하다.

1. 공통 응답 모델과 공통 예외를 정의한다
2. `FTPClientProtocol` 을 정의한다
3. `ftp_path.py` 의 경로 유틸리티를 작성한다
4. `FTPDirectClient` 에 목록 조회, 다운로드, 업로드, 삭제를 구현한다
5. 목록 조회 폴백과 LIST/NLST 보강을 넣는다
6. `DirectFTPAsyncAdapter` 를 만들어 public async surface 를 맞춘다
7. `FTPProxyServer` 를 만들어 서버 로그/전송량 기록을 얹는다
8. Flask blueprint 로 list/download/upload/remove 엔드포인트를 만든다
9. `FTPProxyClient` 를 만들어 HTTP 응답을 공통 계약으로 정규화한다
10. `get_ftp_client()` 를 만들어 Windows/Linux 선택을 한 곳에 모은다
11. 필요하면 batch/SSE 를 proxy feature 의 부가 기능으로 추가한다
12. Windows 와 Linux 에서 같은 호출 코드가 동작하는지 검증한다

## 기능별 세부 고려사항

### 목록 조회

반드시 고려할 것:

- 서버별 명령 지원 차이
- Unix / Windows LIST 형식 차이
- 빈 목록과 진짜 실패의 구분
- `attempts` 메타데이터 보존

중요한 판단:

- 결과 일치성을 위해 direct 와 proxy 는 같은 `FTPDirectClient` 코어를 공유해야 한다
- proxy route 가 별도 구현을 가지면 언젠가 direct 와 결과가 갈라진다

### 다운로드

반드시 고려할 것:

- 전체 파일 메모리 적재 금지
- 바이너리 모드 전환
- 첫 청크 사전 점검
- `Content-Disposition` 파일명 설정
- 중간 오류 시 로그에 transferred bytes 남기기

### 업로드

반드시 고려할 것:

- `path` 는 원격 디렉토리로 해석
- 실제 파일명은 basename 정리 후 사용
- 업로드 후 `remote_path` 반환
- 업로드 파일명에 로컬 절대 경로가 들어와도 basename 으로 안전하게 정리

### 삭제

반드시 고려할 것:

- 파일/디렉토리 삭제 명령 차이
- 삭제 전 대상 타입 판단 전략
- 같은 응답 구조 유지
- 삭제 실패 시 공통 예외 변환

### batch / SSE

판단 기준:

- 운영상 필요하면 proxy feature 에 넣는다
- 기본 공통 FTP 인터페이스에는 넣지 않는 편이 낫다

이유:

- Windows / Linux 공통 surface 를 불필요하게 복잡하게 만들지 않기 위해
- 핵심 기능과 운영 편의 기능을 분리하기 위해

## Flask 쪽에서 특히 주의할 점

### 1. 입력 검증을 직접 해야 한다

FastAPI 와 달리 Flask 는 query/body validation 을 기본 제공하지 않는다. 따라서 아래는 직접 검증해야 한다.

- `host` 필수 여부
- `path` 필수 여부
- `port` 정수 여부
- `timeout >= 1`
- multipart `file` 존재 여부

### 2. 스트리밍과 request context

Flask 스트리밍 응답에서는 `stream_with_context()` 를 검토해야 한다.

### 3. blueprint 는 stateless 하게 유지한다

요청마다 FTP client 를 새로 만들고 닫아야 한다. 연결 객체를 blueprint 전역 상태로 들고 있으면 안 된다.

## 로깅 기준

server-side 와 client-side 모두 로그가 필요하다.

권장 로그 필드:

- `target=host:port`
- `path` 또는 `remote_path`
- `filename`
- `entries`
- `strategy`
- `file_size`
- `transferred_bytes`
- `elapsed_seconds`

로그에 남기면 안 되는 것:

- FTP 비밀번호
- 파일 내용
- 민감한 원문 데이터

추가 권장:

- server logger 와 client logger 를 분리
- 로그 파일 경로와 로그 레벨을 환경 변수로 오버라이드 가능하게 설계

## 다른 LLM에게 넘길 구현 요구사항 템플릿

아래 요구사항을 주면 이번 문서의 방향대로 구현시키기 좋다.

```text
Implement an FTP feature for an existing Flask web server.

Architecture requirements:
- The FTP proxy must run as part of the Flask web server by registering a Blueprint.
- Do not build a separate FTP proxy app or process.
- Split the code into three logical parts:
  1) shared FTP core
  2) Flask blueprint-based FTP proxy feature
  3) unified client layer with runtime backend selection

Behavior requirements:
- Users must call the same method names and receive the same result shapes in both environments.
- On Windows, the unified client must use the Flask FTP proxy over HTTP.
- On Linux, the unified client must connect directly to the remote FTP server.
- The platform decision must happen in one factory function only.

Public client contract:
- async list_files(path="/")
- async list_files_response(path="/")
- async download(remote_path, local_path)
- async upload(local_path, remote_dir)
- async remove(remote_path)

Implementation requirements:
- Reuse the same shared FTP core for both Linux direct mode and server-side proxy mode.
- Normalize remote paths consistently, including Windows drive-style paths.
- Implement FTP list fallback in this order:
  1) MLSD with path
  2) MLSD after cwd
  3) LIST after cwd
  4) LIST with path
  5) NLST after cwd
  6) NLST with path
- Preserve strategy and attempts metadata in list responses.
- Stream downloads in chunks and prime the first chunk before starting the HTTP response.
- Sanitize upload filenames with basename logic.
- Add remove support with correct file vs directory handling.
- Convert direct FTP errors and proxy HTTP errors into the same custom exception hierarchy.

Optional:
- Add batch download and SSE progress as proxy-specific extensions, not as required methods of the base client protocol.
```

## 수동 검증 체크리스트

### 공통 인터페이스 검증

1. 같은 사용자 코드가 Windows 와 Linux 에서 모두 동작하는지
2. `get_ftp_client()` 외부에는 `platform.system()` 분기가 없는지
3. direct / proxy 모두 같은 메서드명을 제공하는지
4. direct / proxy 모두 같은 반환 구조를 돌려주는지

### Flask feature 검증

1. FTP proxy 가 별도 앱이 아니라 기존 Flask 앱 blueprint 로 등록되는지
2. `/ftp-proxy/v1/list` 가 정상 응답을 주는지
3. `/ftp-proxy/v1/download` 가 첫 청크 사전 점검을 하는지
4. `/ftp-proxy/v1/upload` 가 basename 규칙을 지키는지
5. `/ftp-proxy/v1/file` 삭제가 파일/디렉토리 구분을 올바르게 하는지

### FTP 동작 검증

1. `MLSD` 미지원 서버에서도 `LIST` 또는 `NLST` 폴백으로 목록 조회가 되는지
2. 큰 파일 다운로드 시 메모리 급증 없이 동작하는지
3. 업로드/삭제 후 반환 구조가 direct 와 proxy 에서 같은지
4. 실패 시 direct 와 proxy 가 같은 공통 예외 계층으로 보이는지

## 결론

이번 설계의 핵심은 "Windows 에서는 proxy, Linux 에서는 direct" 가 아니라, 그 차이를 사용자 코드에서 보이지 않게 만드는 것이다.

그 목표를 달성하려면 아래 세 가지를 반드시 지켜야 한다.

- FTP proxy 는 기존 Flask 웹 서버의 blueprint 기능으로 넣는다
- 실제 FTP 동작은 shared core 에서 한 번만 구현한다
- 사용자 코드는 unified client factory 하나만 사용한다

이 세 가지가 지켜지면, Windows 는 웹 서버의 FTP proxy 도움을 받고 Linux 는 직접 FTP 에 붙더라도, 사용자 코드는 같은 함수 이름과 같은 결과를 계속 사용할 수 있다.
