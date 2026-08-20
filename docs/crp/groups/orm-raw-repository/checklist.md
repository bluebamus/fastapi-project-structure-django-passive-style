# Checklist — orm-raw-repository (개선 항목 추적판)

## Round 0 — 2026-08-18 · 착수 준비
- [x] 이번 요청을 design-baseline §2 에 기록 (REQ-003) + 이전 요구 충돌 확인
- [x] CRP 그룹 6파일 적재
- [x] charter 인벤토리·계약·불변식(INV-1~6)·인수기준 확정
- [x] 기준선 측정 — `9c93803` · 307 수집 / 306 passed / 1 failed
- [x] (F-001) 기준선 실패 1건 등재

## Round 1 — 2026-08-18 · 착수 게이트 (development-plan §10.1 A~E)
- [x] 이번 요청을 design-baseline §2 에 기록 (REQ-004) + 불가침 제약 충돌 확인
- [x] **A.** (F-001) 자식 프로세스 stderr UTF-8 — `-X utf8` + `errors="strict"` +
      대상 디렉터리 미생성 검증 · fail-on-revert 확인
- [x] **A.** (F-002) 같은 결함의 형제 3곳 동시 수정 — 근본 원인 위치에서 처리
- [x] **A.** 재발 차단 검사 — `test_python_subprocesses_in_tests_force_utf8`
- [x] **B.** ADR-019 유지 확인 — Queue logging 미혼입(`QueueHandler`/`QueueListener` 0건)
- [x] **C.** `compose.test.yaml`(MySQL 8.4 · `${MYSQL_TEST_PORT:-3309}`) 신설
- [x] **C.** `mysql` 마커 등록 · `cryptography` 의존성 추가 · `tests/integration/` 하네스
- [x] **C.** (F-003) 격리를 포트가 아니라 **자격증명**으로 — sibling 컨테이너 오접속 차단
- [x] **C.** CI job 신설 — 같은 compose 파일 사용 · skip 을 실패로 취급 · `down -v` 정리
- [x] **C.** 표준 흐름 실제 실행 — upgrade → check → downgrade -1 → 재-upgrade → check
- [x] **D.** (F-009) README·ARCHITECTURE·QUICKSTART 의 default-style 잔재 제거
- [x] **D.** 회귀 검사 6종 추가 — 등록 절차 존재 · 옛 절차 부활 금지 · `__init__.py` marker ·
      migration/runtime 동일 registry · 환경변수 실재 · fail-on-revert 확인
- [x] **E.** (F-004) `SqlNoiseFilter` 전 handler 부착 + `LOG_SQL_ECHO_ENABLED` ·
      실제 secret bind canary probe (유출/차단 양방향 확인)
- [x] **E.** (F-005) `migrations/env.py` `disable_existing_loggers=False` + 로거 생존 테스트
- [x] **E.** (F-006) `.env.example` CORS 충돌 해소 + 예제 설정 로드 테스트
- [x] **E.** (F-007) production/staging 무인증 `/admin` fail-fast + 잔여 위험 문서화
- [x] **E.** (F-008) 검수 게이트 stdio UTF-8 고정 (bandit cp949 크래시)
- [x] **E.** AST 계층 검사(utils→상위 · core→features · features↔features) 신설
- [x] **E.** OpenAPI 비공허성 검사(경로·응답·설명·스키마) 신설
- [x] GATE 3 인수기준 전부 그린 — 353 passed / 0 skipped / coverage 89.75%
- [x] 요구사항 회귀 0 — C-1~C-8 위반 없음. **C-4 주석**: `tests/utils/test_logs.py` 의
      `filters == ["context"]` 동등 비교를 `"context" in filters` 로 완화했다.
      ADR-019 가 지키는 것은 handler 구성이지 필터 개수가 아니다 → ADR-005 로 박제
- [x] run-log 심각도 추세 갱신 + 수렴 판정
- [x] residual-risk 갱신 — R-001~R-005 + "검사하지 않은 것" 5항목

