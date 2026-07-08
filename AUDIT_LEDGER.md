# AUDIT_LEDGER — 감사 작업 원장 (append-only)

> 이 원장은 감사 실행 전반에 걸쳐 **append-only**로 유지된다. 코드를 바꾸는 모든 작업 단위마다
> 작업 식별자·대상·변경 전후 상태·설계 결정·검증 결과·회귀 위험을 기록한다.
> 규칙: 사용자 프롬프트 5.6 참조.

---

## 실행 #1 — 2026-07-08 (branch: audit/full-review-2026-07-08)

### 0단계 베이스라인 (수정 전 상태)

| 항목 | 결과 |
|---|---|
| 작업 트리 | clean (main) |
| 패키지 매니저 | uv (uv.lock) |
| Python(런타임) | 3.14.4 (uv venv) / pyproject requires >=3.12 |
| 감사 브랜치 | audit/full-review-2026-07-08 |
| **pytest** | **68 passed** (4.78s) — 회귀 판단 기준선 |
| ruff check (기본 select) | 클린 (0 findings) |
| ruff check --extend-select=S | S104 1건(0.0.0.0 bind), S101 144건(대부분 tests) |
| mypy | **49 errors / 12 files** |
| bandit | 미설치 → `uv run --with bandit` 로 임시 실행 예정 |

프로젝트 성격: "FastAPI project structure with Django-style INSTALLED_APPS registration"
(레이어드: domains/<d>/{api,services,repositories,models,schemas,dependencies} + core 인프라)

### 정적 분석 최종 집계 (수정 전)
- ruff: 기본 select 클린 / 보안 S: S104 1건(main.py:11 0.0.0.0), S101(assert)은 테스트 한정
- bandit: B104 1건(main.py:11) — dev 진입점 0.0.0.0 바인딩 (Medium/Medium)
- mypy: 49 errors / 12 files
  - repository_base.py: `type[ModelType].id` 8건(Base에 id 없음, UUIDMixin에만), `Result.rowcount` 6건, no-any-return 5건, selectinload(str) 1건(중첩관계 경로)
  - pagination.py: `ModelT.id`(무바운드), `T.model_fields`(무바운드)
  - 도메인 라우터 responses dict 15건(`dict[int, dict[str, object]]` 불일치)
  - filters.py:41 FrameType|None 대입, user_info_middleware.py 2건, home/admin.py 2건, celery/tasks.py 1건, celery import-untyped 1건

### FastAPI 특화 점검 결과
- async 라우트 블로킹 IO: **없음** (requests/time.sleep/open/socket 0건). user_agents 파싱은 경량 CPU.
- response_model: 모든 엔드포인트에 명시됨(양호).
- CORS: 기본값 안전(origins=["*"]지만 credentials=False 기본). 위험 조합 방어는 런타임 가드 부재 → 설계 권고.
- 예외 처리: 조용한 삼킴/bare except 없음. background 로그 저장의 except Exception은 의도적(요청 비블로킹).
- DI: get_<d>_service 가 yield 후 commit, 예외 시 get_session teardown 이 rollback — 일관적.
- N+1: 단순 CRUD 경로엔 없음. Eager-loading 헬퍼(BaseRepository) 제공됨.

### 5.1 의도 학습 (요약)
- 목적: "Django INSTALLED_APPS 스타일 수동 등록"으로 도메인 앱을 결선하는 FastAPI 구조 템플릿.
- 아키텍처: Router → Depends(get_<name>_service) → Service → Repository → DB. UnitOfWork 제거, 트랜잭션 경계는 dependency.
- 코드 ↔ 문서 정합성: 대체로 높음(README/config API_DESCRIPTION 이 실제 구조와 일치).
- 드리프트: UUIDMixin/TimestampMixin 이 문서엔 사용 예시가 있으나 실제 모델은 미사용(중복 정의).

### 전수 재검수 (실행 #1 추가 — 사용자 요청 "확실히 검수")
사용자 확인 요청에 따라 (1)ARCHITECTURE 정정 (2)미정독 파일 전수 로직 리뷰 (3)런타임 스모크 수행.

