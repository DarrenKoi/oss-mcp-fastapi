# Flask FTP Proxy Server 제작 가이드

## 목적

이 문서는 `app/common/ftp_proxy/` 구현을 기준으로, 다른 LLM이나 개발자가 같은 성격의 FTP Proxy Server를 Flask로 다시 만들 때 따라야 할 설계 기준을 정리한 문서다.

핵심은 단순히 `ftplib`를 Flask 라우터에 붙이는 것이 아니라, 실제 FTP 서버별 편차를 견디고, 스트리밍/배치/경로 정규화/로그까지 포함한 실무형 프록시를 만드는 것이다.

## 먼저 이해해야 할 현재 구조

현재 구현은 아래처럼 역할이 분리되어 있다.

- `ftp_path.py`
  - 원격 경로 정규화, basename 추출, 경로 결합 담당
- `ftp_direct_client.py`
  - 실제 FTP 서버와 직접 통신하는 핵심 로직
  - 목록 조회, 다운로드, 업로드, async wrapper 포함
- `ftp_proxy_server.py`
  - 서버용 로깅과 응답 친화 동작을 덧씌운 어댑터
- `router_v1.py`
  - HTTP 엔드포인트 정의
  - 다운로드 스트림 사전 점검, 업로드/배치/SSE 노출
- `ftp_batch_downloader.py`
  - 여러 호스트 병렬 다운로드
- `ftp_proxy_client.py`, `ftp_batch_client.py`
  - HTTP 프록시를 호출하는 클라이언트 SDK
- `ftp_logger.py`
  - 서버/클라이언트 로그 파일 관리

Flask 버전을 만들 때도 이 역할 분리는 유지하는 편이 좋다. 라우터에서 `ftplib`를 직접 다루기 시작하면 예외 처리, 스트리밍, 재사용, 테스트가 빠르게 망가진다.

## 최종적으로 만들어야 하는 것

Flask 구현 목표를 먼저 고정해라.

1. FTP 접속 정보와 원격 경로를 받아 디렉토리 목록을 반환하는 API
2. FTP 파일을 HTTP 스트림으로 내려주는 다운로드 API
3. multipart 파일을 FTP로 올리는 업로드 API
4. 여러 FTP 호스트에서 같은 파일을 병렬로 받는 배치 다운로드 API
5. 배치 진행 상황을 SSE로 흘려주는 스트리밍 API
6. 공통 경로 처리 유틸리티
7. 공통 FTP 서비스 클래스
8. 서버 로그 체계

이 문서에서는 위 순서대로 만드는 것을 권장한다.

## 1. 경로 유틸리티부터 만든다

가장 먼저 `ftp_path.py`에 해당하는 유틸리티를 분리해서 만들어라. 이 계층을 빼먹으면 라우터와 서비스 코드 곳곳에 경로 예외 처리가 퍼진다.

최소 구현 함수:

- `normalize_remote_path(path, default="/")`
- `is_remote_absolute(path)`
- `join_remote_path(base_dir, raw_name)`
- `remote_basename(path, default="")`

반드시 고려할 점:

- Windows 스타일 경로를 받아도 `/` 기준으로 정규화해야 한다.
  - 예: `C:\\MTC\\LOG` -> `C:/MTC/LOG`
- 드라이브 루트는 일반 POSIX 경로처럼 다루면 안 된다.
  - 예: `C:` 는 `C:/` 로 보정해야 한다.
- 빈 문자열, 공백 문자열, `None` 을 받으면 기본값으로 치환해야 한다.
- FTP 서버 응답에 `folder/file.txt`, `/folder/file.txt`, `C:/folder/file.txt` 가 섞여 들어와도 basename 추출이 안정적으로 동작해야 한다.
- 경로 결합 시 이미 절대 경로인 값은 그대로 유지해야 한다.
- 업로드 파일명에는 전체 경로가 아니라 basename 만 써야 한다.

이 단계의 목적은 "모든 라우터와 서비스가 같은 경로 규칙을 쓴다"는 사실을 보장하는 것이다.

## 2. 직접 FTP 통신 계층을 만든다

