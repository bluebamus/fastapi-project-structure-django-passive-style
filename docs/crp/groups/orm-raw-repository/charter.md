# Charter — orm-raw-repository  (Charter v0.1 / 2026-08-18)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항·불가침 제약(C-1~C-8)과 모순될 수 없다.

## 1. 인벤토리 (Scope Inventory)

| 영역/하위시스템 | 경로 | 종류 | 비고 |
|---|---|---|---|
| ORM Base | `app/core/models/models_base.py`, `app/core/repositories/crud_base.py`, `app/core/repositories/repository_base.py` | 소스 | 재설계 대상 (plan §5) |
| Raw Base | `app/core/repositories/raw_crud_base.py`, `raw_repository_base.py` | 소스 | **신규** (plan §6) |
| App Registry | `app/core/apps/{config,registry,wiring,exceptions}.py`, `config.py` | 소스 | 기존 계약 유지 (C-2·C-3) |
| DB 세션/라우팅 | `app/core/db/{session,router}.py` | 소스 | writer/read-only 분기 (C-1) |
| Lifespan/자원 | `app/core/bootstrap.py`, `main.py` | 소스 | Resource Manager 보강 (plan §9) |
| 예제 기능 | `app/features/<catalog>`, `app/features/<reports>` | 소스+테스트 | **신규** 시나리오 2종 (plan §7) |
| 문서 계약 | `app/core/tags_metadata.py`, OpenAPI/Scalar | 소스 | plan §8 |
| 통합 테스트 환경 | `compose.test.yaml`, `pyproject.toml` (`mysql` marker) | 설정 | **신규** (ADR-004) |
| 기준 문서 | `README.md`, `docs/ARCHITECTURE.md`, `docs/QUICKSTART.md` | 문서 | passive 정합성 복구 (plan §10.1 D) |
| 명세 3종 | `docs/orm-raw-repository/2026-08-13/{requirements,development-plan,workflow-guide}.md` | 문서 | 요구·계획·지침 원본 |

- 착수 기준선 커밋: `9c93803` · 소스 `.py` **158** · 테스트 파일 **62** · 수집 테스트 **307**
- 기준선 상태(Round 0): 306 passed / 1 failed
- Round 1 종료: 353 passed / 0 skipped · coverage 89.75% — 착수 게이트 A~E 완료
- Round 2 종료: 361 passed / 0 skipped · coverage 89.75% — Phase 0 완료.
  기준선 산출물은 `baseline/` (repository-public-api.md · openapi.json · tests.txt)
- Round 3 종료: 385 passed / 0 skipped · coverage 89.63% — Phase 1 완료.
  신규 소스: `app/core/resources.py` · `app/celery/lifecycle.py`
- Round 4 종료: 393 passed + MySQL 마커 2건 — Phase 2 완료.
- Round 5 종료: 412 passed / 0 skipped · coverage 89.98% — Phase 3a 완료.
  신규 소스: `app/core/db/errors.py`. **ledger F-015 닫힘 → C-5 완전 충족**
- **Round 6 종료 상태: 426 passed / 0 skipped · coverage 91.00%** — **Phase 3 완료**.
  `BaseRepository` 공개 계약 28 → 8 (`repository_base.py` 980줄 → 289줄)

## 2. 계약 (Contract)

### 2-1. 지원 구성
- Python 3.12 · SQLAlchemy async · SQLite(단위) / MySQL 8.4(통합, compose 전용 포트 3308)
- 앱 합류는 `config.INSTALLED_APPS` + `apps.py` AppConfig 경로만 지원

### 2-2. 위협 모델
- 방어한다: SQL bind 파라미터·secret 의 로그 유출, read-only 세션에서의 DML, CORS wildcard+credentials 조합, 인증 없는 `/admin` 의 production 노출
- 방어하지 않는다: 부하·성능, 복제 실환경, Celery 워커 실행, Scalar UI 실렌더링

