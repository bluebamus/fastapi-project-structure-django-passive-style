# Checklist — learning-path

> `audit-report.md` §5 완료 판정 기준과 동일. 여기서 진행 상태를 추적한다.

## T-4a — 검사 범위 확대

- [x] `BASE_DOCS` 에 `docs/project-guide/<현행>/*.md` 포함
- [x] 헛통과 방지 가드가 가이드 문서에서도 의미 있게 동작 (ADR-L04: 경로 인용 추가)
- [x] T-1 과 **한 커밋**으로 묶음 (중간 빨간불 없음)

## T-1 — `project-guide v1.1`

- [x] `v1.0` 보존, `v1.1` 신설
- [x] `get_session()`·`get_read_session()`·`get_write_session()` **0회** (L-007)
- [x] Raw 층 반영: `RawRepositoryBase`·`RawCRUDBase`·intent 라우팅
- [x] 예제 2종(`catalog`·`reports`) 반영
- [x] 신규 `09-orm-vs-raw-decision.md` — "언제 ORM, 언제 Raw" (L-004)
- [x] 루트 기준 경로 인용 존재 (헛통과 가드 만족)

## T-2 — 진입 문서 연결

- [x] README 제목 `Default` → `Django Passive Style` (L-005)
- [x] README 구조 트리에 `catalog`·`reports` 실물 (L-006)
- [x] `RawRepositoryBase` 가 진입 문서 **최소 2곳** (L-001)
- [x] 진입 문서 → `project-guide` 링크 (L-003)

## T-3 — 학습 경로 잠금

- [x] `REQUIRED_IN_ENTRY_DOCS` 추가
- [x] fail-on-revert 로 동작 증명 (항목을 지우면 실패하는가)

## 최종

- [x] `scripts/review_gate.py` 8단계 통과
- [ ] 학습자 시나리오 수동 검증: "README 만 읽고 Raw 기능을 하나 만들 수 있는가" — **사람 판정(RL-03)**, 사용자 확인 대기

## Round 1 중 추가된 항목 — 완료

- [x] (L-009) README 목차의 죽은 `레이트 리밋` 앵커 제거
- [x] (L-010) browser 테스트 flake 수정 — 고정 대기 → 폴링. 이 그룹의 회귀가 아님을 stash 재현으로 먼저 확인
- [x] (L-011) `pyproject.toml` name 잔재를 residual-risk RL-05 로 수용
- [x] 커밋 3개로 분할 — `9acbad8`(T-4a+T-1) · `d74ab5a`(T-2) · `7b907cf`(T-3)
