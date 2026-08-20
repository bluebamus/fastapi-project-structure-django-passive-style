# Design Baseline — orm-raw-repository (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준(authoritative baseline)**. charter(코드 계약)와 달리
> 이 문서는 *"사용자가 무엇을, 왜 요구했는가"* 의 영속 기록이다. **모든 추가 작업은 여기 기록된
> Active 요구사항과 불가침 제약을 위반하지 않아야 한다**(요구사항 회귀 방지). 새 요청이 올 때마다
> §2 에 append 하고, 설계 결정은 §3 에 ADR 로 고정한다. append-only — 항목은 지우지 않고
> 상태(Active/Superseded)만 바꾼다.

## 0. 질의 수준 (Autonomy Level)

- [x] **적극(Thorough)**
- [ ] 보통(Balanced)
- [ ] 간략(Lean)

선택: **적극** · 선택일: 2026-08-18 · 변경 이력: (없음)

## 1. 목적 / 배경

`fastapi-project-structure-django-passive-style` 에 ORM(SQLAlchemy 모델) 과 Raw SQL(`text()`)
두 데이터 접근 방식을 **Repository 구현만 다르고 나머지는 동일한** 구조로 제공한다.
Dependency → Service → Repository 흐름, read-only/writer 세션 선택, 트랜잭션 경계, Pydantic
검증, App Registry 기반 라우터 취합, OpenAPI/Scalar 문서 품질, 예외·테스트·정적검사 기준은
두 방식이 같아야 한다. 요구·계획·지침 3종 명세는 `docs/orm-raw-repository/2026-08-13/` 에 있다.

sibling 저장소 `fastapi-default-project-structure` 는 같은 작업을 이미 완주했고(`db49e9c`,
CRP F-001~F-018 전건 Fixed, 373 tests), 그 결과를 **착수 게이트 피드백**으로 이관받는다.

