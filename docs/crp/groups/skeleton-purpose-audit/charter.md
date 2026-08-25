# Charter — skeleton-purpose-audit (Charter v0.1 / 2026-08-25)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항과 불가침 제약(INV-S1~S5).

## 1. 인벤토리 (Scope Inventory)

| 영역 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 앱 registry | `app/core/apps/{config,registry,wiring,exceptions}.py` · `config.py` | 소스 | **검수 대상** — 목적의 심장부 |
| 라우터 결선 | `app/features/*/api/routers/router.py` · `v1/*.py` | 소스 | **검수 대상** — URL 수동 관리 |
| 골격 생성기 | `scripts/new_app.py` | 소스 | 검수 + 수정 (ADR-S01) |
| 진입 문서 | `README.md` · `docs/ARCHITECTURE.md` · `docs/QUICKSTART.md` | 문서 | 유지 |
| 심화 가이드 | `docs/project-guide/v1.1/` 10종 | 문서 | 유지 + 정정 |
| 레지스트리 문서 | `docs/django-style-app-registry/` | 문서 | 2편 유지·재작성, 2편 삭제 |
| 착수 명세 | `docs/orm-raw-repository/2026-08-13/` 3종 | 문서 | **삭제** |
| 폐기 가이드 | `docs/project-guide/v1.0/` 9종 | 문서 | **삭제** |
| CRP 이력 | `docs/crp/groups/` | 문서 | 보존 |
| 검사·CI | `tests/test_docs_*.py` · `.github/workflows/ci.yml` | 소스 | 삭제에 맞춰 조정 |

- 착수 기준선 커밋: `f90eede` · docs 44개 / 575KB
- 착수 상태: 게이트 8단계 통과, 632 passed

## 2. 계약 (Contract)

### 2-1. 이 저장소가 제공하는 것 (목적 3요소)

1. **수동 app 등록** — `config.INSTALLED_APPS` 가 설치 앱의 유일한 진실 공급원
2. **라우터 파일 기반 수동 URL 관리** — `v1/<view>.py` → `router.py` → `AppConfig` prefix
3. **골격(skeleton)** — 위 두 규칙을 따르는 새 앱을 만드는 생성기와 참조 구현

### 2-2. 불변식

- INV-S1: 목적 3요소가 깨지지 않는다
- INV-S2: 문서가 코드에 없는 공개 심볼·기능을 가르치지 않는다
- INV-S3: 삭제한 문서를 가리키는 참조가 남지 않는다(문서·테스트·CI 주석 포함)
- INV-S4: `scripts/review_gate.py` 8단계가 통과한다
- INV-S5: 공개 API 경로·응답 스키마 불변

### 2-3. 비목표

- 기능 앱 축소(`blog`·`reply`·`sns` 의 CRUD 중복 정리) — 별도 결정이 필요하다
- ORM/Raw 계층 재설계, 인증 체계 도입, 성능 튜닝
- CRP 이력 문서 정리

## 3. 인수 기준 (GATE 3 체크리스트)

- [x] 목적 3요소가 코드 실물로 확인됐다 — run-log Round 1 §A 의 표
- [x] 골격 생성기가 만든 앱이 이 저장소의 OpenAPI 계약을 그대로 통과한다 (ADR-S01)
      — `tests/scripts/test_new_app.py` 에 회귀 검사, fail-on-revert 실증
- [x] 삭제한 문서를 가리키는 참조 0건 — 문서·테스트·CI 전수 grep
- [x] 문서가 없는 기능을 있다고 말하지 않는다 (INV-S2) — `require_admin`·
      `AppRegistry.discover()`·`/ready` 부재 서술 정정
- [x] 게이트 8단계 통과
- [x] 공개 API 불변 — `tests/test_route_inventory.py` 및 OpenAPI 규칙 통과

## 4. 변경 이력

- v0.1 (2026-08-25): 최초 작성. 기준선 `f90eede`.
