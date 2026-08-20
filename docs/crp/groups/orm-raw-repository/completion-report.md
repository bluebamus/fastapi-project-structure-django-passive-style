# ORM/Raw Repository 고도화 — 완료 보고서

| 항목 | 값 |
|---|---|
| 작업 그룹 | `orm-raw-repository` |
| 기간 | 2026-08-18 ~ 2026-08-19 |
| 근거 문서 | `docs/orm-raw-repository/2026-08-13/` (요구명세·개발계획서·워크플로 지침서) |
| 브랜치 | `feat/orm-raw-repository-phase0` |
| 라운드 | 0 ~ 10 (Phase 0 ~ 7) |
| 최종 상태 | **전체 통과** — 열린 결함 0건 |

---

## 1. 무엇을 만들었나

목표는 하나였다 — **ORM 과 Raw SQL 이 Repository 구현에서만 갈라지는 구조**. DI·Service·
세션 선택·트랜잭션 경계·DTO 검증·라우터 조립·문서·예외 처리는 양쪽이 같아야 한다.

그 주장을 문장이 아니라 **기계 검사**로 만들었다. `tests/test_orm_raw_parity.py` 가 두
예제의 구조를 대조한다 — 같아야 하는 것(디렉터리·Service base·세션 선택·commit 위치·
`response_model`)과 달라야 하는 것(Repository base·SQL 소유·`from_attributes`·명시적 row
검증)을 각각 고정한다.

### 산출물

| 계층 | ORM | Raw |
|---|---|---|
| Base | `repository_base.py` (289줄, 공개 8개) | `raw_crud_base.py` + `raw_repository_base.py` |
| 예제 기능 | `app/features/catalog/` — 상품 CRUD | `app/features/reports/` — 일별 매출 집계 |
| 반환 | ORM 모델 → `from_attributes` | `RowMapping` → `dict(row)` 명시 검증 |
| migration | `catalog_products` | `sales_orders` |

두 기능 모두 `config.INSTALLED_APPS` 등록만으로 붙는다. `main.py` 는 이번 작업에서 한 줄도
바뀌지 않았다.

---

## 2. 실행한 검증

| 게이트 | 결과 |
|---|---|
| `ruff format --check` | 통과 (317 files) |
| `ruff check` | 통과 |
| `mypy` | 통과 (202 files) |
| `bandit` MEDIUM 이상 | 0건 (231 files) |
| `pytest` (전체) | **594 passed / 0 skipped** · coverage **92%** |
| MySQL 8.4 통합 | **15건 실제 실행** — skip 0 |
| alembic drift | 0 (MySQL `compare_metadata` 직접 비교) |
| OpenAPI 규칙 fail-on-revert | **20/20 감지** |
| Scalar 실렌더링 (Chromium) | **7건 통과** — 태그 9개·Markdown 표·예시 값 |
| 검수 게이트 병렬 3회 | 전부 통과, 잔해 없음 |

한 명령으로 재현한다:

```powershell
uv run python -m scripts.review_gate          # 8단계 전부
uv run python -m scripts.review_gate --fast   # MySQL 제외 (제외 사실이 출력에 남는다)
```

MySQL 통합은 **skip 을 실패로 본다**. 인프라가 없어 안 돈 것과 돌아서 통과한 것은 다르고,
그 차이가 보이지 않으면 "전체 green" 이 거짓말이 된다. 컨테이너를 내리고 돌려 실제로
실패하는 것(종료 코드 1)까지 확인했다.

---

## 3. 닫은 결함 28건

전부 Fixed. 심각도별로 대표만 적는다 — 전체는 `ledger.md`.

### HIGH (4건)

| ID | 무엇이 문제였나 |
|---|---|
| F-003 | 통합 테스트가 **다른 저장소의 컨테이너**에 붙어 스키마를 지웠다. 포트만 나눈 격리가 원인 — DB명·계정으로 격리하도록 바꿨다(ADR-006) |
| F-011 | `detail={"error": str(e.orig)}` 가 **응답으로 나갔다**. 중복키 오류 하나로 실행 SQL 과 바인딩 값이 API 클라이언트에 전달되던 경로 |
| F-016 | startup 이 깨지면 아무것도 닫지 않고 예외만 올라가 커넥션이 샜다. `AsyncExitStack` 으로 실패·정상 경로를 하나로 합쳤다 |
| F-022 | `_is_write()` 가 ORM flush 와 Core `UpdateBase` 만 봐서 **`text("UPDATE ...")` 가 read-only 세션을 통과**했다. SQL 을 파싱하는 대신 호출부가 intent 를 붙이도록 바꿨다(ADR-017) |

