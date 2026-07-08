# 코드 감사 보고서 — 실행 #1

- **대상**: `fastapi-project-structure-django-passive-style` (FastAPI, Django INSTALLED_APPS 스타일 수동 등록 템플릿)
- **일자**: 2026-07-08
- **브랜치**: `audit/full-review-2026-07-08` (main 직접 커밋 없음)
- **패키지 매니저**: uv · Python 3.14(venv), pyproject `requires-python >=3.12`
- **상세 작업 이력·회귀 검수 표**: [`AUDIT_LEDGER.md`](AUDIT_LEDGER.md) 참조(append-only 원장)

---

## 1. 요약

| 지표 | 베이스라인(수정 전) | 수정 후 |
|---|---|---|
| pytest | 68 passed | **68 passed** (회귀 0) |
| ruff check | 클린 | 클린 |
| mypy | **49 errors / 12 files** | **0** |
| bandit (Medium+) | **1 (B104)** | **0** |

- **발견**: 정적 결함 50건(mypy 49 + bandit 1) + 설계/구조 관찰 6건
- **수정**: 정적 결함 50건 전부 해결(원자적 커밋 2개), 동작 보존 원칙
- **보류(설계 결정 필요)**: 6건 (아래 §5 및 원장)
- **설치한 도구**: `bandit`(임시 실행 `uv run --with bandit`, 프로젝트 의존성 미변경). ruff/mypy 는 기존 dev 의존성.

**커밋**
- `94a6894` fix(types): resolve all 49 mypy errors without behavior change
- `0087fbc` fix(security): move dev-server bind address to settings (bandit B104)

---

## 2. 심각도별 발견 목록

### Critical / High
없음. (인증·인가·SQL 인젝션·RCE·비밀정보 유출 등 고위험 결함 미발견. ORM 은 전부 파라미터 바인딩, 하드코딩 시크릿 없음.)

### Medium
| # | 위치 | 문제 | 조치 |
|---|---|---|---|
| M1 | `main.py:11` | dev 진입점 `host="0.0.0.0"` 하드코딩(bandit B104, all-interfaces 바인딩) | **수정**: `AppSettings.HOST/PORT` 신설, 기본 `127.0.0.1`, 배포는 `HOST` env 주입. `0087fbc` |

### Low (mypy 타입 정확성 — 런타임 잠재 결함/유지보수성)
| # | 위치 | 문제 | 조치 |
|---|---|---|---|
| L1 | `repository_base.py` ×8 | 제네릭 `type[ModelType].id` 미선언(Base 에 id 없음) | **수정**: Base 에 TYPE_CHECKING 전용 `id: Mapped[str]` 계약 선언(런타임 무변경) |
| L2 | `repository_base.py` ×6+5 | `Result.rowcount` 미노출 + no-any-return | **수정**: DML 결과를 `CursorResult` 로 cast |
| L3 | `repository_base.py:123` | 중첩 eager-loading 이 문자열 관계명 사용(SQLAlchemy 2.0 체인 로더 규약 위반, 잠재 런타임 오류) | **수정**: 대상 매퍼의 실제 속성으로 체이닝(관계 0개라 실사용 경로는 없음) |
| L4 | `pagination.py:178,218` | 무바운드 TypeVar 로 `model.id`/`model_fields` 타입 실패 | **수정**: `T=BaseModel`, `ModelT=Base` 바운드 |
| L5 | `user_info_middleware.py:258` | `add_middleware(UserInfoMiddleware)` 팩토리 시그니처 불일치 | **수정**: `__init__(app: ASGIApp)`, `call_next: RequestResponseEndpoint` |
| L6 | `filters.py:41` | `frame` 재대입 시 `FrameType | None` 불일치 | **수정**: 변수 타입 명시 |
| L7 | 도메인 라우터 ×15 | `responses` dict 가 `dict[int, dict[str, object]]` 로 추론되어 FastAPI 시그니처와 불일치 | **수정**: `dict[int | str, dict[str, Any]]` 어노테이트 |
| L8 | `celery/tasks.py:22`, `celery/app.py:6` | no-any-return, celery import-untyped | **수정**: `run_async` 제네릭化 + mypy override(`celery.*`) |
| L9 | `home/admin.py:183-187` | SQLAdmin formatter `type` 인자 제약 | **수정**: `getattr` 접근(동작 동일) |

> mypy 는 `# type: ignore` 없이 전부 타입 힌트·시그니처 보강으로 해결했으며, 모든 수정은 런타임 동작을 바꾸지 않습니다(M1 제외 — 아래 명시).