## 2. 요구사항 레지스터 (append-only)

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-08-13 | ORM/Raw 두 데이터 접근 방식을 일관된 구조로 제공 | `requirements.md` 전문 — ORM Base(`crud_base`/`repository_base`) 재설계, Raw Base(`raw_crud_base`/`raw_repository_base`) 신설, 예제 시나리오 2종(상품 카탈로그 CRUD · 일별 매출 리포트), Scalar 문서 기준, Lifespan Resource Manager | Active | plan §5~§9 / charter INV-1~INV-6 |
| REQ-002 | 2026-08-18 | default 저장소 완주 결과를 passive-style 착수 게이트로 이관 | plan §10.1 A~E — CLI stderr UTF-8, ADR-019 유지(Queue logging 분리), MySQL 8.4 통합환경 신설, 기준문서 passive 정합성 복구, 보안 하드닝(SQL redaction·migration logger 생존·CORS·ADMIN 기본값·검수 게이트) | Active | plan §10.1 |
| REQ-003 | 2026-08-18 | 세션 재개 — 진행 상태 재확인 및 준비상태 구성 | CRP 그룹 6파일 적재, 기준선(테스트 307개 중 1건 실패) 확정, Phase 0 착수 대기 | Active | Round 0 |
| REQ-004 | 2026-08-18 | `docs/orm-raw-repository/` 설계·개발계획서를 참고로 작업 진행 | 계획서 §10.1 이 진입을 막고 있으므로 착수 게이트 A~E 를 먼저 완주. ORM/Raw 구현(Phase 0~7)은 그 다음 | Active | Round 1 · F-001~F-009 · ADR-005 |
| REQ-005 | 2026-08-18 | 계속 진행 | Phase 0(계약 고정) 수행 — Base Repository 공개 API 사용처 기준선, OpenAPI·테스트 수집 기준선, §10.1 E 잔여 항목(500 불투명·SQL echo 환경 제한·loopback·bandit reporter·temp 격리), 트랜잭션 규칙과 세션 명명 ADR 확정 | Active | Round 2 · F-010~F-014 · ADR-008~010 |
| REQ-006 | 2026-08-19 | Round 1·Phase 0 를 두 커밋으로 분리 기록 | 브랜치 `feat/orm-raw-repository-phase0` · 각 커밋이 독립적으로 그린 · CRLF→LF 오염 5파일 복구 | Active | fe1dcb0 · 1819fef |
| REQ-007 | 2026-08-19 | 계속 진행 | Phase 1 — `ApplicationResources`, owned_tables 기반 create_all, 실패/정상 동일 cleanup, drain 취소 회수, 세션 Dependency 명명 전환, `/ready`, pool Settings 이동, Celery worker 종료 | Active | Round 3 · ADR-011~013 · C-16~C-18 |
| REQ-008 | 2026-08-19 | 계속 진행 (Phase 2 → 3a → 3b 순서 합의) | Phase 2 — UUID/created/updated 책임 분리 Mixin, 모델 5개 전환, **schema diff 0 · 컬럼 배치 불변** | Active | Round 4 · ADR-014 |
| REQ-009 | 2026-08-19 | 계속 진행 | Phase 3a — 공통 안전 변환기로 F-015 닫기, commit 경로 포함, rowcount 의존 제거 | Active | Round 5 · ADR-015 · F-015 Fixed |
| REQ-010 | 2026-08-19 | Phase 3b 를 **A안**(최소 8개)으로 진행 | 공개 계약 28 → 8 축소, 제거 20개(기능 호출 0건 확인), PK 타입 파라미터화 | Active | Round 6 · ADR-016 |
| REQ-015 | 2026-08-19 | Playwright 로 렌더링 확인 + 줄바꿈 정규화 실행 | `.gitattributes` LF 고정, Playwright 브라우저 테스트 7건, 게이트 8단계로 확장 | Active | Round 11 · ADR-024 |
| REQ-014 | 2026-08-19 | 진행해줘 | Phase 7 — alias 제거, 검수 게이트 일원화, 문서 참조 기계 검사, 완료 보고서 | Active | Round 10 · ADR-023 |
| REQ-013 | 2026-08-19 | 진행해줘 | Phase 6 — Scalar 문서 정비: 태그 정합, schema 이름 충돌 해소, 규칙 기반 OpenAPI 검증 24종 + 규칙별 fail-on-revert | Active | Round 9 · ADR-021~022 |
| REQ-012 | 2026-08-19 | 다음 작업 진행 | Phase 5 — ORM(`catalog`)/Raw(`reports`) 예제 두 개, migration 2개, MySQL 방언·왕복 통합 테스트 | Active | Round 8 · ADR-019~020 |
| REQ-011 | 2026-08-19 | 다음 작업 진행 | Phase 4 — Raw Base(`RawCRUDBase`/`RawRepositoryBase`), 명시적 read/write intent 라우팅, `query_name` 규칙, 정적 `text()` 보간 검사 | Active | Round 7 · ADR-017~018 |

