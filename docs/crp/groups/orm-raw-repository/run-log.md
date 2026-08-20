# Run Log — orm-raw-repository (라운드 로그 + 수렴 판정)

## 라운드 기록

### Round 0 — 2026-08-18 (base SHA: `9c93803`) · 착수 준비
- **트리거:** 세션 재개, 진행 상태 재확인 및 준비상태 구성 (REQ-003)
- **검수 범위:** 기준선 확정만. 구현 코드 변경 없음.
- **확인 사실:** 명세 3종 작성 완료·구현 미착수. 테스트 **307 수집 / 306 passed / 1 failed**
- **신규 finding:** CRIT 0 · HIGH 0 · MED 1 · LOW 0 → ledger F-001
- **수렴 판정:** `NOT CONVERGED`

### Round 1 — 2026-08-18 · 착수 게이트 (development-plan §10.1 A~E)
- **트리거:** 사용자 요청 — "설계·개발계획서를 참고로 작업을 진행해줘" (REQ-004)
- **검수 범위:** 계획서 §10.1 A~E 전부. ORM/Raw 구현(Phase 0~7)은 **미착수** — 계획서가
  "이 다섯 항목을 먼저 처리한 뒤 시작한다"고 진입을 막고 있다.
- **GATE 통과:** 0 ■ 1 ■ 2 ■ 3 ■ 4 ■ 5 ■
- **신규 finding(심각도별):** CRIT 0 · **HIGH 3** · MED 6 · LOW 0
- **신규 Fix:** 9 건 → ledger F-001 ~ F-009 (전부 Fixed)
- **fail-on-revert 검증:** F-001(자식 stderr None 재현) · F-004(canary 유출 라인 재현) ·
  F-009(문서 회귀 3건 재현) — 결함 상태를 실제로 주입해 해당 검사만 실패함을 확인
- **게이트 실행 결과 (전건 실제 실행):**
  - `ruff check` / `ruff format --check` / `mypy`(157 files) / `bandit -ll` — 클린
  - `pytest --cov=app --cov-fail-under=85` — **353 passed, 0 skipped**, coverage **89.75%**
  - alembic 단일 head · SQLite upgrade+check 드리프트 0
  - **MySQL 8.4 실환경**: upgrade head → check clean → downgrade -1 → 재-upgrade → check clean
  - `pytest -m mysql` — 2 passed (compose 컨테이너 실제 기동, 종료 후 volume 까지 정리 확인)
- **수렴 판정:** `CONVERGED` (착수 게이트 범위 한정 — Phase 0~7 은 아직 시작하지 않았다)
- **잔여 위험 변화:** R-001 ~ R-005 수용. R-005 는 이번에 새로 발견한 상호작용이다.
- **깊이 주석:** MySQL 실환경 migration chain 과 실제 secret bind probe 는 이 저장소에서
  **처음** 그 깊이로 본 경로다. 이전까지는 SQLite 단위 테스트와 필터 부재 상태였다.
- **사고 기록:** 하네스 첫 실행이 sibling 저장소의 컨테이너(포트 3308)에 붙어 그 테스트
  DB 테이블을 삭제했다. tmpfs·테스트 전용 DB 라 영구 손실은 없다. 원인은 포트·DB명·계정을
  sibling 과 동일하게 복사한 것 — F-003 으로 등재하고 격리를 자격증명 수준으로 올렸다.

### Round 2 — 2026-08-18 · Phase 0 (계약 고정)
- **트리거:** 사용자 요청 — "진행해줘" (REQ-005)
- **검수 범위:** development-plan Phase 0 전 항목 + Round 1 에서 놓친 §10.1 E 잔여 항목
  (계획서 843줄 이후 — 첫 열람 때 범위를 잘라 읽어 누락했다)
- **GATE 통과:** 0 ■ 1 ■ 2 ■ 3 ■ 4 ■ 5 ■
- **신규 finding(심각도별):** CRIT 0 · **HIGH 2** · MED 4 · LOW 0
- **신규 Fix:** 6 건 → F-010 ~ F-015 (F-015 는 **Open → Phase 3**)
- **기준선 산출물:** `baseline/repository-public-api.md` · `baseline/openapi.json`
  (18 paths · 30 operations · 31 schemas) · `baseline/tests.txt` (361건)