### 이번 작업의 성격을 보여주는 결함

- **F-015** — `raise ... from e` 로 원인을 이어 두면 위에서 누가 `logger.exception` 을
  부르는 순간 traceback 에 SQL 과 값이 통째로 찍힌다. 그 로거 이름은 `app.*` 이라 SQL 필터도
  통과한다. 경계에서 `from None` 으로 끊었다.
- **F-020** — declarative mixin 컬럼이 뒤로 밀려 `id` 가 중간에 끼었다. Alembic 은 컬럼을
  이름으로 비교해 순서를 diff 로 잡지 않으므로 `alembic check` 는 통과한다 — 개발 DB 와
  운영 DB 가 **아무 경고 없이** 갈리던 상태. MySQL `SHOW CREATE TABLE` 실측으로 발견했다.
- **F-025** — `UserResponse` 가 두 모듈에 있어 OpenAPI 가 모듈 경로를 schema key 로
  내보냈다. 그 key 는 파일을 옮기면 바뀐다 — 클라이언트가 통째로 깨진다.
- **F-028** — 작성한 OpenAPI 규칙 24건이 전부 초록불이었지만, 결함을 주입해 보니 **셋이
  아무것도 검사하지 않고 있었다**. FastAPI 가 `summary`·`operationId` 를 자동으로 채우기
  때문이다. 게다가 `app.routes` 직접 순회가 기능 라우트를 하나도 보지 못했다.
- **F-029** — 검수 게이트를 3개 동시에 돌리자 fail-on-revert 하네스끼리 서로의 소스 수정을
  밟아 `tags_metadata.py` 에 주입 문구가 남았다. `finally` 복구만으로는 못 막는다.

---

## 4. 실행하지 않은 검증

"전체 green" 은 **실행된 테스트만** 의미한다. 아래는 이번 작업에서 **돌리지 않은** 범위다.

| # | 항목 | 왜 안 했나 / 무엇이 필요한가 |
|---|---|---|
| 1 | 부하·성능, 커넥션 풀 고갈, 동시성 한계 | 부하 도구와 운영급 데이터가 필요하다 |
| 2 | Raw 집계의 **실행 계획**(`EXPLAIN`) | 소량 데이터에서는 옵티마이저가 전체 스캔을 고르는 것이 정상이라, 의미 있는 검증에 데이터 규모가 필요하다 |
| 3 | **실제 replica** 를 붙인 라우팅·복제 지연 | 라우팅은 로컬 SQLite 엔진 두 개로 "어느 쪽이 처리했는가"만 증명했다. 복제 지연 자체는 재현하지 않았다 |
| 4 | 실제 **Celery worker** 기동 | `worker_process_shutdown` 훅은 단위 테스트로만 확인했다 |
| ~~5~~ | ~~Scalar 브라우저 렌더링~~ | **해소** — Playwright + Chromium 으로 검증한다(`pytest -m browser`, 7건). 게이트 8단계에 포함 |
| ~~6~~ | ~~CI workflow 실제 실행~~ | **해소**(2026-08-19) — push 후 실제 실행. 두 job(GATE 3 · MySQL 8.4 통합) 모두 success. 첫 실행에서 결함 3건이 드러나 고쳤다(아래 §8) |
| 7 | `/ready` 와 Celery 종료 훅의 **실제 프로세스** 동작 | 코드 경로는 테스트했지만 running process 에서 확인하지 않았다 |

---

## 5. 수용한 잔여 위험

전체는 `residual-risk.md`. 여기서는 **다음 사람이 알아야 할 것**만 적는다.

| ID | 내용 | 상태 |
|---|---|---|
| R-001 | `/admin` 에 인증 백엔드가 없다 | 영구 비목표. production/staging 은 `ADMIN_UNAUTHENTICATED_ACK` 미승인 시 **기동 거부**(F-007) |
| R-004 | SQLite 단위 테스트는 MySQL 방언 정확성의 근거가 아니다 | 방언은 `pytest -m mysql` 로만 승인 (ADR-004) |
| R-008 | WSL MySQL 컨테이너가 healthy 직후 종료 코드 255 로 죽는 일이 있었다 | **원인 미상**. Phase 5~7 내내 재현되지 않아 관찰만 유지 — 닫지 않았다 |
| R-010 | `text()` 보간을 **전면 금지**로 잠갔다 | 요구명세는 allowlist 상수의 f-string 구성을 허용한다. 지금은 그런 호출부가 없어 가장 좁은 규칙을 택했다. 필요해지면 ADR 로 연다 |
| ~~R-011~~ | ~~`.gitattributes` 부재 + 줄바꿈 혼재~~ | **해소**(2026-08-19) — `* text=auto eol=lf` 로 고정하고 blob 5개·작업트리 30개를 LF 로 정규화했다 |