## Round 2 — 2026-08-18 · Phase 0 (계약 고정)
- [x] 이번 요청을 design-baseline §2 에 기록 (REQ-005) + 불가침 제약 충돌 확인
- [x] `BaseRepository` 공개 메서드 사용처 전수 조사 → `baseline/repository-public-api.md`
      (공개 28개 · 기능 사용 7개 · 테스트만 19개 · 호출 0건 2개)
- [x] OpenAPI 기준선 저장 → `baseline/openapi.json` (18 paths · 30 ops · 31 schemas)
- [x] 테스트 수집 기준선 저장 → `baseline/tests.txt` (361건)
- [x] (F-010) 일반 500 응답을 DEBUG 에서도 불투명하게 — TestClient 실응답 canary 검증
- [x] (F-011) Repository 예외 `detail` 에서 원본 DB 메시지 제거 (4곳)
- [x] (F-012) 앱 로거의 예외 메시지 보간 제거 (11곳) + 소스 스캔 회귀 검사
- [x] (F-013) `LOG_SQL_ECHO_ENABLED` 를 development/test 로 제한 (교차 설정 fail-fast)
- [x] (F-014) 테스트 DB 를 loopback 에만 publish
- [x] bandit UTF-8/JSON reporter — `scripts/bandit_gate.py`, reporter 실패도 게이트 실패
- [x] 검수 도구 temp/cache 실행별 격리 + cleanup (`GATE_TMP` → mypy·pytest·coverage)
- [x] 실패 시 stdout·stderr 동시 보존
- [x] (ADR-008) ORM/Raw 공통 트랜잭션 규칙 확정 — 커밋은 쓰기 View 가 1회
- [x] (ADR-009) DB session Dependency 정식 이름 + alias 제거 시점(Phase 7) 확정
- [x] (ADR-010 · F-015) traceback 유출은 Phase 3 안전 변환기로 닫기로 결정하고 **Open 유지**
- [x] GATE 3 인수기준 전부 그린 — 361 passed / 0 skipped / coverage 89.75%
- [x] 요구사항 회귀 0 — C-1~C-15 위반 없음
- [x] run-log·ledger·residual-risk 갱신

## Round 3 — 2026-08-19 · Phase 1 (비동기 Runtime · Lifespan Resource Manager)
- [x] 이번 요청을 design-baseline §2 에 기록 (REQ-006·REQ-007)
- [x] `app/core/resources.py` · `ApplicationResources` 신설, lifespan 을 조립만 남김
- [x] (F-018) `owned_tables()` 기반 create_all 축소 · 모델 0개면 DB 미접속
- [x] (F-016) startup 실패와 정상 shutdown 의 **동일 cleanup 경로** + 실패 격리 테스트
- [x] (F-017) drain timeout 후 취소 + gather 회수 + 추적 집합 비우기
- [x] (ADR-012) 대기 80% / 취소 회수 20% 예산 분리 + 회귀 테스트
- [x] (ADR-009) 세션 Dependency 3종 개명 + **같은 객체** 별칭 · identity 테스트
- [x] (F-019) 기능 쓰기 경로를 routed → writer 로 전환 + AST 재발 차단
- [x] (ADR-013) `/ready` writer `SELECT 1` · 2초 timeout · 503 · 자격증명 미노출
- [x] `/health` 가 DB 를 보지 않음을 테스트로 고정
- [x] pool 설정 7종을 `DatabaseSettings` 로 이동 + 총 연결 수 상한 검증 + `.env.example`
- [x] `app/celery/lifecycle.py` — worker 종료 시 dispose → asyncgens → close → 참조 제거
- [x] (C-18) FastAPI/Celery 자원 소유권 분리를 import 검사로 고정
- [x] GATE 3 인수기준 전부 그린 — 385 passed / 0 skipped / coverage 89.63%
- [x] 요구사항 회귀 0 — C-1~C-18 위반 없음
- [x] run-log·ledger·residual-risk 갱신