- **핵심 발견:** `BaseRepository` 공개 메서드 **28개 중 기능이 실제로 쓰는 것은 7개**.
  21개는 호출부가 테스트뿐이고 2개(`get_with_join`·`count_with_relation`)는 테스트조차 없다.
  Raw Base 를 같은 넓이로 맞추면 28개짜리 계약을 두 번 구현하게 된다 → Phase 3 축소 근거.
- **게이트 실행 결과 (전건 실제 실행):**
  - `ruff check` / `ruff format --check` / `mypy`(158 files) / `bandit_gate` — 클린
  - `pytest --cov=app --cov-fail-under=85` — **361 passed, 0 skipped**, coverage **89.75%**
  - alembic 단일 head · MySQL 8.4 upgrade→check→downgrade -1→재-upgrade→check 전건 통과
  - compose 컨테이너 기동·정리 확인 (loopback 바인딩으로 변경 후 재검증)
- **수렴 판정:** `CONVERGED` (Phase 0 범위 한정)
- **잔여 위험 변화:** R-006 신규 — traceback 경유 DB 메시지 유출(F-015)을 Phase 3 까지 수용
- **깊이 주석:** 예외 → 로그/응답의 **양방향 유출 경로**를 이 저장소에서 처음 그 깊이로 봤다.
  Round 1 의 `SqlNoiseFilter` 는 로거 **이름**으로 거르므로 `app.*` 로거가 `{e}` 를 찍는
  경로는 그대로 통과하고 있었다 — 필터를 붙였다는 사실이 안전을 뜻하지 않았다.

### Round 3 — 2026-08-19 · Phase 1 (비동기 Runtime · Lifespan Resource Manager)
- **트리거:** 사용자 요청 — 커밋 분리 후 계속 진행 (REQ-006·REQ-007)
- **검수 범위:** development-plan Phase 1 전 항목
- **GATE 통과:** 0 ■ 1 ■ 2 ■ 3 ■ 4 ■ 5 ■
- **신규 finding(심각도별):** CRIT 0 · HIGH 1 · MED 3 · LOW 0
- **신규 Fix:** 4 건 → F-016 ~ F-019
- **구조 변경:**
  - `app/core/resources.py` 신설 — lifespan 은 조립만. 종료 순서를 `AsyncExitStack`
    등록 역순으로 강제하고, cleanup 실패는 삼켜서 뒤따르는 해제를 막지 않는다.
  - `create_db_tables()` 가 registry 소유 테이블만 `tables=` 로 넘긴다(ADR-011).
  - 세션 Dependency 3종 개명 + 옛 이름을 **같은 객체** 별칭으로 유지(ADR-009).
    기능 쓰기 경로를 routed → writer 로 전환.
  - `/ready` 신설, `/health` 는 DB 를 보지 않는다(ADR-013).
  - pool 설정 7종을 `DatabaseSettings` 로 이동 + 총 연결 수 상한 검증.
  - `app/celery/lifecycle.py` 신설 — worker 종료 시 dispose → shutdown_asyncgens →
    close → 참조 제거.
- **게이트 실행 결과 (전건 실제 실행):**
  - `ruff check`/`format` · `mypy`(160) · `bandit_gate`(184) — 클린
  - `pytest --cov` — **385 passed, 0 skipped**, coverage **89.63%**
  - alembic 단일 head · MySQL 8.4 upgrade→check→downgrade -1→재-upgrade→check 통과
- **수렴 판정:** `CONVERGED` (Phase 1 범위 한정)
- **잔여 위험 변화:** 없음. F-015(traceback)는 Phase 3 예정 그대로 Open.
- **깊이 주석:** 종료 경로를 이 저장소에서 처음 그 깊이로 봤다. 기존 lifespan 은
  **정상 종료에서만** drain·dispose 했고, startup 이 깨지면 아무것도 닫지 않았다.

