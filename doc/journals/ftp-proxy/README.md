# FTP Proxy 저널 정리

이 폴더는 `app/common/ftp_proxy/` 작업 기록을 모아둔 주제별 저널 폴더다.
현재 구현을 확인할 때는 아래 코드 경로를 먼저 보고, 개별 저널은 변경 이력과 의사결정 배경을 확인할 때 참고한다.

## 현재 기준 코드 경로

- `app/common/ftp_proxy/router_v1.py`
- `app/common/ftp_proxy/ftp_direct_client.py`
- `app/common/ftp_proxy/ftp_proxy_server.py`
- `app/common/ftp_proxy/ftp_proxy_client.py`
- `app/common/ftp_proxy/ftp_batch_downloader.py`
- `app/common/ftp_proxy/ftp_batch_client.py`

## 현재 엔드포인트

- `GET /ftp-proxy/v1/list`
- `GET /ftp-proxy/v1/download`
- `POST /ftp-proxy/v1/upload`
- `POST /ftp-proxy/v1/batch-download`
- `POST /ftp-proxy/v1/batch-download/stream`

## 저널 목록

- `20260307-project-init-ftp-proxy.md` - FTP Proxy 초기 구현과 프로젝트 시작 기록
- `20260308-ftp-proxy-robustness-fixes.md` - 디렉토리 리스팅 견고성 보강 기록
- `20260308-ftp-proxy-review-and-refactor.md` - 구조 분리와 리뷰 메모
- `20260308-ftp-proxy-async-mode.md` - async 전환 기록
- `20260308-ftp-batch-downloader.md` - 배치 다운로드 기능 추가 기록
- `20260308-single-url-proxy-operations-plan.md` - 단일 URL 운영 계획 메모

## 관련 문서

- `../20260307-service-router-versioning-refactor.md` - 전역 라우터 구조 개편과 `/ftp-proxy/v1/*` 경로 정리

## 정리 규칙

- FTP Proxy 관련 세션 저널은 앞으로 `doc/journals/ftp-proxy/` 아래에 저장한다.
- 여러 도메인에 걸친 문서는 루트 `doc/journals/`에 유지한다.