## Round 4 — 2026-08-19 · Phase 2 (ORM 모델 기반 정리)
- [x] 이번 요청을 design-baseline §2 에 기록 (REQ-008)
- [x] `UUIDPrimaryKeyMixin`/`CreatedAtMixin`/`UpdatedAtMixin` + 조합 `TimestampMixin`
- [x] 모델 5개 전환 — `UserAccessLog` 은 `CreatedAtMixin` 만(updated_at 없음)
- [x] (F-020) `sort_order` 로 컬럼 배치 고정 + fail-on-revert 확인
- [x] MySQL `SHOW CREATE TABLE` 전후 비교 — 컬럼 집합·타입·순서 완전 일치
- [x] alembic check — SQLite·MySQL 양쪽 drift 0
- [x] Mixin 조합 테스트는 별도 `DeclarativeBase` 사용 (application metadata 미오염 확인)
- [x] GATE 3 인수기준 전부 그린 — 393 passed + MySQL 마커 2건
- [x] 요구사항 회귀 0 — C-1~C-19 위반 없음
- [x] run-log·ledger·residual-risk 갱신

## Round 5 — 2026-08-19 · Phase 3a (공통 안전 변환기 · F-015)
- [x] 이번 요청을 design-baseline §2 에 기록 (REQ-009)
- [x] `app/core/db/errors.py` — `convert_db_error()` · `driver_error_code()`
- [x] Repository 4개 변환 지점 전환 (`from None` 으로 원본 차단)
- [x] **commit 경로**도 변환기 경유 — 지연 제약 위반이 그대로 올라가던 구멍
- [x] 500 핸들러: DB 예외에는 traceback 미출력(마지막 방어선) + 드라이버 코드만 기록
- [x] (F-015) canary 가 최종 formatter 출력에 없음을 확인 — **C-5 완전 충족**
- [x] fail-on-revert: `from None` → `from exc` 시 구조 검사 실패
- [x] (F-021) `rowcount` 로 존재 판단하지 않도록 변경 + MySQL 실측 테스트 3건
- [x] GATE 3 인수기준 전부 그린 — 412 passed / 0 skipped / coverage 89.98%
- [x] 요구사항 회귀 0 — C-1~C-21 위반 없음
- [x] run-log·ledger·residual-risk 갱신 (R-006 해소)

## Round 6 — 2026-08-19 · Phase 3b (공개 계약 축소 — A안 승인)
- [x] 이번 요청을 design-baseline §2 에 기록 (REQ-010)
- [x] 제거 대상 20개의 호출부를 **이름별로 직접** 재확인 (기능 0건 · 테스트만)
- [x] 공개 메서드 28 → 8 (ADR-016) · `repository_base.py` 980줄 → 289줄
- [x] 제거 20개만 쓰던 private helper 2개도 함께 제거
- [x] `PrimaryKeyT`(기본 `str`) 로 PK 타입 파라미터화 — 기존 표기 호환
- [x] 제거 메서드 전용 테스트 8건 삭제 · 혼합 테스트 4건 정리
- [x] 계약 고정 테스트 — 목록 동등 비교 + 제거 20개 **부활 금지**
- [x] baseline 문서에 결정 결과 주석 (근거 보존)
- [x] GATE 3 인수기준 전부 그린 — 426 passed / 0 skipped / coverage 91.00%
- [x] 요구사항 회귀 0 — C-1~C-22 위반 없음