다음은 Flask와 완전히 분리된 순수 Python 서비스 계층을 만든다. 현재 기준으로는 `FTPDirectClient` 가 핵심이다.

권장 클래스:

- `FTPDirectClient`

최소 메서드:

- `_create_and_login_ftp()`
- `_connect()`
- `list_files_response(path="/")`
- `download_stream(path)`
- `download(remote_path, local_path)`
- `_upload_fileobj(remote_dir, filename, file_obj)`
- `upload(local_path, remote_dir)`

여기서는 Flask 개념을 절대 섞지 마라.

### 2-1. FTP 연결 수명주기

기본 원칙:

- 요청마다 새 FTP 연결을 열고 닫는다.
- `timeout` 과 `encoding` 은 생성자에서 받는다.
- `quit()` 는 실패해도 전체 요청을 깨지 않도록 `suppress` 처리한다.

현재 구현에서 중요한 부분:

- `FTP(timeout=...)` 생성
- 필요 시 `ftp.encoding = encoding`
- `connect(host, port, timeout=timeout)`
- `login(user, password)`

이 구조를 유지해야 Flask 라우터가 stateless 하게 동작한다.

### 2-2. 목록 조회는 "한 가지 명령"으로 끝내면 안 된다

이 저장소에서 가장 중요한 포인트 중 하나다.

실제 FTP 서버는 `MLSD`, `LIST`, `NLST`, `cwd(path)` 지원 방식이 제각각이다. 그래서 목록 조회는 아래 순서처럼 여러 전략을 폴백으로 시도해야 한다.

권장 시도 순서:

1. `mlsd(path)`
2. `cwd(path)` 후 `mlsd()`
3. `cwd(path)` 후 `retrlines("LIST")`
4. `retrlines(f"LIST {path}")`
5. `cwd(path)` 후 `nlst()`
6. `nlst(path)`

각 전략마다 남겨야 하는 정보:

- 전략 이름
- 성공/실패 여부
- 성공 시 entry 개수
- 실패 시 에러 문자열

최종 응답 권장 형식:

```json
{
  "path": "/target",
  "entries": [],
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

왜 필요한가:

- 운영 중 특정 FTP 장비에서 어떤 명령이 실패하는지 바로 볼 수 있다.
- 클라이언트가 서버별 편차를 추적할 수 있다.
- "목록 조회 실패"를 재현하기 쉬워진다.

### 2-3. LIST 파서는 유닉스/윈도우 형식을 둘 다 처리해야 한다

`LIST` 결과는 표준화가 약하다. 최소한 아래 둘은 지원해라.

- Unix 스타일
  - 권한 문자열, size, month/day/time-or-year, name
- Windows 스타일
  - date, time, `<DIR>` 또는 size, name

구현 포인트:

- 정규식 두 개를 분리한다.
- `.` 과 `..` 는 제외한다.
- 심볼릭 링크라면 `name -> target` 구조를 분리해 `link_target` 을 남긴다.
- 형식을 전혀 못 알아봐도 raw line 을 살려서 항목 하나로 반환한다.

즉, 파싱 실패를 이유로 항목을 버리지 말고 최대한 복원해야 한다.

### 2-4. NLST 는 이름만 주기 때문에 추가 복원이 필요하다

`NLST` 는 파일명만 주는 경우가 많다. 그래서 그대로 응답하면 `is_dir`, `size`, `permissions` 가 비어 버린다.

현재 구현이 하는 보강:

- 가능하면 `MLST path` 로 facts 조회
- `MLST` 자체가 지원되지 않으면 이후 같은 연결에서는 반복 시도하지 않음
- `cwd(path)` 가 되면 디렉토리라고 판단
- 아니면 `size(path)` 시도로 파일 크기 추정

이걸 Flask 버전에서도 유지해야 한다. 특히 "명령 미지원 서버에서 매 항목마다 MLST 실패" 같은 낭비를 막기 위해, MLST 지원 여부를 연결 단위 플래그로 캐시하는 것이 중요하다.

### 2-5. 다운로드는 반드시 스트리밍으로 만든다

파일 전체를 메모리에 읽지 마라.

구현 순서:

1. FTP 연결
2. `TYPE I` 로 바이너리 모드 전환
3. `transfercmd(f"RETR {path}")`
4. `recv(8192)` 반복
5. 바이트 청크를 generator 로 `yield`
6. 종료 후 `voidresp()` 호출

이 구조를 쓰면 큰 파일도 메모리 사용량을 제한한 채 그대로 HTTP 응답으로 전달할 수 있다.

### 2-6. 업로드는 "원격 디렉토리"와 "저장 파일명"을 분리한다

업로드 API 설계 시 흔한 실수는 원격 경로 전체를 그냥 받는 것이다. 현재 구현은 아래처럼 나눈다.

- 입력 `path`: 원격 디렉토리
- 입력 `file.filename`: 저장 파일명 후보

처리 순서:

1. 원격 디렉토리 정규화
2. 업로드 파일명에서 basename 추출
3. `cwd(remote_dir)`
4. `storbinary(f"STOR {remote_name}", file_obj)`
5. 최종 `remote_path` 반환

이 구조가 좋은 이유:

- 디렉토리와 파일명 책임이 분리된다.
- 클라이언트가 실수로 로컬 절대 경로를 보내도 basename 으로 정리된다.
- 응답 `remote_path` 를 일관되게 만들 수 있다.

## 3. 서버 전용 어댑터 계층을 둔다

현재 `FTPProxyServer` 는 `FTPDirectClient` 를 상속하고, 서버 로그와 응답 친화 동작을 덧씌운다.

Flask 버전에서도 아래 둘 중 하나를 선택해라.

- `FTPProxyServer(FTPDirectClient)` 같은 서버 어댑터 클래스
- `FTPDirectClient` 를 감싼 composition 기반 서비스

중요한 점:

- 라우터에서 직접 로그 포맷을 만들지 말 것
- 시작/성공/실패 로그를 공통 메서드에서 남길 것
- 다운로드는 전송된 바이트 수를 누적해서 기록할 것
- 업로드는 파일 크기를 가능하면 기록할 것

권장 로그 필드:

- `target=host:port`
- `path` 또는 `remote_path`
- `filename`
- `file_size`
- `entries`
- `strategy`
- `transferred_bytes`
- `elapsed_seconds`

절대 로그에 남기면 안 되는 것:

- FTP 비밀번호
- 파일 내용
- 민감한 업무 데이터 원문

## 4. Flask 라우터는 얇게 만든다

Flask에서는 `Blueprint` 로 묶는 것이 좋다.

예시 구조:

```python
ftp_proxy_bp = Blueprint("ftp_proxy", __name__, url_prefix="/ftp-proxy/v1")
```

라우터 책임은 여기까지로 제한해라.

- 요청 파라미터 읽기
- 경로 정규화
- 서비스 객체 생성
- 서비스 호출
- HTTP 응답 포맷팅
- FTP 예외를 HTTP 502 로 변환

라우터에서 해서는 안 되는 일:

- FTP 명령 조합 판단
- LIST 파싱
- 배치 다운로드 스케줄링 세부 구현
- 로컬 파일 경로 생성 규칙 결정

## 5. 엔드포인트를 하나씩 만든다

### 5-1. `GET /ftp-proxy/v1/list`

입력:

- `host`
- `port=21`
- `user="anonymous"`
- `password=""`
- `timeout=30`
- `encoding=None`
- `path="/"`

처리:

1. `path` 정규화
2. 서비스 생성
3. `list_files_response(path)` 호출
4. JSON 반환
5. 예외 시 `502`

고려사항:

- Flask에서는 `request.args.get(...)` 로 값을 읽고 타입 변환 책임을 직접 져야 한다.
- `timeout`, `port` 는 잘못된 값이 들어오면 400 으로 처리하는 것이 좋다.

### 5-2. `GET /ftp-proxy/v1/download`

이 엔드포인트는 "스트리밍 전에 첫 청크를 미리 확인" 하는 동작이 핵심이다.

현재 FastAPI 구현의 `_prime_stream()` 이 하는 일:

- 스트림에서 첫 청크를 먼저 꺼내 본다.
- 이 시점에 권한 오류/연결 오류가 나면 아직 HTTP 응답을 시작하지 않았으므로 정상적인 `502` 를 돌려줄 수 있다.
- 첫 청크를 확보한 뒤에만 `StreamingResponse` 를 생성한다.

Flask에서도 같은 원칙을 적용해라.

권장 순서:

1. `download_stream(path)` generator 생성
2. `next(gen)` 으로 첫 청크 선조회
3. 실패하면 `502`
4. 성공하면 첫 청크 + 나머지 청크를 이어 붙이는 wrapper generator 생성
5. `Response(stream_with_context(...), mimetype="application/octet-stream")`
6. `Content-Disposition` 에 basename 설정

이 단계가 없으면 헤더를 보낸 뒤 중간에 스트림이 터져서, 클라이언트 입장에서는 "깨진 다운로드"만 보이고 오류 JSON 을 못 받는다.

### 5-3. `POST /ftp-proxy/v1/upload`

입력:

- query string 또는 form field 의 FTP 접속 정보
- 업로드 대상 원격 디렉토리 `path`
- multipart file

처리:

1. `path` 정규화
2. `request.files["file"]` 확인
3. 서비스 생성
4. 파일 스트림과 원본 파일명을 넘겨 업로드
5. `{"status": "uploaded", "remote_path": "..."}`

고려사항:

- 빈 파일명은 400 처리
- 업로드 파일명은 basename 으로 정리
- 파일 객체는 한 번만 읽는다는 전제를 지켜야 한다

## 6. 배치 다운로드는 별도 서비스로 뺀다

배치 기능을 라우터에서 직접 만들지 말고 `FTPBatchDownloader` 같은 독립 클래스로 빼라.

왜 별도 클래스로 빼야 하는가:

- Flask 라우터와 무관하게 테스트 가능
- 일반 JSON 응답 API와 SSE API가 같은 핵심 로직을 공유 가능
- 추후 Celery, RQ, APScheduler 같은 백그라운드 시스템으로 바꾸기 쉬움

권장 데이터 구조:

```python
@dataclass
class ToolDownloadResult:
    host: str
    status: Literal["success", "failed"]
    local_path: str | None = None
    error: str | None = None
    elapsed_seconds: float = 0.0