- **리뷰 방식**: blog/sns/reply + utils/core 잡파일을 병렬 리뷰 서브에이전트 2기로 전수 정독, home/스키마/예외는 직접 확인.
- **발견(수정)**: `[86c8410]` 빈 PATCH 바디 `{}` → HTTP 500 (BaseRepository.update 빈 SET 절 CompileError). 전 도메인 공통 latent 버그 → no-op 가드 + 회귀 테스트.
- **발견(수정)**: `[c7dcc9b]` 문서 드리프트 — docs/ARCHITECTURE.md 전면 재작성(pre-refactor 서술: app/apps.py·UoW·app/shared·worker/), main.py·new_app.py docstring 정정.
- **저위험 관찰(미조치)**: auth.py·redis.py 빈 스텁(미import), 로깅 3건 Low(config.py:47 파일명 날짜 startup 고정 / setup.py `_configured` 락없음 / formatters DST 경계) — 동작 무해, 의도 확인 대상.
- **스모크(3)**: docker/compose/Dockerfile 없음 + MySQL 3306·Redis 6379 미리슨 → 실스택 부팅 불가. **달성 최선**: (a) create_app() DB없이 조립 성공(라우터 5·경로 15), (b) 인프로세스 E2E(httpx ASGI, sqlite) **13/13 통과**(health·user CRUD happy+409+422+404·blog·home stats·204). 한계: sqlite 백엔드(MySQL 방언 미검증).
- **미해결(대규모, 결정 대기)**: docs/concepts/ 3개 dated 문서(+HTML 쌍둥이)가 현행 main과 불일치(UoW/app/apps.py/auto-discovery). 처리 방향(갱신/아카이브 배너/삭제) 사용자 결정 필요.

### 작업 로그

#### [94a6894] 2026-07-08 · fix(types): mypy 49건 해소
- 대상: models_base.py, repository_base.py, pagination.py, filters.py,
  user_info_middleware.py, celery/task.py, home/admin.py, 5개 도메인 라우터, pyproject.toml(mypy override)
- 변경 전 문제: mypy 49 errors(제네릭 id 미선언, Result.rowcount, no-any-return, 무바운드 TypeVar, responses dict 등)
- 설계 결정: (1) `id` 는 실제로 모든 모델이 갖는 불변식이므로 Base 에 TYPE_CHECKING 전용 계약 선언(런타임 무변경).
  (2) rowcount 는 DML 에서 CursorResult 로 cast. (3) type:ignore 미사용 원칙 준수.
- 변경 후 상태: mypy 0/135. 인지 사항: 중첩 eager-loading·pagination 자동변환은 관계/사용처가 없어 실사용 테스트 불가(타입만 정합).
- 검증: mypy 0, ruff clean, pytest 68 passed(베이스라인 68 동일 → 회귀 없음).
- 관계: 신규(정적 품질 개선). 회귀 위험 없음(동작 보존).

#### [0087fbc] 2026-07-08 · fix(security): B104 dev-server 바인드 이전
- 대상: config.py(AppSettings HOST/PORT), main.py, .env.example, (pyproject 포함)
- 변경 전 문제: main.py 하드코딩 host="0.0.0.0" → bandit B104(all-interfaces).
- 설계 결정: 안전 기본값(127.0.0.1)을 설정으로 두고 배포는 HOST=0.0.0.0 env 주입.
  코드에서 all-interfaces 리터럴 제거 → B104 소멸.
- 변경 후 상태: bandit 0. 인지 사항: `python main.py` 기본 바인드가 루프백으로 바뀜(동작 변경, 보고서 명시).
- 검증: bandit 0, mypy 0, ruff clean, pytest 68 passed(회귀 없음).
- 관계: 신규(보안 하드닝). 회귀 위험: 개발 편의(외부 접속) 축소 — 배포 env 로 복원 가능.

> 참고: 커밋 5c7b6cc(chore: align project name)는 감사 시작 전 사용자 본인 커밋으로 감사 범위 밖.

### 5.6.2 회귀 방지 비교 검수 표

| 항목 | 이전 작업의 상태·문제 인식 | 현재 방향의 상태·문제 인식 | 회귀 여부 | 판단·근거 |
|---|---|---|---|---|
| 백그라운드 로그 drain (W1) | 이전 감사에서 shutdown drain 도입(유실 방지) | 변경 없음 — 그대로 유지 | 없음 | 건드리지 않음 |
| Celery 영속 이벤트 루프 (C1) | asyncio.run 매회 → loop closed 오류 해결 | run_async 제네릭化(타입만) — 루프 로직 불변 | 없음 | 런타임 동작 보존 |
| UnitOfWork 제거 | 이전에 UoW 제거, dependency 가 트랜잭션 경계 | 변경 없음 | 없음 | 구조 유지 |
| dev 서버 바인드 | 이전엔 main.py 하드코딩 0.0.0.0 | 설정 기반 + 기본 127.0.0.1 | 없음(개선) | 보안 하드닝, 배포 env 로 복원 가능 |
| mypy 미적용 | 이전엔 49건 방치(strict=false) | 0건 — 타입 계약 보강 | 없음 | 동작 보존, type:ignore 미사용 |