### Round 4 — 2026-08-19 · Phase 2 (ORM 모델 기반 정리)
- **트리거:** 사용자 요청 — Phase 2 → 3a → 3b 순서 합의 후 착수 (REQ-008)
- **검수 범위:** development-plan Phase 2 전 항목
- **GATE 통과:** 0 ■ 1 ■ 2 ■ 3 ■ 4 ■ 5 ■
- **신규 finding(심각도별):** CRIT 0 · HIGH 0 · MED 1 · LOW 0 → F-020
- **한 일:** 공통 필드를 `UUIDPrimaryKeyMixin`/`CreatedAtMixin`/`UpdatedAtMixin` +
  조합 `TimestampMixin` 으로 쪼개고 모델 5개를 전환. `UserAccessLog` 은 `updated_at`
  이 없어 `CreatedAtMixin` 만 쓴다 — 쪼갠 이유가 그것이다.
- **F-020 (측정으로 발견):** mixin 컬럼이 모델 자신의 컬럼 **뒤로** 밀려 `id` 가 중간에
  끼었다. 논리 스키마는 같아 `alembic check` 는 통과하지만, `create_all`(개발)과
  migration(운영)의 컬럼 순서가 갈린다. `sort_order` 로 원래 배치를 고정하고 회귀
  테스트를 두었다 — **DDL 을 실제로 떠서 비교하지 않았으면 못 잡았다.**
- **게이트 실행 결과 (전건 실제 실행):**
  - `ruff check`/`format` · `mypy`(160) · `bandit_gate`(184) — 클린
  - `pytest` — **393 passed** (+ MySQL 마커 2건 별도 실행 통과)
  - MySQL 8.4 `SHOW CREATE TABLE` 전후 비교 — **컬럼 집합·타입·순서 완전 일치**
  - alembic check — SQLite·MySQL 양쪽 "No new upgrade operations"
  - fail-on-revert: `sort_order` 제거 시 5건 실패
- **수렴 판정:** `CONVERGED` (Phase 2 범위 한정)
- **잔여 위험 변화:** R-007 신규 — 인덱스 나열 순서 차이(무해, 아래 참조)
- **환경 문제:** WSL 의 테스트 컨테이너가 healthy 직후 종료 로그 없이 exit 255 로
  반복 종료됐다(3회). OOM 아님, 메모리 여유 13Gi. 재기동 직후 짧은 창에서는 정상
  동작하므로 측정은 마쳤으나, 긴 통합 실행은 불안정하다.

### Round 5 — 2026-08-19 · Phase 3a (공통 안전 변환기 · F-015 닫기)
- **트리거:** 사용자 요청 — Phase 3 을 3a(보안)/3b(계약 축소)로 나눠 진행 (REQ-009)
- **검수 범위:** 예외 → 로그·응답 유출 경로 전체 + rowcount 의존
- **GATE 통과:** 0 ■ 1 ■ 2 ■ 3 ■ 4 ■ 5 ■
- **신규 finding:** CRIT 0 · HIGH 0 · MED 0 · LOW 1 (F-021)
- **닫은 것: F-015** — `app/core/db/errors.py` 의 `convert_db_error()` 로 경계에서
  변환하고 원본을 `from None` 으로 끊는다. Repository 4곳 + **commit 경로**를 전환했고,
  500 핸들러는 DB 예외에 대해 traceback 을 남기지 않는다(변환기 미경유 경로의 마지막
  방어선). canary 가 최종 formatter 출력에 나타나지 않음을 확인 — **C-5 완전 충족**.
- **F-021 (정정 포함):** `rowcount == 0` 을 부재로 읽던 코드를 조회 판단으로 바꿨다.
  다만 **살아있는 버그로 단정했던 것은 틀렸다** — 실측 결과 aiomysql 은
  `CLIENT_FOUND_ROWS` 로 매칭 행 수를 세어 1 을 돌려준다. 지금 404 가 나지는 않으며,
  드라이버·플래그가 바뀌면 조용히 뒤집히는 의존을 제거한 것이 이번 변경의 의미다.
  테스트도 "rowcount 가 몇이냐"가 아니라 "그 값에 의존하지 않는다"를 고정하도록 고쳤다.
- **게이트 실행 결과 (전건 실제 실행):**
  - `ruff`·`mypy`(161)·`bandit_gate`(185) — 클린
  - `pytest --cov` — **412 passed / 0 skipped**, coverage **89.98%**
  - MySQL 8.4 통합 5건(rowcount 3건 포함) 실제 실행 · alembic drift 0
  - fail-on-revert: `from None` → `from exc` 로 되돌리면 구조 검사가 실패