---

## 3. FastAPI 특화 점검 결과

| 점검 항목 | 결과 |
|---|---|
| async 라우트 내 블로킹 IO | **없음** — `requests`/`time.sleep`/`open`/`socket` 등 동기 IO 0건. User-Agent 파싱은 경량 CPU. |
| response_model | 전 엔드포인트 명시(양호). |
| Pydantic 검증 공백 | Query 제약(`ge/le`) 적용, 글로벌 `RequestValidationError` 핸들러가 미검증 입력을 422 로 일관 처리. |
| CORS | 기본값 안전(`origins=["*"]`이나 `credentials=False` 기본). 위험 조합 런타임 가드는 부재(권고 §5). |
| Depends 오용 | `get_<d>_service` 가 세션 주입→서비스 구성→성공 시 commit, 예외 시 `get_session` teardown 이 rollback. 일관적. |
| ORM N+1 | 단순 CRUD 경로엔 없음. Eager-loading 헬퍼 제공(단 실제 관계 0개). |
| 예외 처리 | 조용한 삼킴/bare except 없음. background 로그 저장의 `except Exception` 은 의도적(요청 비블로킹, 로그 후 계속). |

---

## 4. 검증

- 각 코드 변경 직후 표준 게이트(ruff + mypy + 관련 테스트) 통과 확인(5.6.3).
- 최종: **ruff clean · mypy 0/135 · bandit 0 · pytest 68 passed**. 베이스라인(68) 대비 **회귀 0**.
- 커밋은 카테고리별 원자적 분리(fix(types) / fix(security)).

---

## 5. 설계·의도 정합성 검수 결과 (Step 5)

### 5.1 파악한 목적·핵심 설계
- **목적**: Django `INSTALLED_APPS` 스타일로 도메인 앱을 **명시적 수동 등록(passive)** 하는 FastAPI 구조 템플릿.
- **아키텍처**: `Router → Depends(get_<name>_service) → Service → Repository → DB`. UnitOfWork 제거, 트랜잭션 경계는 기능 의존성. 메인/백그라운드 커넥션 풀 분리, lifespan drain, 접속로그 미들웨어 + Celery 브리지.
- 문서(README 41KB, config `API_DESCRIPTION`)는 충실하며 코드 구조와 대체로 일치.

### 5.2 정합성 대조 (코드 ↔ 의도)
| 항목 | 결과 |
|---|---|
| INSTALLED_APPS 수동 등록 → 컨벤션 결선 | 구현·동작 일치 (registry.py) |
| 계층 경계(Router/Service/Repository) | 준수 — 라우터에 DB/비즈니스 로직 누수 없음 |
| home 접속로그 엔드포인트 5종 | 코드와 일치 (경미 표기차: `/by-ip/{ip}` ↔ `{ip_address}`) |
| /health·/docs(Scalar)·/admin | DEBUG/ADMIN 게이팅 문서와 일치 |
| 실행 커맨드(uvicorn CLI, `--host 0.0.0.0`) | 유효(CLI 플래그가 `__main__` 기본값보다 우선) |

### 5.3 설계·워크플로우 평가
- 관심사 분리·응집도 우수, 순환 의존 없음. 예외/로깅 일관성 양호(글로벌 핸들러 4종 + 컨텍스트 필터).
- 동시성: async 일관 사용, 트랜잭션 경계 명확, 백그라운드 러너 백프레셔·drain 견고, Celery 영속 루프로 aiomysql 커넥션 안전.
- 구조적 냄새: **미사용 스캐폴딩** 존재(아래 드리프트).

### 5.4 문서-코드 불일치 처리
- **UUIDMixin/TimestampMixin**: 문서엔 사용 예시가 있으나 실제 모델은 미사용(각자 id/created_at 중복 정의). **코드를 기준으로 판단**(테스트·실제 동작이 인라인 정의에 의존) → 자동 리팩터링은 MRO·컬럼 순서 위험으로 **보류**, 설계 결정 항목으로 분리.
- 표기차 `{ip}`↔`{ip_address}`: 기능 무관한 문서 표기차 → 41KB README 대량 편집 회피 위해 보고서에만 기록.

### 5.5 재검증
- 5단계에서 추가 코드 변경 없음(모두 §2 커밋에 포함). 게이트 재실행 결과 위 §4와 동일.

---

## 6. Human decision / 설계 결정 필요 목록 (권고 포함)

