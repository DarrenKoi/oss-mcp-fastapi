# 2026-03-08 FTP 배치 다운로더 구현

## 1. 진행 사항

- **요구사항 분석**: 수백 대의 fab 도구(각각 독립 FTP 서버)에서 동일 파일을 다운로드하는 배치 기능 설계
  - 동시 접속 4개 제한으로 대역폭 과부하 방지
  - `{base_dir}/{tool_ip}/{filename}` 구조로 파일 구분 (동일 파일명 덮어쓰기 방지)
- **기존 FTP 프록시 모듈 탐색**: 클래스 구조, async 패턴, 테스트 헬퍼 등 전체 아키텍처 파악
- **설계 계획 수립**: `ThreadPoolExecutor` 기반 동시성 모델, SSE 스트리밍 진행률, 별도 배치 SDK 클래스 등 결정
- **핵심 배치 다운로더 구현**: `FTPBatchDownloader` 클래스 (순수 Python, FastAPI 의존성 없음)
- **HTTP 엔드포인트 추가**: 동기 + SSE 스트리밍 2개 엔드포인트
- **배치 클라이언트 SDK 구현**: `FTPBatchClient` 클래스 (오피스 사용자용)
- **테스트 작성 및 통과**: 8개 테스트 케이스 전체 통과, 기존 48개 테스트 포함 전체 통과

## 2. 수정 내용

### 새 파일 생성

- **`app/common/ftp_proxy/ftp_batch_downloader.py`** (~105줄)
  - `ToolDownloadResult` / `BatchDownloadResult` 데이터클래스
  - `FTPBatchDownloader` 클래스: `ThreadPoolExecutor(max_workers=4)` 기반
  - `_download_one()`: 호스트별 독립 `FTPDirectClient` 생성, 예외 안전 (절대 raise 안 함)
  - `batch_download()`: `as_completed` 루프, `on_complete` 콜백 지원
  - `MAX_WORKERS_CAP = 8`로 상한 제한

- **`app/common/ftp_proxy/ftp_batch_client.py`** (~100줄)
  - `FTPBatchClient` 클래스: `FTPProxyClient`와 분리 (multi-host 특성)
  - `batch_download()`: 동기 POST → 전체 결과 반환
  - `batch_download_stream()`: SSE 스트리밍 POST → `on_progress` 콜백 + 요약 반환
  - `_http_session()` 컨텍스트 매니저 패턴 (기존 SDK와 동일)

- **`tests/test_ftp_batch_downloader.py`** (~150줄)
  - `TestBatchDownloadSuccess`: 다중 호스트 다운로드, IP별 폴더 구분
  - `TestBatchDownloadPartialFailure`: 부분 실패 시 카운트 검증
  - `TestBatchDownloadCallback`: `on_complete` 콜백 호출 검증
  - `TestBatchDownloadConcurrency`: `max_workers` 상한 제한, 동시 실행 수 추적
  - `TestBatchDownloadCredentials`: FTP 자격증명 전달 검증

### 수정된 파일

- **`app/common/ftp_proxy/router_v1.py`**
  - `BatchDownloadRequest` Pydantic 모델 추가
  - `POST /ftp-proxy/v1/batch-download` — 동기 배치 다운로드 (전체 결과 JSON 반환)
  - `POST /ftp-proxy/v1/batch-download/stream` — SSE 스트리밍 (`event: progress` 호스트별 + `event: done` 요약)
  - `_make_downloader()`, `_format_tool_result()` 헬퍼 함수

- **`tests/ftp_fakes.py`**
  - `patch_connect_multi()` 헬퍼 추가: 호스트별 다른 `FakeFTP` 인스턴스 매핑

## 3. 다음 단계

- 실제 fab 도구 환경에서 배치 다운로드 통합 테스트
- 대규모 배치(100+ 호스트) 시 메모리/성능 프로파일링
- 필요 시 다중 파일 지원 (`remote_paths: list[str]`) 확장
- SSE 스트리밍 엔드포인트 라우터 통합 테스트 추가

## 4. 메모리 업데이트

FTP 프록시 모듈에 배치 다운로더 관련 정보 추가 필요.