---

## 6. 되돌리기 어려운 결정 (ADR 22건)

전체는 `design-baseline.md` §3. 다음 사람이 뒤집으려면 **새 ADR 이 필요한** 것들:

| ADR | 결정 | 뒤집으면 생기는 일 |
|---|---|---|
| ADR-002 | ORM/Raw 는 Repository 구현만 분기한다 | 예제 두 개의 존재 이유가 사라진다 |
| ADR-008 | 커밋은 **쓰기 View 본문**이 한 번 한다 | 커밋 지점이 여러 곳이면 부분 커밋 상태가 생기고 재현이 어렵다 |
| ADR-016 | `BaseRepository` 공개 계약은 **정확히 8개** | 넓히면 Raw 에서 같은 것을 다시 구현해야 한다 |
| ADR-017 | Raw 의 읽기/쓰기는 **intent** 로만 판정, 미분류는 쓰기(fail-closed) | 첫 토큰 파싱으로 돌아가면 CTE DML 이 replica 로 샌다 |
| ADR-021 | 공개 DTO 이름은 **전역 고유** | schema key 가 모듈 경로로 노출되고, 파일을 옮기면 클라이언트가 깨진다 |
| ADR-022 | 문서 품질 규칙은 "비었는가"가 아니라 **"사람이 썼는가"** | 규칙이 절대 실패하지 않는 장식이 된다 |

---

## 7. 다음 사람이 먼저 할 일

1. 새 기능을 만들 때는 `catalog`(ORM) 또는 `reports`(Raw) 를 통째로 복사하는 것이 가장
   빠르다. 두 기능은 그러라고 만들어졌다.

---

## 8. CI 첫 실행에서 드러난 것 (2026-08-19)

"한 번도 실행되지 않은 CI" 를 잔여 위험으로 적어둔 이유가 그대로 나타났다. push 하자
**결함 3건**이 드러났고, 전부 워크플로 쪽이었다 — 애플리케이션 코드는 멀쩡했다.

| # | 무엇이 | 왜 몰랐나 |
|---|---|---|
| 1 | GATE 3 이 마커 없이 `pytest` 를 돌려 인프라 테스트까지 포함했다. 브라우저 테스트가 DB 없이 uvicorn 을 띄우다 실패하고, mysql 은 skip 되어 "SKIP 0건" 검사에서 또 걸렸다 | 로컬 게이트는 처음부터 마커로 나눠 돌렸다. 두 게이트가 같은 일을 다르게 하고 있었다 |
| 2 | `deselected` 를 위반으로 셌다. `-m mysql` 은 나머지를 정상적으로 deselect 하므로 **성공 실행에도 항상** 나타난다 | 로컬 게이트에서 똑같은 실수를 하고 고쳤는데 CI 에는 반영하지 않았다. 같은 판정 로직이 두 곳에 있으면 이렇게 갈린다 |
| 3 | MySQL job 이 정확히 20분에 잘렸다(08:47:00 → 09:07:20). `--with-deps` 가 apt 패키지까지 받는데 앞 단계들이 이미 15분을 썼다 | 브라우저 단계를 로컬에서만 재보고 러너 예산을 다시 계산하지 않았다 |

4번도 있었다. 캐시 히트일 때만 `playwright install-deps` 를 부르도록 분기했더니 **그
경로에서 35분간 멈춰** 또 잘렸다(apt 가 무언가를 기다린 것으로 보인다). 캐시 미스로
`install --with-deps` 를 통째로 돌린 실행은 같은 job 이 3분 9초에 끝났다 — 분기가
아낀 것은 없고 위험만 만들었다. 검증된 쪽만 남겼다.

고친 뒤 두 job 모두 success(약 100초). 브라우저 바이너리는 `actions/cache` 로
재사용한다(키: `uv.lock` 해시).

**교훈은 2번이다.** 같은 판정 규칙을 로컬 게이트와 CI 두 곳에 손으로 적어두면 반드시
갈린다. 다음에 게이트 규칙을 바꾸는 사람은 `scripts/review_gate.py` 와
`.github/workflows/ci.yml` 을 **함께** 봐야 한다.