## Round 7 — 2026-08-19 · Phase 4. Raw SQL Base 구현
- [x] 이번 요청을 design-baseline §2 에 기록 (REQ-011)
- [x] `raw_crud_base.py` — protected primitive 4개 · `RowMapping`·named binding·rowcount
- [x] `raw_repository_base.py` — public API 4개 · `query_name` 검증 · 구조화 로그 · 예외 변환
- [x] **commit 금지** — rollback 후 값이 되돌아오는지로 증명 (ADR-008)
- [x] (F-022) 명시적 read/write intent + 미분류 `TextClause` **fail-closed** (ADR-017)
- [x] read-only 세션 DML 차단 — Base(실행 전) + 라우터(바인딩 시점) **두 겹**
- [x] 회귀 8종 — 일반 DML·소문자·선행 공백·주석·블록 주석·CTE DML·INSERT·UPDATE
- [x] `FOR UPDATE` 는 write intent — writer 고정 확인 (결과값으로)
- [x] replica 오라우팅 — 두 엔진에 다른 행을 심어 결과값으로 증명
- [x] (F-023) `query_name` 정규식 앵커 `$` → `\Z`
- [x] 정적 `text()` 보간 검사 · `query_name` 코드 상수 검사 — **검사기 자체 검증 포함**
- [x] AR-003 — `RawRepositoryBase` 가 `BaseRepository` 를 상속하지 않음
- [x] fail-on-revert — 두 방어선 각각 제거 시 13건 실패 확인
- [x] GATE 3 인수기준 전부 그린 — 474 passed / 0 skipped / coverage 91%
- [x] 요구사항 회귀 0 — C-1~C-24 위반 없음
- [x] run-log·ledger·checklist 갱신

## Round 8 — 2026-08-19 · Phase 5. 두 예제 기능 구현
- [x] 이번 요청을 design-baseline §2 에 기록 (REQ-012)
- [x] `catalog`(ORM) 상품 CRUD 5개 엔드포인트 + Repository/Service/Dependency/DTO
- [x] `reports`(Raw) 일별 매출 집계 + `RowMapping` -> `dict(row)` -> Pydantic 검증
- [x] `SalesOrder` 스키마 모델 등록 (조회에는 미사용 — SCN-RAW-001)
- [x] migration 2개 (`catalog_products`·`sales_orders`) 명시적 upgrade/downgrade
- [x] 각 예제에 `apps.py` AppConfig + `config.INSTALLED_APPS` 등록 (main.py 무수정)
- [x] Admin — `Product` 편집 가능 / `SalesOrder` 읽기 전용
- [x] (ADR-019) 방언 함수 제거 — 배타 상한을 Service 가 계산해 바인딩
- [x] (ADR-020) `bindparams()` 로 Raw bind 타입 명시
- [x] SCN-RAW-002 Raw DML workflow — rowcount·commit 1회·read-only 차단·`updated_at`
- [x] 빈 schema fixture 로 head -> base -> head 왕복 (MySQL)
- [x] revision **단계별** downgrade 확인 — 한 번에 base 로 내리면 중간이 묻힌다
- [x] MySQL 방언 실측 — `Decimal` 반환, DECIMAL(12,2) DDL, 컬럼 배치
- [x] (F-024) 순서 의존 실패 수정 — `config` reload 후 stale `db_settings` 패치
- [x] ORM/Raw 대칭성 기계 검사 25건 (`tests/test_orm_raw_parity.py`)
- [x] fail-on-revert 2종 개별 확인 (5건 / 1건)
- [x] 골든 스냅샷 5곳 갱신 + `ARCHITECTURE.md` 정합
- [x] GATE 3 인수기준 전부 그린 — 550 passed / 0 skipped / coverage 92%
- [x] 요구사항 회귀 0 — C-1~C-26 위반 없음