@dataclass
class BatchDownloadResult:
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    results: list[ToolDownloadResult] = field(default_factory=list)
    elapsed_seconds: float = 0.0
```

### 6-1. 저장 경로 규칙을 고정한다

현재 구현은:

- `{base_dir}/{host}/{filename}`

이 규칙을 유지하는 것이 좋다.

이유:

- 같은 파일명을 여러 호스트에서 내려받아도 충돌하지 않는다.
- 나중에 어떤 장비 파일인지 바로 식별할 수 있다.

### 6-2. 병렬 실행 수를 제한한다

현재 구현은 `max_workers` 상한을 둔다.

권장 사항:

- 기본값 4
- 상한 8 정도
- `max_workers <= 0` 은 400 또는 최소 1로 보정

이걸 두는 이유:

- 사용자가 실수로 수십 개 스레드를 열지 않게 하기 위해
- FTP 서버/사내망/프록시 서버 부하를 제어하기 위해

### 6-3. 완료 순서대로 결과를 내보낸다

현재 구현은 `as_completed()` 로 완료된 작업부터 수집한다.

이 방식의 장점:

- 느린 호스트 하나 때문에 전체 진행 상황이 멈추지 않는다.
- SSE 진행 이벤트를 즉시 보낼 수 있다.

## 7. SSE 스트리밍은 큐 + 백그라운드 스레드로 만든다

현재 `/batch-download/stream` 은 다음 구조를 쓴다.

1. 메인 요청 스레드는 SSE 응답 generator 를 돌린다.
2. 배치 다운로드는 별도 스레드에서 수행한다.
3. 각 호스트 작업이 끝날 때마다 `queue.put(result)`
4. SSE generator 가 큐에서 꺼내 `event: progress` 전송
5. 작업 종료 후 `None` sentinel 전송
6. 최종 집계는 `event: done` 으로 전송

Flask에서도 거의 같은 구조를 쓰면 된다.

권장 SSE 형식:

```text
event: progress
data: {"host":"10.0.0.1","status":"success","local_path":"/tmp/a.txt","error":null,"elapsed_seconds":1.23}

