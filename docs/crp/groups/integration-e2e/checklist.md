# Checklist — integration-e2e (개선 항목 추적판)

> 각 항목은 한 줄이며, 그 줄이 닫히기(`[x]`) 전엔 "완료"가 아니다. ledger 의 항목과 1:1 로 연결한다.

## Round 0 — 2026-10-20 · 계획·인벤토리 재추출
- [x] 요청을 design-baseline §2(REQ-001~REQ-005)에 기록, 그룹 6파일 작성
- [x] 병합된 main(`eb47b6c`)에서 인벤토리 재추출 — operation 38·관리 뷰 7·태스크 2·beat 1·Redis 키 리터럴 11(run-log Round 0)
- [x] 포트 13341·13342·16393·18093 점유 없음(Windows netstat·WSL ss), WSL→Windows 127.0.0.1 전달 확인

## Round 1 — W0
- [x] (F-003) 브라우저 하네스 Redis 대상 명시 강제·자식 env 명시·CI 명시 — RED 는 접속 없는 호출로, 6379 접속 0

## Round 2 — W1~W6 e2e 스위트
- [x] W1 `compose.e2e.yaml`(GTID 복제·tmpfs·명령줄 설정·비밀번호 필수 변수), profile `redis-old`
- [x] W2 하네스(대상 검사·WSLENV·`.env` 없는 실행 디렉터리·Alembic·uvicorn·worker·로그 수집·artifact)
- [x] W3 인벤토리 대조기(빈 칸·낡은 N/A 모두 실패)
- [x] W4 L2·L3·L4·L5·L6 + 비밀값 검사
- [x] W5 `pytest-timeout`(dev), browser 마커 병존(ADR-005)
- [x] W6 CI job `e2e`(매 push·마스킹·skip/xfail/0건 실패·artifact·항상 down), gate·mysql job `REDIS_HOST`·`REDIS_PORT`
- [x] (F-001) 위조·만료 토큰 401 의 `WWW-Authenticate` — TDD·별도 커밋
- [x] (F-002) 브라우저 live server 파이프 막힘 — TDD·별도 커밋

## Round 3 — 사용자 결정 반영
- [x] (F-004) 결정 1 — Redis 연결 오류 503·기록 한 번·keep-alive, L5 기대값 갱신
- [x] (F-005) 결정 2 — replica 연결 오류 primary 재시도(ADR-010), L5 기대값 갱신
- [x] (F-006) 결정 3 — 재현 안 됨, 실제 프로세스 계약 테스트로 고정(ADR-011)

## Round 4 — 검증·문서
- [x] Windows 전체 e2e 309 passed(skip·xfail 0), L1: 단위 1364·`-m mysql` 27·`-m browser` 10
- [x] Linux `.env` 없는 클론: 단위 1364·e2e 309, prefork Warm shutdown 확인, 클론 삭제
- [x] ruff·ruff format·mypy(1.20.2 순수 Python)·`review_gate --fast` 7단계
- [x] README·DEVELOPMENT §6.6·ARCHITECTURE(예외 표·replica 재시도·초기 로그 줄)
- [ ] (F-007·F-008·F-009·F-012) 정책 결정 대기 — 사용자

## Round 5 — 2026-10-21 · e2e 정책 결정 2차 (e2e-policy-2)
- [x] (F-010) 결정 1 — OpenAPI 422 = `ErrorResponse`, 계약 테스트·e2e L2 단정 (`371d896`·`95ae048`)
- [x] (F-013) 결정 2 — 처리기 없는 예외 기록 1번·keep-alive, 실제 uvicorn 테스트 (`8665236`)
- [x] (F-012) 결정 3 — 모든 401 에 `WWW-Authenticate: Bearer` (`6788468`·`62da6f6`)
- [x] 결정 4 — `create_superuser --set-password` 세션 폐기: 이미 충족, 계약 고정 (`ddaadc7`)
- [x] (F-008) 결정 5 — 인증 사용자 조회 primary, e2e L3 기대값 갱신 (`4743b1c`)
- [x] (F-009) 결정 6 — 관리 화면 저장 실패 503, e2e L5 기대값 갱신 (`c3e8280`)
- [x] (F-007) 결정 7 — CSRF 본문 413·필드 400, L5 측정 기대값 갱신 (`6bfc431`)
- [x] (F-014) 의존성 `aiomysql[rsa]` 통일 (`ab7f15d`)
- [x] 검사: e2e 309·단위 1386·`-m mysql` 27·ruff·mypy·`review_gate --fast`(pip-audit 포함)
