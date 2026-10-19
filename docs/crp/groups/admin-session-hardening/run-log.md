# Run Log — admin-session-hardening (라운드 로그 + 수렴 판정)

> 각 라운드가 무엇을 검사했고 심각도 추세가 어떻게 변했는지. 마지막 라운드가 `CONVERGED` 이고 이후 코드·계약이
> 안 바뀌었으면 동일 요청은 "할 일 없음".

## 라운드 기록

### Round 0 — 2026-10-19 (base SHA: `a3af9ac`) · 계획 · 조사
- **트리거:** 사용자 요청 REQ-001
- **조사(sqladmin 0.32 소스):** `Admin.__init__` 라우트 — `/logout` GET 전용, `/{identity}/delete` DELETE, `create`·`edit` GET/POST, `import` POST,
  `@action` 은 `add_route(..., methods=["GET"])`. `main.js` — 삭제·일괄 삭제는 `$.ajax({method: 'DELETE'})`, 가져오기는 `fetch(POST, FormData)`,
  사용자 정의 작업은 `window.location.href`(GET). 템플릿 로더 `ChoiceLoader([FileSystemLoader(templates_dir), PrefixLoader({"sqladmin_original": ...}), ...])`.
  `AuthenticationBackend.__init__` 만 `SessionMiddleware` 를 만든다. `itsdangerous` 소비처: 소스 0(테스트의 서명 쿠키 조작만).
- **신규 finding:** MED 3 · LOW 1(+ 사용자 결정 수용 1) → ledger F-001 ~ F-005
- **수렴 판정:** `NOT CONVERGED` (Open Fix 4)

### Round 1 — 2026-10-19 · 구현 · 검증 (`cc72ade`·`97d274f`)
- **변경:** Redis 관리 세션(저장소·미들웨어·설정), CSRF 미들웨어·POST 로그아웃·`base.html` 확장, 즉시 폐기(API·관리 화면·스크립트), 기간 필터, `itsdangerous` 제거.
- **fail-on-revert(작업 폴더 밖 복사 → 변이 → 지정 테스트 → 복원):** 1차 23개 변이 중 21개 감지, 2개(스크립트 헤더 부착 제거·필터 종료일 입력 제거)가
  살아남아 테스트를 보강(스크립트 세 갈래 문자열·`type="date" data-date-end`) — 2차에서 9개 모두 감지. 폼 본문 재생 제거는 요청이 걸려 시간 초과(감지).
- **실기동 스모크:** uvicorn(lifespan off) + SQLite + fakeredis + Chromium — 로그인 → 쿠키는 43자 세션 ID 만 → Redis 키 `admin:sess:{64hex}` →
  생성(폼 hidden 토큰) → 삭제(XHR `X-CSRF-Token`) → 기간 필터 UI(`created_at=2020-01-01~오늘`, 열린 구간 `2099-01-01~` 는 빈 목록) →
  GET 로그아웃 405 → 링크 클릭으로 POST 로그아웃(토큰) → 로그아웃 전 쿠키 사본 302(거부). 15개 확인 모두 통과. 접속 로그는 끄고 MySQL 은
  닿지 않는 주소로 둬 DB 에 붙지 않았다.
- **신규 finding:** 0 · **수렴 판정:** Open Fix 0

### Round 2 — 2026-10-19 · 감독자 정정 REQ-003 (`5a18851`)
- **변경:** `UserSessionRevoker`(refresh + 관리 세션), 관리 화면 폐기를 커밋 전 훅으로.
- **fail-on-revert:** 10개 변이 모두 감지(폐기 실패 삼킴 → 수정·삭제가 커밋되는 것을 테스트가 잡음).
- **신규 finding:** F-006 → Fixed

### Round 3 — 2026-10-19 · 감독자 정정 REQ-004 (`738a8b9`)
- **변경:** 판정 `revocation_for_change` 하나가 두 집합을 정함, 강등은 관리 세션만, 스크립트 비밀번호 변경도 refresh 폐기.
- **fail-on-revert:** 7개 변이 모두 감지. **신규 finding:** F-007 → Fixed

### Round 4 — 2026-10-19 · 감독자 최종 정정 REQ-005 (`5b2582d`)
- **확인:** `UserService.update_user` 는 base(`a3af9ac`)부터 강등 시 refresh 를 폐기했다(`test_demotion_revokes_refresh_families`). → 관리 화면도 폐기,
  고정 테스트 원복(base 대비 `app/features/user/tests/test_endpoint.py` 에 지운 줄 0).
- **fail-on-revert:** `demoted = False` → API·관리 화면 테스트 2건 동시 실패, refresh 집합에서 강등 제거 → 같은 2건 동시 실패.
- **검사(`.env` 없는 저장소 밖 클론, HEAD):** 아래 "최종 검사" 참조.
- **신규 finding:** F-008 → Fixed · **수렴 판정:** `CONVERGED` (Open Fix 0)

## 최종 검사
- 작업 트리: ruff check·format 통과, mypy(규칙 파일 방법) 222 파일 이상 없음, `pytest -m "not mysql and not browser"` 1223 passed · 36 deselected · skip 0 · xfail 0.
- `-m browser` 수집 9건 · `-m mysql` 수집 27건(로컬은 수집만 — 실행은 CI).
- 저장소 밖 클론(`.env` 없음): `scripts/review_gate.py --fast` 결과는 보고서에 적는다.
