# FTP Proxy 비동기 모드 구현

**날짜**: 2026-03-08

## 1. 진행 사항

- FTP 프록시 모듈 전체에 `asyncio.to_thread()` 기반 비동기 지원 추가
- `FTPDirectClient._connect()` 리팩토링: `_create_and_login_ftp()` 추출하여 sync/async 컨텍스트 매니저가 공유
- `FTPDirectClient`에 async 메서드 6개 추가: `_aconnect()`, `alist_files()`, `alist_files_response()`, `adownload_stream()`, `adownload()`, `aupload()`
- `FTPProxyServer`에 async 별칭 3개 추가: `alist_dir()`, `alist_dir_response()`, `aupload()`
- `router_v1.py` 엔드포인트 3개 모두 `def` → `async def` 전환
- `FTPProxyClient` 리팩토링: `_FTPProxyClientBase` 추출, `AsyncFTPProxyClient` 신규 클래스 추가
- `__init__.py`에서 `AsyncFTPProxyClient` export 추가
- 테스트 인프라 확장: `async_patch_connect()` 헬퍼, async 테스트 10개 작성
- `pytest-asyncio` 패키지 설치

## 2. 수정 내용

### 수정된 파일
| 파일 | 변경 내용 |
|------|-----------|
| `app/common/ftp_proxy/ftp_direct_client.py` | `_create_and_login_ftp()` 추출, `_aconnect()` async context manager, `alist_files()`, `alist_files_response()`, `adownload_stream()`, `adownload()`, `aupload()` 추가 |
| `app/common/ftp_proxy/ftp_proxy_server.py` | `alist_dir()`, `alist_dir_response()`, `aupload()` async 별칭 추가 |
| `app/common/ftp_proxy/router_v1.py` | 3개 엔드포인트 `async def`로 전환, async 서버 메서드 호출 |
| `app/common/ftp_proxy/ftp_proxy_client.py` | `_FTPProxyClientBase` 공통 베이스 추출, `AsyncFTPProxyClient` 클래스 추가 (`httpx.AsyncClient` 기반) |
| `app/common/ftp_proxy/__init__.py` | `AsyncFTPProxyClient` export |
| `tests/ftp_fakes.py` | `async_patch_connect()` 헬퍼 추가 |

### 신규 파일
| 파일 | 내용 |
|------|------|
| `tests/test_ftp_direct_client_async.py` | async 직접 클라이언트 + 프록시 서버 테스트 6개 |
| `tests/test_ftp_proxy_client_async.py` | async HTTP 프록시 클라이언트 테스트 4개 |

### 핵심 설계 결정
- **`asyncio.to_thread()` 채택** (aioftp 대신): ftplib은 stdlib이고 6단계 폴백 체인이 이미 검증됨. `to_thread()`는 메서드당 2-3줄로 최소 리스크. 서버 6 CPU / 기본 스레드풀 10개로 10-20 동시 다운로드에 충분
- **같은 파일에 async 메서드 배치** (별도 `_async.py` 파일 생성 안 함): thin wrapper이므로 별도 파일은 과도. 예외로 `AsyncFTPProxyClient`는 `httpx.AsyncClient` 라이프사이클이 다르므로 별도 클래스
- **`adownload_stream()` 패턴**: `to_thread(next, gen, sentinel)` — sync generator를 async generator로 변환

### 검증 결과
- 기존 sync 테스트 18개: 전부 통과 (회귀 없음)
- 신규 async 테스트 10개: 전부 통과
- 앱 임포트 정상 확인 (14개 라우트 로드)

## 3. 다음 단계

- `pytest-asyncio`를 `requirements.txt` 또는 dev dependencies에 추가 (현재 pip install만 한 상태)
- `adownload` 테스트에서 실제 async 스트리밍 다운로드 (httpx.AsyncClient.stream) 통합 테스트 고려
- 동시 다운로드 실사용 시 스레드풀 크기 튜닝 필요 여부 모니터링 (`loop.set_default_executor(ThreadPoolExecutor(max_workers=N))`)
- 커밋 및 푸시 (아직 미수행)

## 4. 메모리 업데이트

FTP 프록시 모듈 아키텍처에 async 관련 정보 추가 필요.