- **수렴 판정:** `CONVERGED` (Phase 3a 범위 한정)
- **잔여 위험 변화:** **R-006 해소**(F-015 Fixed).

### Round 6 — 2026-08-19 · Phase 3b (공개 계약 축소 — A안)
- **트리거:** STOP 체크포인트에서 사용자가 **A안(최소 8개)** 선택 (REQ-010)
- **검수 범위:** `BaseRepository` 공개 계약 전체 + PK 타입
- **GATE 통과:** 0 ■ 1 ■ 2 ■ 3 ■ 4 ■ 5 ■
- **신규 finding:** 0건 (계약 변경이며 결함 수정이 아니다)
- **한 일:**
  - 공개 메서드 **28 → 8** (`create`·`get_by_id`·`get_one`·`get_all`·`count`·
    `exists`·`update`·`delete`). 제거 20개는 **기능 호출 0건**을 이름별로 직접 확인.
  - 그 20개만 쓰던 private helper 2개(`_apply_eager_loading`·`_apply_column_loading`)도
    함께 제거 — 남겨두면 호출부 없는 코드가 된다.
  - `repository_base.py` **980줄 → 289줄**.
  - PK 를 `PrimaryKeyT`(기본 `str`)로 계약에 노출. 기존 `BaseRepository[User]` 표기 유지.
  - 제거 메서드만 검증하던 테스트 8건 삭제, 혼합 테스트 4건은 남는 계약만 보도록 정리.
  - 계약 고정 테스트 추가 — 목록 동등 비교 + 제거 20개의 **부활 금지** 검사.
- **정정:** 착수 전 스캔 스크립트가 "테스트 호출 0건"으로 잘못 보고했다. 이름별 직접
  grep 으로 재확인해 20개 모두 테스트 호출이 **있음**을 확정한 뒤 진행했다. 스크립트
  결과를 그대로 믿었으면 테스트 정리를 빠뜨렸을 것이다.
- **게이트 실행 결과 (전건 실제 실행):**
  - `ruff`·`mypy`(161)·`bandit_gate`(185) — 클린
  - `pytest --cov` — **426 passed / 0 skipped**, coverage **91.00%** (89.98% → 상승)
  - MySQL 8.4 통합 5건 실제 실행 · alembic drift 0
- **수렴 판정:** `CONVERGED` — **Phase 3 완료**
- **잔여 위험 변화:** 없음.

### Round 7 — 2026-08-19 · Phase 4 (Raw SQL Base)
- **트리거:** 사용자 "다음 작업 진행해줘" (REQ-011)
- **검수 범위:** Raw Base 2파일 + 라우터의 Raw 판정 경로
- **GATE 통과:** 0 ■ 1 ■ 2 ■ 3 ■ 4 ■ 5 ■
- **신규 finding:** 2건 (F-022 HIGH · F-023 LOW) — 둘 다 Fixed
- **한 일:**
  - `raw_crud_base.py` — protected primitive 4개(`_fetch_one`/`_fetch_all`/
    `_fetch_scalar`/`_execute`). `RowMapping` 반환, named binding, rowcount, **commit 금지**.
  - `raw_repository_base.py` — public API 4개 + `query_name` 검증 + 구조화 로그 +
    예외 변환(`convert_db_error` 재사용, `from None`).
  - (F-022) 라우터에 **intent 기반 판정** 도입 — `read_intent()`/`write_intent()`/
    `statement_intent()`/`is_read_only_session()` 공개. `_is_write()` 가 `TextClause` 를
    intent 로만 가르고, 미분류는 쓰기로 본다(fail-closed).
  - 차단은 **두 겹**이다. Raw Base 가 실행 전에 `is_read_only_session()` 으로 거부하고
    (라우터를 꺼도 동작), 라우터가 바인딩 시점에 한 번 더 막는다 — "설정을 끄면 보안도
    꺼지는" 상태를 만들지 않기 위해서다.
  - (F-023) `query_name` 정규식 앵커를 `$` → `\Z` 로 교체.
  - 정적 검사 2종 추가 — `text()` 보간 금지 · `query_name` 코드 상수 소유.
    **두 검사기 모두 자기 자신을 먼저 검증**한다(나쁜 입력에서 실제로 걸리는지).