### 2-3. 불변식
- INV-1: 쓰기 View 는 writer 세션, 조회 View 는 read-only 세션으로만 실행된다 (C-1)
- INV-2: ORM/Raw 은 Repository 계층에서만 갈라지고 View·Dependency·Service·DTO 형태는 동일하다 (ADR-002)
- INV-3: `INSTALLED_APPS` 밖의 라우터·모델은 앱에 합류하지 않는다 (C-2)
- INV-4: migration metadata 와 runtime metadata 는 같은 registry 결과다 (C-3)
- INV-5: 어떤 application handler 출력에도 secret canary 가 나타나지 않는다 (C-5)
- INV-6: 문서가 참조하는 경로·심볼·환경변수는 실재한다 (C-8)
- INV-7: 일반 500 응답과 Repository 예외 `detail` 은 원본 DB 메시지를 담지 않는다 (C-12)
- INV-8: 앱 로거는 예외 메시지를 보간하지 않는다 — 타입만 남긴다 (C-13)
- INV-9: 커밋은 쓰기 View 본문이 1회 수행한다. Repository·Service 는 커밋하지 않는다 (ADR-008)
- INV-10: startup 실패와 정상 shutdown 은 같은 cleanup 경로를 탄다 (C-16)
- INV-11: 개발용 create_all 은 registry 소유 테이블만 대상으로 한다 (ADR-011)
- INV-12: `/health` 는 DB 를 보지 않는다. 준비 상태는 `/ready` 가 답한다 (ADR-013)
- INV-13: 공통 필드는 Mixin 으로만 오고, 컬럼 배치는 id → 도메인 → created_at → updated_at 이다 (C-19)
- INV-14: DB 예외는 경계에서 변환되고 원본은 이어지지 않는다 — 응답에도 traceback 에도 SQL·bind 값이 없다 (C-20)
- INV-15: `BaseRepository` 공개 메서드는 정확히 8개다 (C-22 · ADR-016)
- INV-16: Raw DML 은 read-only 세션에서 **실행 전에** 거부된다. 라우터를 꺼도 막힌다 (C-23 · ADR-017)
- INV-17: Raw Repository 는 commit 하지 않고 `RowMapping`/scalar/rowcount 만 돌려준다 (ADR-008 · RAW-REP-005)
- INV-18: SQL 문자열은 Raw Repository 밖에 존재하지 않는다 (C-25)
- INV-19: ORM 예제와 Raw 예제는 Repository 를 뺀 모든 계층이 같다 (C-26)
- INV-20: OpenAPI schema key 에 `__` 가 없다 — 공개 DTO 이름이 전역 고유하다 (C-27 · ADR-021)
- INV-21: 선언 태그 집합 == 사용 태그 집합 (C-28)
- INV-22: `get_session`·`get_read_session`·`get_write_session` 은 존재하지 않는다 (ADR-009)
- INV-23: 문서가 가리키는 심볼·경로·환경변수는 실재한다 (C-30)
- INV-24: 저장소 줄바꿈은 LF 다 (C-32)
- INV-25: Scalar 문서는 실제 브라우저에서 그려진다 (ADR-024)

### 2-4. 비목표
- Queue logging 전환(별도 ADR), 성능 튜닝, 인증 체계 개편, 멀티테넌시
- Base 계층의 편의 메서드 — 일괄/upsert/eager loading/부분 컬럼 조회는 기능별
  Repository 소관이다. Base 에 다시 올리려면 ADR-016 을 뒤집는 새 ADR 이 필요하다.

## 3. 인수 기준 (GATE 3 체크리스트)
- [x] 전 테스트 실제 실행·통과 — 완료 시점 **594 passed / 0 skipped**(run-log Round 10), 2026-08-20 재측정 **632 passed / skip·xfail·deselect 0**
- [x] `pytest -m mysql` 이 compose 인스턴스에서 실제 실행 — 2026-08-20 재측정 **22 passed / skip 0**. 게이트 7단계가 skip 을 실패로 처리한다
- [x] alembic upgrade head → downgrade → 재-upgrade → drift 0 — `tests/integration/test_mysql_migration_roundtrip.py` 5건 (`head_to_base_to_head_round_trip` · `new_revisions_have_a_working_downgrade` · `migrated_schema_matches_the_registry_models` 등), MySQL 에서 실제 실행
- [x] mypy·정적분석 클린, stdio UTF-8 고정 — 게이트 1~4단계(ruff format·ruff check·mypy·bandit) + `tests/test_layering_and_openapi.py::test_ci_pins_utf8_stdio` · `::test_python_subprocesses_in_tests_force_utf8`
- [x] 불변식 구조 증거: **INV-1~25** 각각에 검사가 연결됨
      (이 줄의 문구는 v0.1 당시 **INV 6개** 기준이었고 이후 §2-3 이 25개로 늘었다.
      2026-08-20 재검수에서 전수 대조했다 — 아래 매핑 참조)
- [x] OpenAPI 문서 규칙 비공허성 검증 — 게이트 6단계 `scripts/openapi_revert_check.py` ("규칙이 실제로 결함을 잡는지 — 통과만으로는 알 수 없다")
- [x] 질의 수준(design-baseline §0 = 적극) 준수 — Round 0~11 각 라운드 로그에 P/D 질의와 결정 근거가 남아 있다


### 3-1. 불변식 → 검사 매핑 (2026-08-20 전수 대조)