1. **미사용 믹스인(UUIDMixin/TimestampMixin)** — 권고: 모델을 믹스인 기반으로 통일하거나 믹스인 제거. 통일 시 컬럼 순서/마이그레이션 영향 검토 필요.
2. **미사용 제네릭 기계(eager-loading 8종 메서드, pagination 자동변환)** — 관계 0개 상태. 권고: 템플릿 스캐폴딩으로 유지하되 "관계 추가 전 미검증" 주석 명시, 또는 실제 관계 도입 시 테스트 추가.
3. **CORS 하드닝** — 권고: `CORSSettings` 에 `origins=["*"]` + `credentials=True` 동시 설정을 거부하는 validator 추가(기본값은 이미 안전).
4. **dev 바인드 기본값 변경(0.0.0.0 → 127.0.0.1)** — *동작 변경*. `python main.py` 로컬 실행이 루프백 바인드. 컨테이너/외부 노출은 `HOST=0.0.0.0` env 로 복원. README uvicorn CLI 예시와 정책 정합 확인 권고.
5. **시크릿/배포 값 주입** — 하드코딩 시크릿은 없었음. 단 `MYSQL_PASSWORD`/`REDIS_PASSWORD` 등은 배포 시 env 주입 필수(`.env.example` 참조). 신규 키 `HOST`/`PORT` 추가됨.
6. **저장소 전역 포맷 드리프트** — `ruff format --check` 기준 58개 파일(대부분 tests/utils, 감사 미수정 파일)이 미포맷. 감사 diff 오염 방지로 일괄 적용 보류 → 별도 포맷 커밋 권고.

---

## 6-B. 후속 개선 적용 결과 (사용자 승인 기반)

실행 #1 이후, 승인 범위에 따라 아래를 적용했습니다(**CORS 가드는 nginx 리버스 프록시 계층에서 처리 가능하므로 앱 레벨 제외**).

| 항목 | 조치 | 커밋 |
|---|---|---|
| 설계결정 #1 미사용 믹스인 | **적용(C1)**: 5개 모델이 UUIDMixin/TimestampMixin 상속 → 죽은코드·중복 해소. 동작 보존(컬럼 순서만 이동) | `a63dcbd` |
| 설계결정 #5 전역 포맷 | **적용(B)**: `ruff format` 저장소 전역(56파일), CI format 게이트 선행 | `161fc0a` |
| 다음단계 CI/pre-commit | **적용(A)**: GitHub Actions(ruff+format+mypy+bandit+pytest) + pre-commit + bandit dev편입 + ruff S룰(tests S101 예외) | `a24cecd` |
| 설계결정 #3 CORS 가드 | **제외**: nginx 계층 처리 영역 → 앱 미적용 | — |
| 설계결정 #2a pagination | **적용**: app/utils 로 이전 + 표준 @dataclass 컨테이너(초기값·`return cls()` 필드만) + 인스턴스화형 `Paginator` + 테스트 10케이스. app/shared 제거 | `70295ba` |
| 설계결정 #2b 미사용 eager-loading 8메서드 | **의결·종결**: `BaseRepository`는 기반(foundation) 계층으로 "미래 비즈니스 코드용 primitives" → 미사용은 결함이 아닌 확장점. **현행 유지 + 목적 주석 추가**(동작 무변경). 관계 도입 확장법은 `EAGER_LOADING_DESIGN.html` 참조 | `(아래 커밋)` |
| 설계결정 #6 README `{ip}` 표기차 | **보류**: 문서 경미 드리프트 | — |

검증(CI 동등, 최종): ruff clean · ruff format clean · mypy 0/135 · bandit 0 · pytest 68 passed(회귀 0).

---

## 7. 다음 단계 제안

- ✅ **CI 게이트 도입** — 적용됨(`a24cecd`): ruff+format+mypy+bandit+pytest.
- ✅ **pre-commit** — 적용됨(`a24cecd`).
- ✅ **ruff 보안 룰(S) 상시화** — 적용됨(`a24cecd`, tests S101 예외).
- ✅ **bandit dev 의존성 편입** — 적용됨(`a24cecd`).
- ⬜ **mypy 점진적 strict 화**: 현재 `strict=false`. 신규 코드부터 `disallow_untyped_defs` 상향 검토(권장).
- ⬜ **README 미세 드리프트 정정**(`{ip}`) 및 미사용 eager-loading/pagination 스캐폴딩 정책 결정.
- ⬜ **`pre-commit install`** 을 온보딩 문서(README)에 안내.

> pre-commit 훅 활성화: `uv run pre-commit install` (최초 1회).