- **측정:** replica 오라우팅은 writer/reader 두 엔진에 다른 행을 심어 **결과값으로**
  증명했다. 쓰기 확인은 같은 세션 재조회가 아니라 **엔진에 직접** 물었다 — 쓰기가
  replica 로 갔어도 같은 세션은 그 replica 를 다시 읽어 "성공"처럼 보이기 때문이다.
- **plan 항목 중 이미 충족된 것:** "third-party SQL/driver 로그 end-to-end canary" 와
  "Alembic 실행 후 application logger 생존"은 Round 1~2 에서 이미 구현·검증되어 있어
  중복 작성하지 않았다(`tests/core/test_security_hardening.py`).
- **게이트 실행 결과 (전건 실제 실행):**
  - `ruff`·`ruff format`·`mypy`(163)·`bandit_gate`(187) — 클린
  - `pytest --cov` — **474 passed / 0 skipped**, coverage **91%**
    (Raw Base 커버리지: `raw_crud_base` 100% · `raw_repository_base` 96%)
  - MySQL 8.4 통합 5건 실제 실행 · alembic head 재적용 후 **drift 0**
  - fail-on-revert: 두 방어선 각각 제거 시 13건 실패 확인 후 복구
- **수렴 판정:** `CONVERGED` (Phase 4 범위 한정)
- **잔여 위험 변화:** R-00x 신규 없음. Raw SQL 의 **MySQL 방언 정확성**은 Phase 5 의
  통합 테스트가 담당한다 — 이 라운드는 SQLite 로 Base 계약만 확인했다(ADR-004).

### Round 8 — 2026-08-19 · Phase 5 (두 예제 기능)
- **트리거:** 사용자 "진행해줘" (REQ-012)
- **검수 범위:** 신규 기능 2개 전체 + migration 2개 + 골든 스냅샷 3종
- **GATE 통과:** 0 O 1 O 2 O 3 O 4 O 5 O
- **신규 finding:** 1건 (F-024 MED) — Fixed
- **한 일:**
  - `catalog`(ORM) — 상품 CRUD 5개 엔드포인트. `Numeric(12,2)` 금액, SKU 전역 고유,
    limit 상한 100, SKU 오름차순 **안정 정렬**(정렬 없는 pagination 은 페이지 중복·누락).
  - `reports`(Raw) — 일별 매출 집계. `RowMapping` -> `dict(row)` -> Pydantic 검증.
    조회 전용이라 read-only Dependency 만 노출.
  - `sales_orders` 는 스키마 모델(`SalesOrder`)을 두되 **조회에는 쓰지 않는다** —
    registry/metadata 동등성과 drift 검사를 유지하면서 집계는 Raw 로 한다(SCN-RAW-001).
  - migration 2개 (`catalog_products`, `sales_orders`) — 명시적 upgrade/downgrade.
  - Admin: `Product` 는 편집 가능, `SalesOrder` 는 **읽기 전용** — 원본을 화면에서
    고치면 리포트 숫자가 근거 없이 움직인다.
  - 두 기능 모두 `INSTALLED_APPS` 등록만으로 붙는다. `main.py` 는 건드리지 않았다.
- **방언 결정 2건:**
  - (ADR-019) 기간 상한을 `DATE_ADD` 대신 Service 가 계산한 배타 상한으로 바인딩.
    같은 SQL 이 MySQL/SQLite 양쪽에서 돌고, 경계 규칙이 테스트가 볼 수 있는 코드가 된다.
  - (ADR-020) `text()` 에는 타입 정보가 없어 `Decimal` 이 SQLite 드라이버에서 거부된다.
    `bindparams()` 로 타입을 명시했다 — Raw 계약의 실제 함정이라 주석으로 남겼다.
- **정정:** fail-on-revert 를 처음에 **두 개를 동시에** 되돌려 돌렸다. 두 결함이 서로를
  가려(배타 상한을 줄이자 취소 주문이 범위 밖으로 빠짐) SQLite 쪽 신호가 사라졌다.
  하나씩 다시 돌려 각각의 신호를 확인했다.
