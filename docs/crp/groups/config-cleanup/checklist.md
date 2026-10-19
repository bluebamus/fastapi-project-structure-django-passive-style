# Checklist — config-cleanup (개선 항목 추적판)

> 각 항목은 한 줄이며, 그 줄이 닫히기(`[x]`) 전엔 "완료"가 아니다. ledger 의 Fix 항목과 1:1 로 연결한다.

## Round 0 — 2026-10-19 · 참조 조사
- [x] 요청을 design-baseline §2(REQ-001)에 기록 — 과거 그룹(skeleton-purpose-audit ADR-S11 의 `SMTP_PASSWORD` 검사 추가)은 이력으로 두고 고치지 않음
- [x] 그룹 6파일 작성(design-baseline·charter·checklist·ledger·residual-risk·run-log)
- [x] `git grep` 참조 목록(app·scripts·tests·migrations·docs·CI·compose) — run-log Round 0
- [x] `python-multipart` 사용처 확인 → 유지(ADR-004)

## Round 1 — 2026-10-19 · 삭제 · 만료 정본 · 계약 테스트
- [x] (F-001) `SMTPSettings`·`UploadSettings`·전역 인스턴스·`SESSION_EXPIRE_SECONDS`·`.env.example` 절 삭제, 배포 안전 검사의 SMTP 항목과 관련 테스트 정리
- [x] (F-001) 계약 테스트 — 설정 필드 읽힘(예외 5건 사유 명시)·지운 키 무시 · fail-on-revert
- [x] (F-002) README "세션·토큰 만료" 표 + 업그레이드 노트, ARCHITECTURE·admin-auth-guide·server-lifecycle-guide 는 표를 가리킴
- [x] (F-003) 범위 밖 미사용 설정 5건 → residual-risk R-001
- [x] GATE 3 인수기준 그린 — `.env` 없는 사본에서 1230 passed · 36 deselected · skip 0, review_gate --fast 7단계 통과
