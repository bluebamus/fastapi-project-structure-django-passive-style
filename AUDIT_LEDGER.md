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

### 작업 로그
(이하 append)