event: done
data: {"total":3,"succeeded":2,"failed":1,"elapsed_seconds":5.41}
```

고려사항:

- `mimetype="text/event-stream"`
- 가능하면 `Cache-Control: no-cache`
- reverse proxy 환경이면 buffering 비활성화 헤더도 검토
- JSON 문자열화는 항상 한 줄 `data:` 로 유지
- worker thread 종료를 `join()` 해서 누수 방지

## 8. 응답 계약을 먼저 고정하고 구현한다

다른 LLM이 Flask 버전을 만들 때 가장 많이 흔들리는 부분은 응답 구조다. 내부 구현보다 먼저 계약을 고정해라.

권장 계약:

### 목록 조회 응답

- `path`
- `entries`
- `strategy`
- `attempts`

### 다운로드 응답

- 바이너리 스트림
- `Content-Disposition`

### 업로드 응답

- `status`
- `remote_path`

### 배치 다운로드 응답

- `total`
- `succeeded`
- `failed`
- `elapsed_seconds`
- `results`

### 진행 이벤트 응답

- progress 이벤트에는 호스트 단위 결과
- done 이벤트에는 전체 요약

응답 계약이 고정되면:

- SDK 작성이 쉬워지고
- FastAPI/Flask 간 교체 비용이 줄고
- 테스트 포인트도 명확해진다

## 9. Flask에서 특별히 신경 써야 할 점

FastAPI 구현을 Flask로 옮길 때 문법보다 실행 모델 차이를 먼저 생각해라.

### 9-1. FTP I/O 는 blocking 이다

`ftplib` 는 blocking 이다. Flask에서 기본적인 sync view 를 쓰는 것은 괜찮지만, 아래를 전제해야 한다.

- 요청 하나가 연결 하나를 붙잡는다
- 큰 다운로드는 워커 하나를 오래 점유한다
- 대량 동시 다운로드가 필요하면 gunicorn worker/thread 설정까지 같이 봐야 한다

즉, Flask 버전은 "작동"보다 "배포 시 동시성 한계"까지 같이 설계해야 한다.

### 9-2. 스트리밍 응답은 context 유지가 필요하다

Flask에서는 `stream_with_context()` 를 써서 request context 문제를 피하는 편이 안전하다.

### 9-3. 입력 검증을 직접 챙겨야 한다

현재 FastAPI는 query 파라미터 타입, `timeout >= 1`, `max_workers` 범위 등을 선언형으로 다룬다.

Flask에서는 직접 해야 한다.

최소 검증 항목:

- `host` 필수
- `path` 필수인 엔드포인트 구분
- `port` 정수 여부
- `timeout >= 1`
- `max_workers` 범위 제한
- multipart `file` 존재 여부

## 10. 로그 체계를 별도 유틸로 만든다

현재 구현은 서버/클라이언트 로그를 나눠 저장하고, 최근 N개 레코드만 유지한다.

Flask 버전에서도 적어도 아래는 유지해라.

- 전용 logger name
  - 예: `ftp_proxy.server`
- 환경 변수 기반 로그 레벨
- 로그 파일 경로 환경 변수 오버라이드
- 파일 핸들러 초기화 실패 시 서비스 전체는 계속 동작

로그는 "FTP 문제 디버깅"을 위해 필수다. 특히 목록 조회 전략 실패 내역, 다운로드 전송 바이트, 배치 호스트별 실패 원인은 반드시 남겨라.

## 11. 보안과 운영 관점에서 반드시 지켜야 할 것

### 보안

- 비밀번호는 로그에 남기지 않는다
- 업로드 파일 내용이나 다운로드 내용은 로그에 남기지 않는다
- 사내 호스트명, 실 IP, 업무 파일명 노출 범위를 검토한다
- 필요하면 허용 대상 호스트 화이트리스트를 둔다

### 운영

- timeout 기본값을 둔다
- batch worker 상한을 둔다
- 매우 큰 파일 다운로드 시 reverse proxy timeout 을 검토한다
- SSE 는 중간 프록시가 끊지 않는지 확인한다
- 인코딩 문제 대응을 위해 `encoding` 오버라이드 옵션을 남긴다

## 12. 구현 순서 권장안

다른 LLM에게 실제 구현을 시킬 때는 아래 순서로 요구하는 것이 좋다.

1. `ftp_path.py` 수준의 경로 유틸리티 작성
2. `FTPDirectClient` 작성
3. `LIST` 파서와 `MLSD/LIST/NLST` 폴백 구현
4. 다운로드 스트림과 업로드 구현
5. Flask `Blueprint` 로 `list/download/upload` 엔드포인트 작성
6. 서버 로그 추가
7. `FTPBatchDownloader` 작성
8. 일반 배치 다운로드 API 작성
9. SSE 스트리밍 API 작성
10. curl 기반 수동 검증 문서화

이 순서가 좋은 이유는 핵심 FTP 기능을 먼저 고정한 뒤, HTTP 어댑터와 배치 기능을 얹기 때문이다.

## 13. 다른 LLM에게 줄 구현 요구사항 템플릿

아래 요구사항을 그대로 넘기면 비교적 안정적으로 비슷한 구조가 나온다.

```text
Create a Flask-based FTP proxy server that mirrors the behavior of app/common/ftp_proxy in this repository.

