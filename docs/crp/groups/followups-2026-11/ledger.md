# Ledger — followups-2026-11 (결함 원장)

| ID | Severity | 위반 계약 조항 | 결정 | Status | 근거(커밋/링크) | 비고 |
|---|---|---|---|---|---|---|
| F-001 | LOW | INV-3 | Fix | Fixed | `fix/test-module-imports` 병합 | 2곳: `admin/test_disabled`→`test_deployment_safety`(STRONG·SOURCE), `db/test_replica_fallback`→`db/test_router`(Probe·엔진·origins). 다른 테스트 모듈 간 import 없음(grep) |
| F-002 | MED | REQ-001 | Fix | Fixed | `test/mysql-ci` 병합 | 실제 MySQL 자동 검증 0건 → 9건, CI `4fa2a0d` 에서 9 passed |