- **fail-on-revert (개별 실행):**
  - 상태 필터 제거 -> **5건** 실패 (SQLite 2 + MySQL 3)
  - 배타 상한 제거 -> **1건** 실패 (전용 가드 `test_end_date_is_inclusive`)
- **골든 스냅샷 갱신:** 라우트 인벤토리 3경로, migration 예상 테이블 2개, 앱 라벨 2개,
  Admin 관리 모델 2개, `ARCHITECTURE.md` 의 `INSTALLED_APPS` 예제.
- **게이트 실행 결과 (전건 실제 실행):**
  - `ruff`·`ruff format`·`mypy`(201)·`bandit_gate`(231) — 클린
  - `pytest --cov` — **550 passed / 0 skipped**, coverage **92%**
    (신규 기능 22개 모듈 중 20개가 100%, 최저 95%)
  - MySQL 8.4 통합 **15건** 실제 실행 — 집계 타입(Decimal), 배타 상한, injection,
    head->base->head 왕복, revision 단계별 downgrade, DECIMAL 스케일, 컬럼 배치
  - MySQL drift 0 (`compare_metadata` 로 migration 스키마 vs registry 모델 직접 비교)
- **수렴 판정:** `CONVERGED` (Phase 5 범위 한정)
- **잔여 위험 변화:** **R-009 해소**(Raw SQL 의 MySQL 방언 검증 완료). R-008(WSL 컨테이너)은
  이번 라운드 내내 재현되지 않아 **관찰 유지** — 원인을 특정하지 못했으므로 닫지 않는다.

### Round 9 — 2026-08-19 · Phase 6 (Scalar 문서 정비)
- **트리거:** 사용자 "진행해줘" (REQ-013)
- **검수 범위:** OpenAPI 스키마 전체 + `tags_metadata.py` + 공개 DTO 이름
- **GATE 통과:** 0 O 1 O 2 O 3 O 4 O 5 O
- **신규 finding:** 4건 (F-025 MED · F-026 LOW · F-027 LOW · F-028 MED) — 전부 Fixed
- **측정으로 시작했다:** 규칙을 쓰기 전에 현재 스키마를 실제로 훑었다. 그 결과가
  F-025~F-027 이다. 짐작으로 규칙만 만들었으면 이미 깨져 있는 것을 못 봤을 것이다.
- **한 일:**
  - (F-025) `UserResponse` 충돌 해소 — auth 쪽을 `AuthenticatedUserResponse` 로 개명.
    `__` 를 포함한 schema key 2개가 사라졌다.
  - (F-026) `tags_metadata.py` 전면 재작성 — `Auth` 추가, `Analytics` 제거,
    구현 완료 기능의 "예정" 문구 제거. 선언 9개 == 사용 9개.
  - (F-027) `ErrorResponse` 를 OpenAPI 3.1 `examples` 로 전환 + 필드 설명 3개 추가.
  - 예제 DTO 예시 보강 — `ProductUpdate` 는 **일부 필드만** 담은 예시를 둔다(PATCH 를
    PUT 처럼 쓰게 만들지 않으려고).
  - `tests/test_openapi_contract.py` — 규칙 24건(공허 통과 방지 3건 포함).
  - `scripts/openapi_revert_check.py` — 규칙별 결함 주입 하네스 20건.
- **F-028 이 이번 라운드의 요점이다.** 규칙 24건이 전부 초록불이었지만, 결함을 주입해
  보니 셋이 아무것도 검사하지 않고 있었다. FastAPI 가 `summary`·`operationId` 를
  자동으로 채우고, `response_model` 을 지워도 반환 타입에서 schema 를 다시 만든다.
  게다가 `app.routes` 직접 순회는 `_IncludedRouter` 때문에 기능 라우트를 하나도
  보지 못했다(3개만 보였다). 규칙을 "자동 생성값과 같은가"로 바꾸고 라우터를
  평탄화해 다시 검증했다.
- **정정:** revert 하네스 첫 판이 예외로 죽으면서 복구를 건너뛰어 `blog.py` 를
  깨진 상태로 남겼다(operationId 중복). git 으로 되돌리고 복구를 `finally` 로 옮겼다.
