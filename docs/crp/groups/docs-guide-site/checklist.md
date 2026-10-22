# Checklist — docs-guide-site

## Round 0 — 2026-10-22 · 계획
- [x] 요청을 design-baseline §2(REQ-001)에 기록
- [x] 생성물 원본을 브랜치 `docs/guide-site` 에 그대로 커밋 — `4d346ee`
- [x] 지적마다 코드 근거를 다시 열어 확인 — 33건 중 31건 그대로, 2건(GS-03·DEP-03 의 "Redis 장애 = 전 API 503")은 코드대로 고침

## Round 1 — 2026-10-22 · 수정
- [x] 계약 테스트를 먼저 써서 생성물에서 4건 실패 확인(API 표·설정 표·Mermaid·허브 링크)
- [x] 서비스 docstring — `7c8e91c`
- [x] 흐름·기능 문서 — `905dfc4`
- [x] 시작·설정·배포·테스트 문서 — `daf9805`
- [x] API·인증 문서 — `b36a58e`
- [x] 허브·CSS — `f00b28e`
- [x] 계약 테스트 — `ffb09e7`
- [x] README·ARCHITECTURE 변경 이력·docs-guide-review residual-risk 원복·이 그룹 — 기록 커밋

## Round 2 — 2026-10-22 · 재검수 남은 결함 (REQ-002)
- [x] 지적마다 코드 근거를 다시 확인 — P-N1~P-N5·X-1·X-3 맞음, X-2 는 이미 검사 중(고치지 않음)
- [x] 문서 — `bab635a`
- [x] 계약 테스트 보강(기능별 API 표·설정 기본값), 깨진 복사본에서 먼저 실패 확인 — `1a47a02`
- [x] "e2e-policy-2 결정" 인용 정리 — `1cbe48b`
- [x] 1차 수렴 선언 정정(ledger 정정-01)
