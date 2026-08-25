# Checklist — skeleton-purpose-audit

## Round 1 — 2026-08-25 · 목적 기준 검수 + 문서 정리

### 검수 (REQ-S02)

- [x] 이번 요청을 design-baseline §2 에 기록 (REQ-S01~S04) + 이전 요구 충돌 확인
- [x] CRP 그룹 6파일 적재
- [x] 목적 3요소를 실물로 판정 — INSTALLED_APPS SSOT · 라우터 파일 계층 · 자동 스캔 0건
- [x] (S-001) 생성기 골격이 게이트를 통과하지 못하는 것을 발견
- [x] (S-002·S-003) 설계 문서가 없는 기능(`require_admin`·`AppRegistry.discover()`)을
      가르치고 폐기된 트랜잭션 모델을 서술하는 것을 발견
- [x] (S-004·S-005) v1.1 내부 모순과 경로 오기 발견
- [x] (S-006·S-007) CI 주석·검사 면제 목록의 죽은 참조 발견

### 코드 수정 (ADR-S01·S04)

- [x] `scripts/new_app.py` 템플릿에 `operation_id` 추가
- [x] `next_steps()` 가 `tags_metadata.py` 에 붙여 넣을 항목을 출력
- [x] 회귀 검사 2건 추가 — 기존 하네스 재사용(새 스캐폴딩 없음)
- [x] **fail-on-revert 실증** — 되돌리면 자동 생성 operationId 로 실패하는 것을 확인 후 복구

### 삭제 (REQ-S03 · ADR-S02·S03)

- [x] `docs/orm-raw-repository/` (요구명세·개발계획·워크플로 지침 3종)
- [x] `docs/django-style-app-registry/DJANGO-STYLE-MANUAL-APP-INTEGRATION-PLAN.md`
- [x] `docs/django-style-app-registry/PRODUCTION-READINESS-DEVELOPMENT-PLAN.md`
- [x] `docs/project-guide/v1.0/` 9종
- [x] `docs/.gitkeep` (docs 에 파일이 있으므로 불필요)
- [x] 합계 15파일 · 5,840줄

### 갱신 (REQ-S04)

- [x] `django-style-app-registry/README.md` — 인덱스 4편 → 2편, 삭제 사실과 이유 명시
- [x] `DJANGO-APP-COMPATIBILITY.md` §8 — 삭제된 요구사항 ID 표 → **실재하는 검사** 매핑
- [x] `PASSIVE-APP-PROJECT-DESIGN.md` — 전면 재작성 (S-002·S-003)
- [x] `project-guide/v1.1/README.md` — v1.0 행 제거, 근거 문서 링크를 CRP 로 전환
- [x] `v1.1/01`·`v1.1/06` — 삭제된 설계 문서 참조 정정
- [x] `v1.1/03` — Raw 계열 3항목 추가, §8 미제공 목록 교체, `/ready` 반영
- [x] `v1.1/04` — reports 경로 오기 정정 (S-005)
- [x] `v1.1/05` — 생성기 경고를 실물(태그 선언만 수동)로 갱신
- [x] `v1.1/08` — `/ready` 서술 추가, 제한 목록 정정
- [x] `tests/test_docs_consistency.py` — `HISTORICAL_DOCS` 제거
- [x] `.github/workflows/ci.yml` — 죽은 인용 5곳 정리

### 검증

- [x] 삭제 대상을 가리키는 참조 0건 (문서·테스트·CI 전수 grep)
- [x] 게이트 `--fast` 6단계 통과
- [x] 게이트 8단계 통과 (MySQL·브라우저 포함) — 종료 코드 0
- [ ] 사용자 확인 — 갱신된 문서를 읽고 골격 설명이 실제와 맞는지 판정 (사람 판정)
