# Ledger — docs-guide-review (결함 원장)

> 지적 ID 는 검수 보고(main `8553cdc`)의 F01~F26 을 그대로 쓴다. 근거 커밋: `6864018` 안내서 3종 · `069bbe1` ARCHITECTURE·DEVELOPMENT · `c998e20` README.

| ID | 판정 | Sev | 문서 | 고친 내용 | Status | 커밋 |
|---|---|---|---|---|---|---|
| F01 | WRONG | MED | ARCH §10 | revision 체인 끝에 `a3c9e8f1b274`(head) | Fixed | `069bbe1` |
| F02 | WRONG | MED | ARCH §11.1 #4 | MYSQL 빈 값·placeholder 거부, REDIS 값 있을 때 placeholder 거부, 32자 미만 | Fixed | `069bbe1` |
| F03 | WRONG | MED | server-lifecycle #lifespan | 전역 apps 소비 경고 삭제 | Fixed | `6864018` |
| F04 | WRONG | MED | server-lifecycle #redis | /ready 는 DB·Redis 를 함께 검사 | Fixed | `6864018` |
| F05 | WRONG | MED | server-lifecycle #operations | compose.test 의 Redis 7.4 `127.0.0.1:6380`(REDIS_TEST_PORT) | Fixed | `6864018` |
| F06 | INCONSISTENT | MED | server-lifecycle #setting-map·부록 | 비밀키 판정은 test 외 모든 ENV·32자 미만 포함, debug 판정만 staging/production | Fixed | `6864018` |
| F07 | MISSING | MED | server-lifecycle #health | 422·Redis 503·처리기 없는 예외 500 행 | Fixed | `6864018` |
| F08 | MISSING | MED | ARCH §3.3 | 예외 핸들러 목록·`answer_unhandled_exception`·422 후처리·8단계 `AccessPolicyGuard` | Fixed | `069bbe1` |
| F09 | WRONG | MED | feature-development #read-update | get_all 은 created_at DESC, PK DESC. total 은 목록과 같은 조건(R-001) | Fixed | `6864018` |
| F10 | OUTDATED | MED | feature-development #product | ProductUpdate 는 PatchSchema — description 외 명시 null 422 | Fixed | `6864018` |
| F11 | OUTDATED | MED | feature-development #security-tests | CI gate·mysql·e2e 세 job | Fixed | `6864018` |
| F12 | UNCLEAR | MED | server-lifecycle #health | 모든 401 에 핸들러(`_challenge`)가 `WWW-Authenticate: Bearer` | Fixed | `6864018` |
| F13 | INCONSISTENT | LOW | ARCH §7 | test 외 모든 ENV·32자 미만 | Fixed | `069bbe1` |
| F14 | WRONG | LOW | server-lifecycle 부록 | LogSettings 13개 필드 | Fixed | `6864018` |
| F15 | OUTDATED | LOW | server-lifecycle #setting-map | "선언만 있는 설정" 문장 삭제 | Fixed | `6864018` |
| F16 | WRONG | LOW | ARCH §3.4 · server-lifecycle #lifespan | `_prepare_database(resources, app.state.app_registry)` | Fixed | `069bbe1` `6864018` |
| F17 | INCONSISTENT | LOW | feature-development | 23 경로 / 38 오퍼레이션 | Fixed | `6864018` |
| F18 | OUTDATED | LOW | feature-development | 링크 문구 server-lifecycle.html | Fixed | `6864018` |
| F19 | INCONSISTENT | LOW | admin-authentication | --set-password 는 관리 세션 + refresh | Fixed | `6864018` |
| F20 | UNCLEAR | LOW | admin-authentication #architecture | 메인 체인 맨 바깥에 `answer_unhandled_exception` | Fixed | `6864018` |
| F21 | UNCLEAR | LOW | ARCH §11.2 · README | /ready 200 (DB·Redis 준비), README 503 행도 같은 값 | Fixed | `069bbe1` `c998e20` |
| F22 | OUTDATED | LOW | ARCH 머리·HTML 3종 | 기준일 2026-10-21 · main `8553cdc` | Fixed | `069bbe1` `6864018` |
| F23 | MISSING | LOW | ARCH §12 | integration-e2e·e2e-policy-2·이 그룹 행 | Fixed | `069bbe1` |
| F24 | INCONSISTENT | LOW | ARCH 머리·DEV §7·README | index.html 은 진입 링크 목록, 색인은 README 하나(ADR-003) | Fixed | `069bbe1` `c998e20` |
| F25 | MISSING | LOW | DEV §7 | admin-authentication·index.html 행 | Fixed | `069bbe1` |
| F26 | MISSING | LOW | ARCH §3.2 | LogSettings field validator 3종·SessionSettings 만료 validator 행 | Fixed | `069bbe1` |

## 누락 표

| 항목 | 위치 | Status | 커밋 |
|---|---|---|---|
| 조립 8단계 | ARCH §3.3 | Fixed (F08) | `069bbe1` |
| Redis 503·500 미들웨어·422 | server-lifecycle #health | Fixed (F07) | `6864018` |
| 변경 이력 3건 | ARCH §12 | Fixed (F23) | `069bbe1` |
| e2e job·마커 | feature-development #security-tests | Fixed | `6864018` |
| 기동 초기 로그 줄 파일 기록 | server-lifecycle #log-sinks | Fixed | `6864018` |
| replica→primary 재시도 | server-lifecycle #requests | Fixed | `6864018` |
| aiomysql[rsa] | ARCH §4.3 | Fixed | `069bbe1` |
| 문서 표 행 | DEV §7 | Fixed (F25) | `069bbe1` |