| INV | 검사 |
|---|---|
| INV-1 세션 선택 | `tests/test_read_path_no_commit.py` · `tests/core/test_db_router.py` |
| INV-2 Repository 에서만 분기 | `tests/test_orm_raw_parity.py` |
| INV-3 미등록 앱 비합류 | `tests/core/apps/test_manual_registration.py` · `test_installed_apps.py` |
| INV-4 migration == runtime metadata | `tests/core/test_alembic_metadata.py` |
| INV-5 secret canary | `tests/core/test_security_hardening.py` |
| INV-6 문서 참조 실재 | `tests/test_docs_references.py` |
| INV-7 예외 detail 원문 차단 | `tests/core/test_db_error_conversion.py` |
| INV-8 로그 보간 금지 | `tests/core/test_security_hardening.py` · `tests/core/test_raw_repository_base.py::test_logs_carry_query_name_but_not_sql_or_params` |
| INV-9 커밋은 View 1회 | `tests/test_read_path_no_commit.py` · `tests/test_orm_raw_parity.py::test_no_feature_commits_outside_the_view` |
| INV-10 startup 실패·shutdown 동일 cleanup | `tests/core/test_runtime_lifecycle.py` |
| INV-11 create_all 대상 한정 | `tests/core/test_bootstrap.py` · `tests/core/test_alembic_metadata.py` |
| INV-12 `/health` 는 DB 를 안 본다 · `/ready` | `tests/core/test_runtime_lifecycle.py` (503 응답·스키마 포함) |
| INV-13 Mixin 컬럼 배치 | `tests/core/test_model_mixins.py` |
| INV-14 DB 예외 경계 변환 | `tests/core/test_db_error_conversion.py` |
| INV-15 `BaseRepository` 공개 8개 | `tests/core/test_repository_base.py` |
| INV-16 Raw DML read-only 거부 | `tests/core/test_raw_routing.py` · `tests/core/test_db_router_env.py` |
| INV-17 Raw commit 없음·반환 형태 | `tests/core/test_raw_repository_base.py` |
| INV-18 SQL 은 Raw Repository 밖에 없다 | `tests/test_orm_raw_parity.py::test_only_the_raw_repository_owns_sql` · `tests/core/test_raw_repository_base.py::test_raw_base_owns_no_domain_sql` |
| INV-19 예제 계층 동일 | `tests/test_orm_raw_parity.py` |
| INV-20 schema key `__` 없음 | `tests/test_openapi_contract.py` |
| INV-21 선언 태그 == 사용 태그 | `tests/test_openapi_contract.py` |
| INV-22 옛 세션 이름 부재 | `tests/core/test_runtime_lifecycle.py` · `tests/test_docs_references.py::test_session_dependency_names_in_docs_are_importable` |
| INV-23 문서 심볼·경로·환경변수 실재 | `tests/test_docs_references.py` (2026-08-20 이후 `project-guide` 현행 버전까지 포함) |
| INV-24 저장소 줄바꿈 LF | **실행 테스트 없음.** `.gitattributes` 의 `* text=auto eol=lf` 가 커밋 시점에 강제한다 |
| INV-25 Scalar 실렌더링 | `tests/browser/test_scalar_rendering.py` (게이트 8단계) |

**INV-24 에 테스트를 두지 않는 이유.** 줄바꿈은 git 이 커밋 시점에 정규화한다. 작업
디렉터리 파일을 읽어 CRLF 를 금지하는 테스트를 쓰면 Windows 체크아웃에서 오히려 실패한다
— 실제로 이 저장소의 작업 트리에는 CRLF 가 있고 `.gitattributes` 가 blob 을 LF 로 만든다.
검사를 추가하면 git 이 이미 보장하는 것을 잘못된 층에서 다시 주장하게 된다.

## 4. 변경 이력
- v0.1 (2026-08-18): 최초 작성. 기준선 `9c93803` 확정.
- v0.2 (2026-08-18): Round 1 반영 — 착수 게이트 A~E 완료 상태와 실측치 갱신.
- v0.3 (2026-08-18): Round 2 반영 — Phase 0 완료. INV-7~9 추가.
- v0.4 (2026-08-19): Round 3 반영 — Phase 1 완료. INV-10~12 추가.
- v0.5 (2026-08-19): Round 4 반영 — Phase 2 완료. INV-13 추가.
- v0.6 (2026-08-19): Round 5 반영 — Phase 3a 완료. INV-14 추가.
- v0.7 (2026-08-19): Round 6 반영 — Phase 3 완료. INV-15 추가, §2-4 비목표 보강.
- v0.8 (2026-08-19): Round 7 반영 — Phase 4 완료. INV-16~17 추가.
- v0.9 (2026-08-19): Round 8 반영 — Phase 5 완료. INV-18~19 추가.
- v0.10 (2026-08-19): Round 9 반영 — Phase 6 완료. INV-20~21 추가.
- v1.0 (2026-08-19): Round 10 반영 — **전체 작업 완료**. INV-22~23 추가.
- v1.1 (2026-08-19): Round 11 반영 — 잔여 위험 2건 해소. INV-24~25 추가.
- v0.6 (2026-08-20): 재검수. 미체크로 남아 있던 인수 기준 7칸을 근거와 함께 닫고,
  불변식 범위 문구를 실제 집합(INV-1~25)에 맞췄다. §3-1 매핑표를 추가했다.
  인수 기준 자체는 바꾸지 않았다.