- **fail-on-revert:** 20종 주입 → **20/20 감지**. 매 실행 후 `git status` 로 복구 확인.
- **게이트 실행 결과 (전건 실제 실행):**
  - `ruff`·`ruff format`·`mypy`(202)·`bandit_gate`(231) — 클린
  - `pytest --cov` — **574 passed / 0 skipped**, coverage **92%**
  - MySQL 8.4 통합 15건 실제 실행
  - `baseline/openapi.json` 갱신 (paths 22 · schemas 38)
- **수렴 판정:** `CONVERGED` (Phase 6 범위 한정)
- **잔여 위험 변화:** 신규 없음. Scalar **브라우저 렌더링**은 여전히 미검증이다 —
  스키마가 규격에 맞는지는 봤지만 실제 화면은 열어보지 않았다.

### Round 10 — 2026-08-19 · Phase 7 (문서 및 최종 검수)
- **트리거:** 사용자 "진행해줘" (REQ-014)
- **검수 범위:** 저장소 전체 — alias 잔재, 게이트 구성, 문서 참조
- **GATE 통과:** 0 O 1 O 2 O 3 O 4 O 5 O
- **신규 finding:** 3건 (F-029 HIGH · F-030 MED · F-031 MED) — 전부 Fixed
- **한 일:**
  - deprecated session alias 3개 제거 (ADR-009 의 예정 시점). 기능 호출부는 **0건**이었고,
    남은 것은 정의·re-export·docstring·안내 문구뿐이었다. 부활 금지 검사로 교체.
  - `scripts/review_gate.py` — 7단계를 하나로. UTF-8 고정(자식 프로세스 포함),
    실행마다 고유 캐시, 첫 실패에서 멈추지 않음, MySQL skip 을 실패로 판정.
  - `tests/test_docs_references.py` — 문서가 **가리키는 대상**이 실재하는지 13건.
  - `docs/crp/groups/orm-raw-repository/completion-report.md` — 완료 보고서.
- **F-031 이 이번 라운드에서 제일 컸다.** 문서 26곳이 사라진 심볼을 안내하고 있었다.
  코드 테스트는 전부 초록불이었다 — 문서는 아무것도 import 하지 않으니까. 그리고
  쓰기 예시가 routed 세션을 쓰고 있어서, 이름뿐 아니라 **동작**도 틀렸다.
- **F-029 는 게이트가 자기 자신을 검사하다 나왔다.** 명세의 "게이트를 병렬 실행해도
  충돌이 없어야" 항목을 실제로 3개 동시 실행으로 시험했더니, fail-on-revert 하네스가
  서로의 소스 수정을 밟아 주입 문구를 저장소에 남겼다. 시험하지 않았으면 몰랐다.
- **정정:** 처음 만든 게이트의 skip 판정에 `deselected` 를 넣어, `-m mysql` 의 정상
  동작(나머지를 deselect)을 실패로 읽었다. 게이트가 영원히 빨간불이 되는 상태였다.
  `skipped` 와 `no tests ran` 만 보도록 고쳤다.
- **검수 게이트 자체를 검증했다:**
  - MySQL 컨테이너를 **내리고** 실행 → skip 금지가 잡고 종료 코드 **1**
  - `--fast` → 6단계 통과 + "실행하지 않았다" 경고, 종료 코드 **0**
  - 게이트 **3개 동시 실행** → 전부 통과, `scaffoldprobe` 잔해 0, 소스 오염 0
- **게이트 실행 결과 (전건 실제 실행):**
  - `review_gate` 7단계 전부 통과
  - `pytest --cov` — **587 passed / 0 skipped**, coverage **92%**
  - MySQL 8.4 통합 15건 실제 실행 · fail-on-revert 20/20 감지
- **수렴 판정:** `CONVERGED` — **전체 작업 완료**
- **잔여 위험 변화:** 신규 없음. R-011(줄바꿈)은 사용자 결정 대기로 남긴다.