## 3. 설계 결정 기록 (ADR)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-08-13 | "비즈니스 코드는 View 에서 실행" = View 는 주입받은 Service 유스케이스를 호출한다. 규칙은 Service, SQL 은 Repository | requirements §4.1 | Accepted | |
| ADR-002 | 2026-08-13 | ORM/Raw 는 Repository 구현만 분기한다. DI·Service·세션 선택·트랜잭션·DTO·라우팅·문서·예외는 공통 | requirements §2 | Accepted | |
| ADR-003 | 2026-08-13 | 이번 작업에서 ADR-019(console + RotatingFileHandler)를 **유지**한다. Queue logging 은 후속 ADR 로 분리 | plan §10.1 B | Accepted | |
| ADR-004 | 2026-08-13 | MySQL 8.4 통합 테스트는 신규 `compose.test.yaml`로 격리한다. SQLite 는 단위테스트 전용이며 방언 정확성 근거로 쓰지 않는다 | plan §10.1 C | Accepted | |
| ADR-005 | 2026-08-18 | ADR-019 가 고정하는 것은 **handler 구성**(console + RotatingFileHandler)이지 handler 의 필터 개수가 아니다. 보안 필터(`sql_noise`) 추가는 ADR-019 유지와 모순되지 않는다 | C-4 는 Queue logging 전환을 막기 위한 제약이다(plan §10.1 B). `tests/utils/test_logs.py` 의 `filters == ["context"]` 동등 비교는 그 의도보다 넓게 잠근 것이라 `"context" in filters` 로 완화했다 | Accepted | |
| ADR-006 | 2026-08-18 | 테스트 인스턴스 격리는 포트가 아니라 **DB명·계정**으로 보장한다. 전용 포트는 3309 | 포트만 나누면 다른 저장소의 컨테이너에 조용히 붙어 스키마를 지운다(F-003 에서 실제 발생). 계정이 다르면 오접속이 인증 거부로 즉시 드러난다 | Accepted | |
| ADR-007 | 2026-08-18 | 무인증 `/admin` 의 개발 기본값(`ADMIN=true`)은 유지하되, production/staging 에서는 `ADMIN_UNAUTHENTICATED_ACK` 승인 없이는 기동을 거부한다 | plan §10.1 E 의 "동등한 fail-fast 보호". 2026-08-12 의 개발 우선 결정을 뒤집지 않으면서 사고와 의도를 구분한다 | Accepted | |
| ADR-008 | 2026-08-18 | **ORM/Raw 공통 트랜잭션 규칙**: 커밋은 *쓰기 View 본문*이 `await service.commit()` 로 한 번 수행한다. Repository 도 Service 도 스스로 커밋하지 않는다. 롤백은 세션 Dependency 의 teardown 이 담당한다. Raw Repository 는 **커밋 금지**이며 read-only 세션에서의 DML 은 차단된다 | 커밋 지점이 여러 곳이면 한 요청이 부분 커밋된 상태로 끝날 수 있고, 그 상태는 재현이 어렵다. 커밋을 View 한 곳으로 모으면 트랜잭션 경계가 HTTP 요청 경계와 1:1 이 된다. ORM/Raw 가 이 규칙을 공유해야 "Repository 구현만 다르다"(ADR-002)가 성립한다 | Accepted | |
| ADR-011 | 2026-08-19 | 개발용 `create_all` 대상은 전역 `Base.metadata` 가 아니라 **registry 소유 테이블**(`tables=`)로 한정한다. 소유 테이블 0개면 DB 에 접속하지 않는다 | `Base.metadata` 는 전역이라 한 번이라도 import 된 모델(테스트의 임시 모델 포함)이 남는다. 전체를 넘기면 설치하지 않은 앱의 테이블이 개발 DB 에 생긴다 — C-2·C-3 위반 | Accepted | |
| ADR-012 | 2026-08-19 | drain 예산을 **대기 80% / 취소 회수 20%** 로 나눈다 | 바깥 guard 와 같은 값을 대기에 주면 취소 회수 도중 잘려, 태스크의 `finally`(세션 rollback/close)가 실행되지 못한 채 engine dispose 로 넘어간다. 그러면 이미 닫힌 pool 을 만지는 태스크가 남는다 | Accepted | |
| ADR-016 | 2026-08-19 | `BaseRepository` 공개 계약을 **최소 CRUD 8개**로 고정한다: `create`·`get_by_id`·`get_one`·`get_all`·`count`·`exists`·`update`·`delete`. 그 밖의 조회/일괄/upsert 는 기능별 Repository 가 소유한다. PK 는 `PrimaryKeyT`(기본 `str`)로 계약에 노출한다 | 28개 중 기능이 실제 호출한 것은 7개였고 20개는 호출부가 테스트뿐이었다(baseline 근거). ADR-002 가 "Repository 구현만 다르다"를 요구하므로 넓은 계약은 **Raw 에서 두 번 구현**해야 한다 — 쓰지도 않는 20개를 두 번 만들 이유가 없다. 사용자가 A안(최소)을 선택 | Accepted | |
| ADR-015 | 2026-08-19 | DB 예외는 경계에서 `convert_db_error()` 로 변환하고 **원본을 `from None` 으로 끊는다**. 로그에는 예외 클래스·드라이버 코드·모델·연산만 남기고 드라이버 메시지 본문은 버린다 | 원본을 `from e` 로 이어두면 위에서 누가 `logger.exception` 을 부르는 순간 traceback 에 SQL 과 바인딩 값이 통째로 찍힌다. 그 로거 이름은 `app.*` 이라 `SqlNoiseFilter` 도 통과한다(F-015). 메시지 본문에 값이 들어 있으므로 파싱해 재사용하지 않는다 | Accepted | |
| ADR-014 | 2026-08-19 | 공통 필드 Mixin 은 **책임 단위로 쪼갠다**(`UUIDPrimaryKeyMixin`/`CreatedAtMixin`/`UpdatedAtMixin`) + 조합 `TimestampMixin`. mixin 컬럼은 `sort_order` 로 원래 배치(id → 도메인 → created → updated)를 고정한다 | 실제 모델이 그렇게 생겼다 — 접속 로그처럼 한 번 쓰고 고치지 않는 테이블은 `updated_at` 이 없다. `sort_order` 없이는 mixin 컬럼이 뒤로 밀려 `create_all`(개발)과 migration(운영)의 컬럼 순서가 갈리는데, Alembic 은 순서를 diff 로 잡지 않아 **아무 경고 없이** 어긋난다 | Accepted | |
| ADR-013 | 2026-08-19 | liveness(`/health`)와 readiness(`/ready`)를 분리한다. `/health` 는 DB 를 보지 않는다 | liveness 가 DB 에 의존하면 DB 가 잠깐 흔들릴 때 오케스트레이터가 멀쩡한 프로세스를 죽인다 — 복구가 아니라 장애 증폭이다. 준비되지 않은 인스턴스는 재시작이 아니라 LB 에서 빼는 것이 맞다 | Accepted | |
| ADR-010 | 2026-08-18 | 잡히지 않은 예외의 **traceback 로그**(`logger.exception`)는 유지한다. 그 안의 DB 예외 메시지 유출은 Phase 3 의 "공통 안전 변환기"가 예외를 소독하는 방식으로 닫는다 — traceback 자체를 끄지 않는다 | traceback 을 없애면 운영 장애에서 원인 추적 수단이 사라진다. 유출을 막는 올바른 지점은 출력이 아니라 **예외가 만들어지는 곳**이다. 그때까지 이 경로는 ledger F-015 로 열어 둔다 | Accepted | |
| ADR-017 | 2026-08-19 | Raw 구문의 읽기/쓰기는 **SQL 을 해석해 추론하지 않고 호출부가 붙인 intent**(`execution_options`)로 판정한다. `fetch_*`=read, `execute`=write, 잠금 읽기(`FOR UPDATE`)=write. **intent 없는 `TextClause` 는 쓰기로 본다(fail-closed)** | 첫 토큰 파싱은 소문자·공백·주석까지는 버티지만 `WITH ... DELETE` 같은 CTE DML 을 읽기로 오판한다(requirements RAW-REP-007 이 default 프로젝트의 잔여 위험으로 명시). 오판의 두 방향은 비대칭이다 — 읽기로 잘못 보면 DML 이 replica 로 새어 조용히 사라지고, 쓰기로 잘못 보면 SELECT 하나가 primary 로 갈 뿐이다. 모를 때는 비싼 쪽이 아니라 안전한 쪽을 고른다 | Accepted | |
| ADR-018 | 2026-08-19 | Raw 로그 라벨 `query_name` 은 `feature.use_case` 형식의 **코드 상수**여야 한다. Base 가 형식·길이(64)를 **실행 전에** 검증하고, 코드 상수 소유는 AST 검사로 강제한다. 로그에는 `query_name`·소요 시간·성공 여부만 남기고 SQL 본문·params 는 남기지 않는다 | 요청값으로 라벨을 만들면 관측 도구의 시계열이 무한히 늘어나고(cardinality), 그 값 자체가 로그에 영구 보존된다. 형식 검증만으로는 "코드가 소유한 상수인가"를 알 수 없어 정적 검사를 함께 둔다. 정규식은 `$` 가 아니라 `\Z` 를 쓴다 — `$` 는 끝의 개행 앞에서도 맞아 로그 한 줄을 쪼개는 값이 통과한다(F-023) | Accepted | |
| ADR-019 | 2026-08-19 | Raw 집계 SQL 에서 **방언 전용 함수를 계약에서 뺀다**. 기간 상한은 `DATE_ADD(:end, INTERVAL 1 DAY)` 가 아니라 Service 가 계산한 **배타 상한**(`:end_exclusive`)을 바인딩한다 | 테스트 편의로 SQL 을 치환한 것이 아니다 — 방언 함수를 빼면 같은 SQL 이 MySQL·SQLite 양쪽에서 그대로 돌고, 기간 경계 규칙이 SQL 이 아니라 **Service 의 코드**로 드러난다. 포함/배타 경계는 리포트에서 가장 자주 틀리는 지점이라 테스트가 직접 볼 수 있는 곳에 있어야 한다 | Accepted | |
| ADR-020 | 2026-08-19 | Raw `text()` 의 bind 값 중 드라이버가 직접 못 받는 타입(`Decimal`·tz-aware `datetime`)은 `bindparams()` 로 **타입을 명시**한다 | `text()` 에는 타입 정보가 없어 값이 드라이버로 그대로 간다. ORM 경로에서 이 문제가 안 보이는 것은 컬럼 타입이 어댑터를 붙여주기 때문이다. 방언별로 SQL 을 갈아끼우는 것이 아니라 같은 SQL 에 타입만 알려주는 것이므로 계약이 갈리지 않는다 | Accepted | |
| ADR-021 | 2026-08-19 | 공개 Pydantic DTO class 이름은 **프로젝트 전체에서 고유**해야 한다. 충돌하면 의미가 좁은 쪽 이름을 바꾼다(`auth.UserResponse` → `AuthenticatedUserResponse`) | 서로 다른 모듈의 같은 class 이름은 schema key 가 `app__features__auth__schemas__auth_schema__UserResponse` 처럼 **모듈 경로**로 노출된다. 그 이름은 파일을 옮기는 순간 바뀌고, 그때 이 스키마로 생성한 클라이언트 코드가 통째로 깨진다. 결과(`__` 금지)와 원인(이름 고유성)을 각각 검사한다 | Accepted | |
| ADR-022 | 2026-08-19 | 문서 품질 규칙은 “비어 있는가”가 아니라 **“사람이 썼는가”**를 본다. `summary`·`operationId` 는 FastAPI 자동 생성값과 비교한다 | FastAPI 는 `summary` 를 함수명 제목화로, `operationId` 를 함수명+경로 조합으로 자동으로 채운다. 그래서 “비었는가” 규칙은 **절대 실패하지 않는 장식**이 된다 — 실제로 fail-on-revert 를 돌려 그 상태를 발견했다. 자동 생성 `operationId` 는 경로를 바꾸면 함께 바뀌어 클라이언트 메서드 이름을 전부 갈아엎는다 | Accepted | |
| ADR-023 | 2026-08-19 | 검수 게이트는 **하나의 스크립트**(`scripts/review_gate.py`)로 모으고, MySQL 통합은 **skip 을 실패로 본다**. 인프라가 없으면 `--fast` 로 명시적으로 제외해야 하며 그 사실이 출력에 남는다 | 검사를 손으로 나눠 돌리면 빠뜨리는 것과 순서에 따라 결과가 달라지는 것이 조용히 생긴다. skip 을 통과로 보면 “전체 green” 이 거짓말이 된다 — 인프라가 없어 안 돈 것과 돌아서 통과한 것은 다르다(NFR-012). 컨테이너를 내리고 실제로 종료 코드 1 이 나오는 것까지 확인했다 | Accepted | |
| ADR-024 | 2026-08-19 | Scalar 렌더링은 **실제 브라우저**로 검증한다(Playwright + Chromium, `pytest -m browser`). Playwright 는 **async API** 만 쓴다 | 스키마가 3.1 규격에 맞는 것과 화면이 그려지는 것은 다르다 — 규격에 맞는 스키마를 렌더러가 못 그리면 사용자는 빈 화면을 본다. `sync_api` 는 자기 이벤트 루프를 돌려 `asyncio_mode=auto` 인 이 저장소에서 **브라우저와 무관한 테스트 수백 개를 함께 깨뜨린다**(38 failed / 124 errors 실측). 마커로 나눠 돌리면 가려지지만 전체 실행에서 드러난다 | Accepted | |
| ADR-009 | 2026-08-18 | **DB session Dependency 명명**: `get_read_session`→`get_read_only_db_session`, `get_write_session`→`get_writer_db_session`, `get_session`→`get_routed_db_session`. Phase 1 에서 새 이름을 추가하고 옛 이름은 deprecated alias 로 남긴다. **alias 제거 시점 = Phase 7**(호출부 전환 완료 후, 사용처 0건을 기계로 확인한 뒤) | `session` 만으로는 HTTP 세션·사용자 세션과 구분되지 않는다(plan §9.8). 이름을 한 번에 바꾸면 `dependency_overrides` 를 쓰는 테스트가 조용히 어긋나므로, alias 기간을 두고 callable identity 를 보존한다 | Accepted | |