Requirements:
- Separate path utilities, direct FTP client, Flask blueprint, batch downloader, and logging utilities.
- Support list/download/upload/batch-download/batch-download-stream endpoints under /ftp-proxy/v1.
- Use ftplib for direct FTP access.
- Normalize remote paths consistently, including Windows drive-style paths.
- For directory listing, implement fallback strategies in this order:
  1) MLSD with path
  2) MLSD after cwd
  3) LIST after cwd
  4) LIST with path
  5) NLST after cwd
  6) NLST with path
- Return strategy and attempts metadata in list responses.
- Stream downloads in chunks instead of reading entire files into memory.
- Prime the first download chunk before starting the HTTP streaming response so FTP failures become HTTP errors.
- For uploads, treat the incoming path as a remote directory and sanitize the filename with basename logic.
- Implement batch download with ThreadPoolExecutor and capped max_workers.
- Implement SSE progress streaming with queue + background thread, sending progress and done events.
- Add structured logging without logging FTP passwords.
```

## 14. 수동 검증 체크리스트

구현 후 최소한 아래는 직접 확인해야 한다.

1. `/ftp-proxy/v1/list` 가 정상 서버와 제한된 서버에서 모두 동작하는지
2. `MLSD` 미지원 서버에서 `LIST` 또는 `NLST` 폴백이 살아 있는지
3. 다운로드 실패 시 깨진 파일 응답 대신 HTTP 오류가 오는지
4. 큰 파일 다운로드가 메모리 급증 없이 동작하는지
5. 업로드 후 반환된 `remote_path` 가 예상 경로인지
6. 배치 다운로드가 호스트별 디렉토리로 저장되는지
7. SSE progress 와 done 이벤트가 순서대로 오는지
8. 로그에 비밀번호가 남지 않는지

## 결론

Flask 버전 FTP Proxy Server를 만들 때 가장 중요한 것은 "FTP 서버는 제각각이라 단일 happy path 로는 운영이 안 된다"는 전제를 코드 구조에 반영하는 것이다.

따라서 구현의 중심은 Flask 문법이 아니라 아래 네 가지다.

- 경로 정규화 일관성
- 목록 조회 폴백 전략
- 안전한 스트리밍
- 배치/SSE/로그를 포함한 운영 가능성

이 네 가지를 유지하면 FastAPI가 아니라 Flask로 옮겨도 실무에서 쓸 수 있는 수준의 FTP Proxy를 만들 수 있다.