### 설계 결정 필요(자동 미적용) 목록
1. UUIDMixin/TimestampMixin 미사용(각 모델이 id/created_at 중복 정의) — 채택 or 제거 결정 필요.
2. eager-loading/pagination 제네릭 기계 미사용(관계 0개) — 템플릿 스캐폴딩 유지 vs 축소.
3. CORS origins=["*"]+credentials=True 런타임 가드 부재 — validator 추가 권고(기본값은 안전).
4. dev 바인드 기본값 127.0.0.1 변경 — README uvicorn CLI 예시(--host 0.0.0.0)와 정책 정합 확인 필요.
5. 저장소 전역 ruff format 미적용(58파일) — 감사 diff 오염 방지로 미적용, CI/일괄 포맷 권고.
6. 문서 경미 드리프트: README `/by-ip/{ip}` ↔ 코드 `{ip_address}`.

---

## 실행 #1 후속 — 승인 기반 개선 적용 (2026-07-08)

사용자 승인 범위: A(CI/pre-commit) + B(전역 포맷) + C1(믹스인 채택). **CORS 가드는 제외**
(리버스 프록시 nginx 계층에서 처리 가능한 설정이라 앱 레벨 미적용). C2(믹스인 제거)는
C1과 상호배타 → C1이 대체(supersede).

#### [a63dcbd] refactor(models): 믹스인 채택 (설계 결정 #1 해소)
- 대상: 5개 도메인 models.py. UUIDMixin/TimestampMixin 을 실제 상속 → 미사용 죽은코드 + id/created_at 중복 제거.
- 회귀 검수: 이전 감사엔 관련 결정 없음(신규). 컬럼 정의 동일, 물리 순서만 이동(이름 접근이라 무관, Alembic 이름 비교로 드리프트 없음).
- 검증: ruff clean, mypy 0, pytest 68(회귀 0).

#### [161fc0a] style: 전역 ruff format (설계 결정 #5 해소)
- 대상: 56파일 재포맷(포맷 전용). CI 의 format --check 게이트 선행.
- 검증: ruff/format clean, mypy 0, pytest 68.

#### [a24cecd] ci: 품질 게이트 + pre-commit (다음 단계 #1 이행)
- 대상: .github/workflows/ci.yml, .pre-commit-config.yaml, pyproject(bandit dev편입 + ruff S룰 + tests S101 예외), uv.lock.
- 검증(CI 동등): ruff clean, format clean, mypy 0, bandit 0, pytest 68.

### 잔여 설계 결정(미적용, 사용자 판단 대기)
- #2a **pagination** — **적용**: app/utils 로 이전 + dataclass화(아래 70295ba).
- #2b **eager-loading 8메서드** — **의결·종결**: BaseRepository는 기반 계층이라 미사용이 정상(확장점).
  **현행 유지 + 목적 주석**으로 결정. 설계안(`EAGER_LOADING_DESIGN.html`)은 향후 관계 도입 가이드로 존속.
  검증: ruff/format/mypy clean, pytest 78 passed(동작 무변경).
- #3 CORS 런타임 가드 — **nginx 계층 처리로 제외 확정**(앱 미적용).
- #6 README `{ip}`↔`{ip_address}` 표기차 — 문서 경미 드리프트(대량 편집 회피).

#### [70295ba] refactor(pagination): utils 이전 + dataclass화 (설계결정 #2a 해소)
- 대상: app/utils/pagination.py(신규), app/shared/**(제거), tests/utils/test_pagination.py(신규 10케이스).
- 사용자 결정: PaginatedResponse 를 **표준 @dataclass**로 구현(안티패턴 경고 인지 후 선택).
  안티패턴(제네릭 stdlib dataclass 를 FastAPI response_model 로 직접 노출 시 OpenAPI
  스키마/검증 약화)은 모듈 docstring 에 경계 변환 권고로 명시. Paginator 는 인스턴스화형.
- 회귀 검수: 이전(미사용 스캐폴딩) → 현재(테스트된 유틸). 외부 참조 없어 삭제 안전. 회귀 없음.
- 검증: ruff clean, format clean, mypy 0/133, pytest 78 passed(기존 68 + 신규 10).
