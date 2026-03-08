# FTP Proxy 디렉토리 리스팅 견고성 개선

**날짜**: 2026-03-08

## 배경

fab FTP 서버들이 서로 다른 응답 형식을 사용하기 때문에, 디렉토리 리스팅 코드의 견고성을 심층 리뷰하고 발견된 문제점들을 수정함.

## 발견된 문제 및 수정 내역

### Critical 수정

| 문제 | 설명 | 수정 내용 |
|------|------|----------|
| 심볼릭 링크 이름 파싱 오류 | UNIX `ls -l` 출력에서 `link -> target`이 파일명으로 포함됨 | `_parse_list_line`에서 `l` 퍼미션일 때 ` -> ` 기준으로 분리, `link_target` 필드 추가 |
| 빈 결과 조기 반환 | MLSD가 빈 결과를 반환하면 실제 파일이 있어도 빈 리스트 반환 | 빈 결과는 후보로 저장하고 다음 전략 계속 시도, 비어 있지 않은 결과 우선 |
| 연결 타임아웃 없음 | 도달 불가능한 호스트에서 무한 대기 가능 | `timeout` 파라미터 추가 (기본 30초), `FTP.connect()`에 전달 |
| NLST N+1 쿼리 문제 | 각 NLST 항목마다 MLST 시도 → 대량 파일 시 매우 느림 | 첫 MLST 실패 시 나머지 항목에 대해 MLST 건너뛰기 |

### Moderate 수정

| 문제 | 설명 | 수정 내용 |
|------|------|----------|
| 인코딩 미설정 | `ftplib` 기본 latin-1 → 한글 파일명 깨짐 | `ftp.encoding = "utf-8"` 설정 |
| UNIX 정규식 ACL 미지원 | SELinux/POSIX ACL의 `+`, `.`, `@` 문자 매칭 불가 | 퍼미션 패턴에 `[+.@]?` 추가 |
| Windows 날짜 형식 제한 | `/` 구분자, AM/PM 앞 공백 미처리 | 정규식에 `[-/]` 구분자, `\s?` 선택적 공백 추가 |
| upload STOR 경로 중복 | CWD 후 절대경로로 STOR 호출 | `STOR {filename}`으로 변경 (CWD 후 파일명만 사용) |
| 전략 낭비 | `mlsd_path` 실패 후 `mlsd_cwd`도 반드시 시도 | "not supported" 류 에러 감지 시 MLSD 전략 전체 건너뛰기 |

## 변경 파일

- `app/common/ftp_proxy/ftp_proxy_server.py` — 상기 모든 수정 적용

## 검증

- 기존 테스트 4건 모두 통과 (`tests/test_ftp_proxy_listing_home.py`)
  - MLSD 정상 동작
  - UNIX LIST 폴백
  - Windows LIST 폴백
  - NLST + MLST 메타데이터 폴백