## Round 9 — 2026-08-19 · Phase 6. Scalar 문서 정비
- [x] 이번 요청을 design-baseline §2 에 기록 (REQ-013)
- [x] **측정 먼저** — 현재 스키마를 훑어 실제 결함 3종 확인
- [x] (F-025) `UserResponse` 충돌 해소 → `AuthenticatedUserResponse` (ADR-021)
- [x] (F-026) `tags_metadata.py` 재작성 — `Auth` 추가 · `Analytics` 제거 · "예정" 문구 제거
- [x] (F-027) `ErrorResponse` OpenAPI 3.1 `examples` 전환 + 필드 설명
- [x] 예제 DTO 예시 보강 (`ProductUpdate` 는 부분 수정 모양으로)
- [x] `tests/test_openapi_contract.py` — 규칙 24건 (공허 통과 방지 3건 포함)
- [x] 핵심 schema snapshot — 필드 집합·필수 여부만 고정 (설명 변경에 안 깨지게)
- [x] (F-028) fail-on-revert 로 **헛도는 규칙 3건 + 라우터 평탄화 결함** 발견·수정
- [x] `scripts/openapi_revert_check.py` — 규칙별 주입 하네스, 복구는 `finally`
- [x] fail-on-revert **20/20 감지** · 매 실행 후 복구 확인
- [x] `baseline/openapi.json` 갱신
- [x] GATE 3 인수기준 전부 그린 — 574 passed / 0 skipped / coverage 92%
- [x] 요구사항 회귀 0 — C-1~C-29 위반 없음

## Round 10 — 2026-08-19 · Phase 7. 문서 및 최종 검수
- [x] 이번 요청을 design-baseline §2 에 기록 (REQ-014)
- [x] deprecated session alias 3개 제거 — 기능 호출부 0건을 이름별로 확인 (ADR-009)
- [x] alias 부활 금지 검사로 교체 (모듈 속성 + 패키지 `__all__` 둘 다)
- [x] `scripts/review_gate.py` — 7단계 일원화 (ADR-023)
- [x] UTF-8 고정 — 자기 stdout/stderr + 자식 프로세스 `PYTHONIOENCODING`
- [x] 실행마다 고유 캐시 디렉터리 (ruff·mypy)
- [x] MySQL skip 금지 — 컨테이너를 내리고 **실제로 종료 코드 1** 확인
- [x] `--fast` 는 제외 사실을 출력에 남기고 종료 코드 0
- [x] (F-029) 게이트 3개 병렬 → 소스 오염 발견 → temp 기반 배타 락으로 순차화
- [x] (F-030) `test_new_app` 이름에 PID 부착 — 병렬 실행 시 디렉터리 경합 해소
- [x] 병렬 3개 재시험 — 전부 통과, 잔해 0, 오염 0
- [x] (F-031) 문서 26곳의 죽은 심볼 참조 수정 (세션 21 + Repository 5)
- [x] 쓰기 예시를 routed → writer 세션으로 정정 (F-019 반영 누락분)
- [x] `tests/test_docs_references.py` — 문서 참조 실재 검사 13건
- [x] 검사기 정밀화 — 변경 이력 제외, 백틱/코드블록만, 루트 기준 경로만
- [x] `completion-report.md` — 실행하지 않은 검증 7항목·잔여 위험 5건 명시
- [x] GATE 3 인수기준 전부 그린 — 587 passed / 0 skipped / coverage 92%
- [x] 요구사항 회귀 0 — C-1~C-31 위반 없음

---

**전체 작업 완료.** Phase 0~7 전부 CONVERGED, 열린 결함 0건.
남은 것은 사용자 확인 항목뿐이다 — CI 첫 실행, Scalar 렌더링, `.gitattributes` 결정.

---

## Round 11 — 2026-08-19 · 잔여 위험 2건 해소
- [x] 이번 요청을 design-baseline §2 에 기록 (REQ-015)
- [x] `.gitattributes` 작성 — 0바이트였다. `* text=auto eol=lf`
- [x] blob 5개 재정규화 · 작업트리 30개 LF 변환 · 잔존 0 확인
- [x] Playwright + Chromium 설치, dev 의존성 등재
- [x] Scalar 실렌더링 7건 — 태그 9개·Markdown 표·예시 값·우리 오리진 실패 0
- [x] (F-032) sync API → async API 전환 — 전체 실행에서 594 passed 확인
- [x] `browser` 마커 등록 · 게이트 8단계로 확장 (skip 금지 적용)
- [x] git 인증 확인 — remote·user·GCM·push 권한 전부 정상, 오류 없음
- [x] 게이트 8단계 전부 통과 · 병렬 2회 통과
- [x] R-011 · 미검증 4번 해소 표기