### Round 11 — 2026-08-19 · 잔여 위험 2건 해소 (사용자 요청)
- **트리거:** "렌더링은 플라이라이트를 이용하면 되지 않는가? 3번은 정규화 실행해줘" (REQ-015)
- **신규 finding:** 1건 (F-032 HIGH) — Fixed
- **한 일:**
  - `.gitattributes` 를 채웠다 — **0바이트였다.** `* text=auto eol=lf` 로 고정하고
    blob 5개·작업트리 30개를 LF 로 정규화. `.bat`/`.cmd` 는 CRLF 유지, 바이너리 제외.
  - Playwright + Chromium 으로 Scalar 실렌더링 검증 7건 추가. 게이트 8단계로 확장.
- **정정:** 앞서 "저장소 줄바꿈 혼재(CRLF 202 / LF 67)" 라고 보고했는데, 그 숫자는
  **작업트리** 기준이었고 blob 은 LF 365 / CRLF 5 였다. 두 측정이 서로 다른 것을 재고
  있었다 — 어느 쪽인지 밝히지 않은 채 하나로 말한 것이 잘못이다.
- **F-032 가 이번 라운드의 교훈이다.** `playwright.sync_api` 를 쓰자 브라우저와 무관한
  테스트가 38 failed / 124 errors 로 깨졌다. **게이트는 통과했다** — 마커로 나눠 돌리기
  때문이다. 마커 없이 전체를 돌린 뒤에야 드러났다. async API 로 전환했다.
- **측정한 것:** Scalar 가 태그 9개를 그리고, Markdown 표가 실제 `<table>` 7개가 되고,
  예제 DTO 예시(`SKU-1001`·`129000.00`)가 화면에 나타난다. 외부 404
  (`api.scalar.com`)는 세지 않는다 — 통제할 수 없고 렌더링에 영향이 없다.
- **git 인증 확인(사용자 요청):** remote·로컬 user(bluebamus)·GCM 2.7.3·저장된 자격증명
  모두 정상. `git push --dry-run` 으로 **쓰기 권한까지** 확인했다. 오류 없음.
- **게이트:** 8단계 전부 통과 · **594 passed / 0 skipped** · 병렬 2회 통과
- **수렴 판정:** `CONVERGED`
- **잔여 위험 변화:** **R-011 해소**(줄바꿈), **미검증 4번 해소**(Scalar 렌더링).
- **후속(같은 날, push 이후):** 브랜치를 origin 에 올렸고 CI 가 처음 돌았다. 워크플로
  결함 3건이 드러나 고쳤다 — (1) GATE 3 이 마커 없이 인프라 테스트까지 돌림,
  (2) `deselected` 를 위반으로 오판(로컬 게이트에서 고친 것과 **같은 실수**를 CI 에는
  반영하지 않았다), (3) 브라우저 단계가 붙으며 20분 예산 초과. 수정 후 두 job 모두
  success. **미검증 6번(CI 실제 실행) 해소.**

## 심각도 추세
| Round | CRIT | HIGH | MED | LOW | 신규 Fix | 판정 |
|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 1 | 0 | 1 | NOT CONVERGED |
| 1 | 0 | 3 | 6 | 0 | 9 | CONVERGED (착수 게이트 한정) |
| 2 | 0 | 2 | 4 | 0 | 6 | CONVERGED (Phase 0 한정) · Open 1건(F-015→Phase 3) |
| 3 | 0 | 1 | 3 | 0 | 4 | CONVERGED (Phase 1 한정) |
| 4 | 0 | 0 | 1 | 0 | 1 | CONVERGED (Phase 2 한정) |
| 5 | 0 | 0 | 0 | 1 | 1 | CONVERGED (Phase 3a 한정) · **F-015 닫힘** |
| 6 | 0 | 0 | 0 | 0 | 0 | CONVERGED — **Phase 3 완료** (계약 변경) |
| 7 | 0 | 1 | 0 | 1 | 2 | CONVERGED — **Phase 4 완료** |
| 8 | 0 | 0 | 1 | 0 | 1 | CONVERGED — **Phase 5 완료** |
| 9 | 0 | 0 | 2 | 2 | 4 | CONVERGED — **Phase 6 완료** |
| 10 | 0 | 1 | 2 | 0 | 3 | CONVERGED — **전체 작업 완료** |
| 11 | 0 | 1 | 0 | 0 | 1 | CONVERGED — 잔여 위험 2건 해소 |
