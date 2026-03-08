# FTP Proxy 심층 리뷰 및 리팩토링 검토

**날짜**: 2026-03-08

## 1. 진행 사항

### FTP Proxy 디렉토리 리스팅 코드 심층 리뷰
- `app/common/ftp_proxy/` 전체 코드 리뷰 수행
- 다양한 FTP 서버 응답 형식 대응 관점에서 견고성(robustness) 분석
- Critical 4건, Moderate 5건, Minor 3건의 문제점 식별

### 견고성 수정 구현 (`ftp_proxy_server.py`)
- 심볼릭 링크 이름 파싱: `_parse_list_line`에서 `l` 퍼미션 시 ` -> ` 기준 분리, `link_target` 필드 추가
- 빈 결과 가드: 빈 MLSD 결과 조기 반환 방지, `first_empty` 패턴으로 다음 전략 계속 시도
- 연결 타임아웃: `timeout` 파라미터 추가 (기본 30초)
- NLST N+1 최적화: `mlst_available` 플래그로 첫 MLST 실패 시 나머지 항목 건너뛰기
- UTF-8 인코딩: `ftp.encoding = "utf-8"` 설정
- UNIX 정규식 ACL 지원: `[+.@]?` 추가
- Windows 날짜 형식 확장: `[-/]` 구분자, `\s?` AM/PM 공백 허용
- Upload STOR 경로 수정: CWD 후 파일명만 사용
- 전략 건너뛰기: `_is_command_not_supported` 헬퍼로 MLSD 미지원 감지 시 `skip_mlsd` 적용
- 테스트 4건 통과 확인

### 사용자 커밋 리뷰 (`07b2c31`)
- 사용자가 별도로 대규모 리팩토링 커밋 수행 → 리뷰 요청
- 3-클래스 계층 구조로 재설계:
  - `FTPListResponseNormalizer` (`ftp_client_base.py`) — 응답 정규화 믹스인
  - `FTPDirectClient` (`ftp_direct_client.py`) — 핵심 FTP 로직 (492줄)
  - `FTPProxyServer` (`ftp_proxy_server.py`) — 얇은 어댑터 (18줄)
  - `FTPProxyClient` (`ftp_proxy_client.py`) — HTTP SDK, `FTPListResponseNormalizer` 상속
- 테스트 인프라 분리: `tests/ftp_fakes.py`에 `FakeFTP`, `FakeTransferSocket` 추출
- 9개 파일 변경, +1105/-618줄

### 커밋 리뷰에서 발견한 이슈
1. `_normalize_path`와 `_display_name`에서 `.strip()` 누락 — 공백 포함 경로 미처리
2. `_try_mlst` 빈 facts 시 `(None, False)` 반환 — MLST를 너무 공격적으로 비활성화
3. `FTPProxyServer.upload` vs `FTPDirectClient.upload` 시그니처 불일치 (LSP 위반)
4. 인코딩 opt-in 방식 전환 — 기본값 latin-1 유지 (의도적, 하위 호환성)
5. `skip_mlsd` 최적화 의도적 제거 — `MLSD /path` 실패해도 `MLSD` (CWD 후)는 성공하는 서버 지원
6. 테스트 미비: 심볼릭 링크, ACL, Windows 포맷 변형, 빈 결과 가드

## 2. 수정 내용

### 내가 수정한 파일 (이후 사용자 커밋으로 대체됨)
- `app/common/ftp_proxy/ftp_proxy_server.py` — 견고성 수정 9건 적용

### 사용자 커밋에서 변경된 파일 (리뷰 대상)
- `app/common/ftp_proxy/ftp_client_base.py` — 신규, 응답 정규화 클래스
- `app/common/ftp_proxy/ftp_direct_client.py` — 신규, 핵심 FTP 클라이언트
- `app/common/ftp_proxy/ftp_proxy_server.py` — `FTPDirectClient` 상속 어댑터로 축소
- `app/common/ftp_proxy/ftp_proxy_client.py` — `FTPListResponseNormalizer` 상속으로 리팩토링
- `app/common/ftp_proxy/router_v1.py` — `timeout`, `encoding` 쿼리 파라미터 추가
- `tests/ftp_fakes.py` — 신규, 테스트 FakeFTP 인프라 분리
- `tests/test_ftp_direct_client_home.py` — 신규, 직접 클라이언트 테스트 3건
- `tests/test_ftp_proxy_client_home.py` — 신규, 프록시 클라이언트 테스트 4건
- `tests/test_ftp_proxy_listing_home.py` — 기존 테스트 리팩토링 + 신규 2건 추가

### 저널 생성
- `doc/journals/ftp-proxy/20260308-ftp-proxy-robustness-fixes.md` — 첫 번째 수정 내역 저널

## 3. 다음 단계

- `_normalize_path`, `_display_name`에 `.strip()` 복원
- `_try_mlst` 빈 facts 처리 정책 재검토 (`(None, True)` vs `(None, False)`)
- 테스트 추가: 심볼릭 링크 파싱, ACL 퍼미션, Windows 포맷 변형, 빈 결과 가드 시나리오
- `FTPProxyServer.upload` 시그니처 LSP 위반 해소 검토

## 4. 메모리 업데이트

FTP 프록시 모듈 아키텍처가 크게 변경되었으므로 MEMORY.md 업데이트 필요.
