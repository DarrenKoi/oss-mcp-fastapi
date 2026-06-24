# 고쳐야 할 버그 (2026-06-25)

member_info 모듈을 옮겨 심는 과정에서 발견한, **member_info 와 무관한 선재 버그**를
정리한다. 새 세션에서 여기부터 처리하면 된다. 자세한 맥락은
`20260625-member-info-mcp-handoff.md` 참고.

---

## BUG-1 (심각) — 실서버가 `/health` 외 라우터를 하나도 등록하지 않음

### 증상
`uvicorn app.main:app` 으로 띄운 전역 `app` 에 라우트가 `/health` 하나뿐이다. ftp-proxy,
oss, skewnono 등 자동 등록되어야 할 모든 라우터가 빠져 있다. 즉 지금 실서버는 사실상
헬스체크만 응답한다.

테스트로는 `tests/test_router_discovery.py::test_app_exposes_health_and_versioned_routes`
가 이 때문에 실패한다.

### 재현
```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -c "from app.main import app; from fastapi.routing import APIRoute; \
print(sorted(r.path for r in app.routes if isinstance(r, APIRoute)))"
# 기대: 여러 prefix(/ftp-proxy/v1/list, /oss/v1/health, ...)
# 실제: ['/health']
```

### 핵심 증거 (모순처럼 보이는 부분)
같은 프로세스 안에서:
- 전역 `app` 의 라우트 = `['/health']`  ← import 시점에 등록된 결과
- 그런데 `discover_routers()` 를 **직접 호출하면 8개 prefix 를 전부 정상 반환**한다
  (member_info 포함).
- 각 `router*` 모듈을 개별 `import_module()` 하면 **전부 성공**한다.

즉 발견 로직(`discover_routers`) 자체는 멀쩡하다. **문제는 `app/main.py` 가 import 되는
바로 그 순간(top-level `for` 루프 실행 시점)에만 발견 결과가 비어 나온다는 것.**

HEAD 의 커밋된 `app/main.py` 로도 동일하게 재현된다(워킹트리의 로컬 수정과 무관).

### 유력한 원인 (확인 필요)
`pkgutil.walk_packages` 는 **`onerror` 를 주지 않으면 하위 패키지 import 중 발생한
`ImportError` 를 조용히 삼키고 그 서브트리를 건너뛴다**(파이썬 표준 동작; ImportError 만
무시, 그 외 예외는 전파).

`app/main.py` 는 top-level 에서 다음을 한다:
```python
app = FastAPI(..., lifespan=lifespan)
for router in discover_routers():     # ← import 도중(app.main 이 아직 부분 초기화 상태)에 실행
    app.include_router(router)
```
이 `for` 가 도는 시점에 `app.main` 은 **아직 sys.modules 에 '미완성' 상태로 올라가 있다.**
`walk_packages` 가 하위 패키지를 import 하며 재귀하다가 (직접 또는 전이적으로) 절반만
초기화된 `app.main` 을 다시 건드리면 `ImportError` 가 나고, walk_packages 가 그걸 삼켜
해당 서브트리를 통째로 누락한다. app.main 초기화가 끝난 뒤에 같은 walk 를 호출하면
정상이라, "직접 호출은 되고 import 시점은 빈다"는 모순이 설명된다.

### 확인 절차 (원인 못 박기)
`discover_router_module_names` 의 `walk_packages` 호출에 `onerror` 를 임시로 달아 무엇이
삼켜지는지 본다:
```python
walk_packages(search_paths, prefix=f"{search_package_name}.",
              onerror=lambda name: print("WALK ERROR:", name))
```
import 시점에 어떤 모듈에서 에러가 찍히는지 확인하면 원인이 확정된다.

### 권장 수정 (택1, 위 확인 후 결정)
1. **등록을 import 부작용에서 분리** — `create_app()` 팩토리로 감싸 app 객체 생성과 라우터
   등록을 함수 안에서 수행하고, top-level 에서는 `app = create_app()` 한 줄만 둔다. 함수
   본문은 `app.main` 초기화가 끝난 맥락에서 호출되므로 부분 초기화 문제를 피한다.
   (uvicorn 은 `app.main:app` 또는 `--factory app.main:create_app` 로 가리키게.)
2. `walk_packages(..., onerror=...)` 로 에러를 **표면화**해 더는 조용히 누락되지 않게 하고,
   동시에 등록 루프를 `lifespan` 시작 시점 등 완전 초기화 이후로 옮긴다.
3. 최소 변경으로 막고 싶으면, 등록 로직을 별도 함수 `register_routers(app)` 로 빼고
   `if __name__ ...` 가 아니라 명시적 호출 지점(완전 초기화 후)에서 한 번만 부른다.

어느 쪽이든 **회귀 방지로 `test_app_exposes_health_and_versioned_routes` 가 통과해야 한다.**

### 영향 범위
- member_info 코드는 이 버그와 무관하다(직접 발견·import 모두 성공). **건드릴 필요 없음.**
- 단, 이 버그가 살아 있는 한 `/skewnono/member_info/v1/*` 도 실서버에서 안 뜬다.
  member_info 검증을 실제 엔드포인트로 하려면 BUG-1 을 먼저 고쳐야 한다.

---

## 참고 — 환경 관련 (버그는 아님)

- 이 저장소엔 동작하는 가상환경이 없었다. 기존 `.venv` 는 Python 3.14 에 의존성이 하나도
  안 깔려 있어(apscheduler 조차 없음) 테스트 수집 단계에서 import 에러가 난다.
  `python3.11 -m venv .venv && pip install -r requirements.txt pytest` 로 다시 만들면 된다.
- 워킹트리에 미커밋 상태인 `app/main.py` 수정(scheduler lifespan)과 untracked
  `app/common/scheduler/` 가 있다(사용자 기존 작업). BUG-1 은 그와 별개다.