## 4. 불가침 제약 (추가 작업이 위반 금지)

- C-1: 쓰기 경로는 writer 세션, 조회 경로는 read-only 세션을 사용한다 — REQ-001
- C-2: 라우터·모델은 `main.py` 직접 등록이 아니라 `apps.py` + `config.INSTALLED_APPS` 로만 합류한다 — passive-style 기준 구조
- C-3: migration 과 runtime 은 같은 App Registry 모델 집합을 사용한다 — passive-style 기준 구조
- C-4: ADR-019 로깅 계약(console + RotatingFileHandler)과 `tests/utils/test_logs.py` 를 이번 그룹에서 변경하지 않는다 — ADR-003
- C-5: SQL bind 파라미터를 포함한 secret 은 어떤 application handler 에도 출력되지 않는다 — REQ-002 (default F-008)
- C-6: 통합 테스트는 공유 MySQL 인스턴스를 건드리지 않고 전용 compose 인스턴스만 사용한다 — ADR-004
- C-7: 검수 게이트와 자식 프로세스 stdio 는 UTF-8 로 고정한다 — REQ-002 (default F-016/F-017)
- C-8: 문서가 참조하는 파일 경로·심볼·환경변수는 실재해야 하며 기계 검사로 보호한다 — REQ-002 (default F-018)
- C-9: `.env.example` 은 그대로 `.env` 로 복사해도 Settings 검증을 통과해야 한다 — REQ-004 (F-006)
- C-10: production/staging 에서 무인증 `/admin` 은 명시적 승인 없이 열리지 않는다 — REQ-004 (F-007, ADR-007)
- C-11: `app/utils` 는 상위 계층을, `app/core` 는 `app/features` 를 import 하지 않는다. 기능 간 직접 의존은 문서화된 예외만 허용한다 — REQ-004 (AST 계층 검사)
- C-12: 일반 500 응답은 DEBUG 에서도 `str(exc)` 를 싣지 않는다. Repository 예외의 `detail` 도 원본 DB 메시지를 담지 않는다 — REQ-005 (F-010·F-011)
- C-13: 앱 로거는 예외 **메시지**를 보간하지 않는다(타입만). `sql_noise` 는 로거 이름으로 거르므로 `app.*` 로거의 `{e}` 는 필터를 통과한다 — REQ-005 (F-012)
- C-14: `LOG_SQL_ECHO_ENABLED` 는 development/test 에서만 허용한다 — REQ-005 (F-013)
- C-15: 테스트 DB 컨테이너는 loopback 에만 publish 한다 — REQ-005 (F-014)
- C-16: startup 실패와 정상 shutdown 은 **같은 cleanup 경로**를 탄다. cleanup 하나가 실패해도 나머지는 실행된다 — REQ-007
- C-17: 쓰기 경로는 `get_writer_db_session`, 조회는 `get_read_only_db_session` 을 쓴다. routed 세션은 예외 경로 전용이다 — REQ-007 (C-1 구체화)
- C-18: FastAPI 자원 관리자와 Celery worker 종료는 서로의 자원을 닫지 않는다 — REQ-007 (프로세스 소유권 분리)
- C-19: 공통 필드는 Mixin 으로만 제공하고, 모델에 같은 컬럼을 다시 선언하지 않는다. 컬럼 배치는 id → 도메인 → created_at → updated_at 로 고정한다 — REQ-008 (ADR-014)
- C-20: DB 예외는 Repository·commit 경계에서 변환기를 거치고 원본을 이어붙이지 않는다(`from None`) — REQ-009 (ADR-015)
- C-21: 행의 존재 여부를 `rowcount` 로 판단하지 않는다 — REQ-009 (F-021)
- C-22: `BaseRepository` 공개 메서드는 정확히 8개다. 늘리려면 이 제약과 charter 를 함께 고친다 — REQ-010 (ADR-016)
- C-23: Raw 구문의 읽기/쓰기는 intent 로만 판정한다. intent 없는 `TextClause` 는 reader 로 보내지 않는다 — REQ-011 (ADR-017)
- C-24: `text()` 인자에 f-string·`%`·`.format()`·문자열 연결을 쓰지 않는다. `query_name` 은 코드 상수다 — REQ-011 (ADR-018)
- C-25: SQL 문자열은 Raw Repository 만 소유한다. View·Service·Dependency 는 `text()` 를 부르지 않는다 — REQ-012 (ADR-002)
- C-26: 예제 두 개는 Repository 를 제외한 모든 계층이 같은 구조를 유지한다 — REQ-012 (Phase 5 완료 조건)
- C-27: 공개 DTO class 이름은 전역 고유하며 OpenAPI schema key 에 `__` 가 나타나지 않는다 — REQ-013 (ADR-021)
- C-28: 태그 선언과 사용이 정확히 일치하고, 구현된 기능에 '미구현/예정' 설명이 없다 — REQ-013 (DOC-004)
- C-29: OpenAPI 규칙은 각각 fail-on-revert 로 동작을 증명한다 — REQ-013 (ADR-022)
- C-30: 문서가 참조하는 심볼·경로·환경변수는 실재해야 한다(변경 이력 제외) — REQ-014 (DOC-006)
- C-31: 검수 게이트는 병렬로 돌려도 서로의 캐시·소스를 밟지 않는다 — REQ-014 (ADR-023)
- C-32: 저장소 blob 과 작업트리의 줄바꿈은 LF 다(`.bat`/`.cmd` 제외) — REQ-015
- C-33: Playwright 는 async API 만 쓴다 — REQ-015 (ADR-024)

