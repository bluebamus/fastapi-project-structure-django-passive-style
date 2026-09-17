# Run Log — skeleton-purpose-audit

> 라운드별 실행 기록. 무엇을 했고, 무엇으로 확인했는지.

## Round 0 — 2026-08-25 · 문서 학습 (`f90eede`)

- **트리거:** "저장소 내부 docs 에서 문서를 학습해줘" (REQ-S01)
- **범위:** docs 44개 중 41개 전편 열람(폐기 예고된 v1.0 8종 제외). 코드 변경 0.
- **결과:** 앱 레지스트리·트랜잭션·ORM/Raw 계약 파악. 문서 불일치 4건 보고
  (reports 경로 오기 · v1.1 03·08 의 "Raw 미제공" 잔재 · PASSIVE-APP 의 폐기된 커밋 모델)

## Round 1 — 2026-08-25 · 목적 기준 검수 + 문서 정리 (`f90eede`)

- **트리거:** "이 저장소의 목적은 django 기반의 수동 app 등록, 라우터 파일로 URL 수동
  관리를 하는 프로젝트 골격 구조다. 이를 기반으로 코드를 검수하고 불필요한 문서는
  삭제하고 필요한 문서는 업데이트" (REQ-S02~S04)
- **STOP 체크포인트:** 삭제는 되돌리기 어려우므로 4개 결정을 먼저 확인받았다 —
  삭제 범위 / v1.0 처리 / PASSIVE-APP 처리 / 코드 결함 수정 여부. 전부 권장안 승인.

### A. 목적 부합 판정 — **부합**

측정으로 확인했다. 주장이 아니라 실물이다.

| 목적 요소 | 실물 | 판정 |
|---|---|---|
| 수동 app 등록 | `config.INSTALLED_APPS` 8줄이 유일한 SSOT. `main.py` 는 `create_app()` 호출뿐 | ✅ |
| 등록 = 결선 | `app/core/apps/` 674줄 (config 299 / registry 192 / wiring 115 / exceptions 33) | ✅ 얇다 |
| URL 수동 관리 | `v1/<view>.py` → `router.py`(prefix·tag 선언) → `AppConfig`(`/api`). 8개 앱 전부 동일 | ✅ |
| 자동 스캔 없음 | 디렉터리 순회 0건. route 충돌은 기동 실패 | ✅ |
| core 독립성 | `config.py`·`registry.py` 가 FastAPI·SQLAdmin·SQLAlchemy 를 import 하지 않음 | ✅ |

### B. 검수에서 나온 것 — 9건 (Fixed 8 · Accepted 1)

**S-001 이 이번 라운드의 요점이다.** 골격 생성기가 만든 앱이 이 저장소의 게이트를
통과하지 못했다. `operation_id` 가 없어 자동 생성값이 들어가고, 그 값을 OpenAPI 계약
검사가 거부한다. 태그 선언까지 없어 **검사 두 개**가 걸린다.

문서는 그것을 "생성 후 직접 붙이세요" 라는 주의사항으로 적어 두고 있었다. 골격을 받은
사람의 첫 경험이 "만들자마자 빨간불" 이라는 뜻이다 — 한 줄이면 되는 것을 문서로
떠넘긴 상태였다. 템플릿을 고치고, 태그는 중앙 파일이라 붙여 넣을 항목을 출력하게 했다.

**S-002 는 문서가 없는 기능을 있다고 말한 경우다.** `PASSIVE-APP-PROJECT-DESIGN.md` 가
"관리자용 API 는 `require_admin` Dependency 로 보호한다" 고 적었는데 그 심볼은 `app/`
전체에 0건이다. 조립 순서로 안내한 `AppRegistry.discover()` 도 존재하지 않는다.
**있는 기능을 안 적은 것보다 없는 기능을 있다고 적은 것이 나쁘다** — 전자는 발견하면
되고 후자는 그것을 전제로 설계하게 만든다.

### C. 삭제 — 15파일 / 5,840줄

| 대상 | 근거 |
|---|---|
| `docs/orm-raw-repository/2026-08-13/` 3종 | 완료된 착수 명세 (ADR-S02) |
| `DJANGO-STYLE-MANUAL-APP-INTEGRATION-PLAN.md` | 같음 — 구축이 끝났다 |
| `PRODUCTION-READINESS-DEVELOPMENT-PLAN.md` | 같음 — README 가 이미 "역사적 자료" 로 표기 |
| `docs/project-guide/v1.0/` 9종 | 존재하지 않는 세션 API 를 가르친다 (ADR-S03) |
| `docs/.gitkeep` | docs 에 파일이 있다 |

삭제 후 **참조 전수 확인**을 했다. 문서 4곳·CI 주석 5곳·테스트 1곳이 삭제 대상을
가리키고 있었고 전부 정리했다. 그 과정에서 이 저장소에 **존재한 적 없는** 인용
2건(`AUDIT_REPORT.md`·`LEDGER-1`, 형제 저장소에서 딸려온 것)도 함께 나왔다(S-006).

### D. 검증

- 게이트 `--fast` 6단계 통과 → 컨테이너 기동 후 **8단계 전부 통과** (MySQL·브라우저 포함)
- **fail-on-revert 실증(S-001):** `operation_id` 를 템플릿에서 되돌리자
  `assert 'ping_api_v1_...ping_get' == 'pingScaffoldprobe...'` 로 실패. 복구 확인.
- **검사가 내 실수를 잡았다(S-008):** 08 문서에 백틱으로 감싼 `EXPLAIN` 을 넣었더니
  환경변수 검사가 미선언 변수로 잡았다. run-log 에 기록된 `DATE_ADD` 사례와 같은
  함정이다 — 이 저장소의 검사가 헛돌지 않는다는 증거로 남긴다.

### E. 수렴 판정

`CONVERGED` — Open Fix 0. S-001~S-008 Fixed, S-009 는 골격 최소주의에 부합해 Accepted
(RS-01). 잔여 위험 5건 등재.

**하지 않은 것:** 예제 앱 축소(RS-03), CRP 이력 정리, 인증 도입. 요구 범위 밖이다.

## 심각도 추세

| Round | CRIT | HIGH | MED | LOW | 신규 | 판정 |
|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 | 4 (보고만) | — (열람 라운드) |
| 1 | 0 | 1 | 3 | 5 | 9 | **CONVERGED** (Open Fix 0) |