## 5. 변경 이력
- v0.1 (2026-08-18): 최초 작성. REQ-001~003, ADR-001~004, C-1~C-8 등재.
- v0.2 (2026-08-18): Round 1(착수 게이트) 반영. REQ-004, ADR-005~007, C-9~C-11 등재.
- v0.3 (2026-08-18): Round 2(Phase 0) 반영. REQ-005, ADR-008~010, C-12~C-15 등재.
- v0.4 (2026-08-19): Round 3(Phase 1) 반영. REQ-006~007, ADR-011~013, C-16~C-18 등재.
- v0.5 (2026-08-19): Round 4(Phase 2) 반영. REQ-008, ADR-014, C-19 등재.
- v0.6 (2026-08-19): Round 5(Phase 3a) 반영. REQ-009, ADR-015, C-20~C-21 등재. **F-015 닫힘.**
- v0.7 (2026-08-19): Round 6(Phase 3b) 반영. REQ-010, ADR-016, C-22 등재. **Phase 3 완료.**
- v0.8 (2026-08-19): Round 7(Phase 4) 반영. REQ-011, ADR-017~018, C-23~C-24 등재. **Phase 4 완료.**
- v0.9 (2026-08-19): Round 8(Phase 5) 반영. REQ-012, ADR-019~020, C-25~C-26 등재. **Phase 5 완료.**
- v0.10 (2026-08-19): Round 9(Phase 6) 반영. REQ-013, ADR-021~022, C-27~C-29 등재. **Phase 6 완료.**
- v1.0 (2026-08-19): Round 10(Phase 7) 반영. REQ-014, ADR-023, C-30~C-31 등재. **전체 작업 완료** — 완료 보고서는 `completion-report.md`.
- v1.1 (2026-08-19): Round 11 반영. REQ-015, ADR-024, C-32~C-33 등재. **R-011(줄바꿈)·잔여위험 4번(Scalar 렌더링) 해소.**
