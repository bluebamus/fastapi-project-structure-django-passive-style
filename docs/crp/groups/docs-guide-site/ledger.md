# Ledger — docs-guide-site (결함 원장)

> 지적 ID 는 2차 검수(passive 25 + 감독 재검수 8)의 것을 그대로 쓴다. 공통 결함 번호는 C-xx.
> 커밋: `7c8e91c` docstring · `905dfc4` 흐름·기능 · `daf9805` 시작·설정·배포·테스트 · `b36a58e` API·인증 · `f00b28e` 허브·CSS · `ffb09e7` 계약 테스트 · 기록 커밋(README·ARCHITECTURE·residual-risk·이 그룹).

| ID | 공통 | Sev | 문서 | 고친 내용 | Status | 커밋 |
|---|---|---|---|---|---|---|
| TST-01 | C-02 | HIGH | development/testing | `uv run python -m pytest -m "not mysql and not browser"`, browser 는 REDIS_HOST/PORT, e2e 는 `-m e2e` 때만 수집 | Fixed | `daf9805` |
| TST-02 | C-14 | LOW | development/testing | 인증·rate limit 은 기본 게이트의 fakeredis, 실제 Redis 는 browser·e2e | Fixed | `daf9805` |
| FEAT-01 | C-01 | MED | features 8편 | 쓰기 핸들러가 응답 DTO 검증 뒤 `await service.commit()` 1회, 세션은 의존성. home·reports 는 조회 전용 문장 | Fixed | `905dfc4` |
| ARC-01 | C-01 | MED | architecture | 커밋 시점은 핸들러, 세션은 Depends. 패턴 표의 트랜잭션 행 | Fixed | `905dfc4` |
| SEQ-01 | C-01 | MED | sequence-diagrams 쓰기 도식(렌더·원문) | Depends 세션 → 핸들러 DTO 검증 → `service.commit()` | Fixed | `905dfc4` |
| DEV-02 | C-01 | LOW | development/index 도식 | "서비스/트랜잭션" → "서비스 규칙", 라우터 노드에 commit | Fixed | `905dfc4` |
| SEQ-02 | C-13 | LOW | sequence-diagrams 기동 도식 | Redis ping·버전, DEBUG 때만 create_all, background drain → Redis close → DB dispose (worker 없음) | Fixed | `905dfc4` |
| SEQ-03 | C-13 | LOW | sequence-diagrams 인가 도식 | superuser 경로도 토큰 실패 401, 슈퍼유저 아님 403 | Fixed | `905dfc4` |
| REQ-01 | C-03 | MED | request-processing | request id 삭제 → client IP·User-Agent·경로 | Fixed | `905dfc4` |
| REQ-02 | C-07 | MED | request-processing | 미들웨어 순서 answer_unhandled_exception → UserInfo → CORS, Redis 503, 401 WWW-Authenticate | Fixed | `905dfc4` |
| REQ-03 | C-07 | LOW | request-processing | DEBUG=true 면 다시 던짐, SQLAlchemyError 는 traceback 없음 | Fixed | `905dfc4` |
| REQ-04 | C-07 | LOW | request-processing | "Routed DB session" → read_only/writer 세션(routed 미사용) | Fixed | `905dfc4` |
| API-01 | C-08 | LOW | reference/api | /docs·/openapi.json 은 DEBUG=true 만, /admin 은 OpenAPI 밖 | Fixed | `b36a58e` |
| API-02 | — | LOW | reference/api | 근거를 access.py·wiring.py·기능 라우터 8개·정책 테스트로 | Fixed | `b36a58e` |
| API-03 | C-08 | LOW | reference/api·authentication | rate limit 은 register·login 만 | Fixed | `b36a58e` |
| CFG-01 | C-04 | MED | reference/configuration | 설명을 Field description 으로, `**…**`·값 잘림 제거(ADR-003) | Fixed | `daf9805` |
| CFG-02 | C-04 | MED | reference/configuration | Settings 78개 필드 전부 + 검증 규칙 절 | Fixed | `daf9805` |
| GS-01 | C-05 | MED | getting-started | 비밀 키 3종(32자+, 서로 다름)·MYSQL_PASSWORD·Redis·MySQL(create_all)·슈퍼유저 | Fixed | `daf9805` |
| GS-02 | C-05 | LOW | getting-started | DEBUG=false 또는 소유 테이블 0 이면 기동 중 DB 접속 안 함, /ready 는 별도 요청 | Fixed | `daf9805` |
| GS-03 | C-05 | MED | getting-started | 설정 검증은 config import 시점, Redis 기동 필수. 요청 중 장애는 **Redis 를 쓰는 경로만** 503 | Partial | `daf9805` |
| DEP-01 | C-03 | MED | operations/deployment | request id 삭제 → 예외 로그 path·method + 접속 로그 user_id | Fixed | `daf9805` |
| DEP-02 | C-06 | LOW | operations/deployment | URL → MYSQL_*/REDIS_* (URL 은 ALEMBIC_DATABASE_URL 만) | Fixed | `daf9805` |
| DEP-03 | C-06 | MED | operations/deployment | ENV 게이트·TRUSTED_PROXY_HOPS·`e5a7c2d9f310`·첫 슈퍼유저·LOG_FILE_ENABLED·README 링크. Redis 장애는 "전 API 503" 이 아니라 Redis 를 쓰는 경로·/ready 만 503 | Partial | `daf9805` |
| DEV-01 | C-11 | MED | development/index | `config.INSTALLED_APPS` 에 AppConfig 경로 한 줄, AccessPolicyGuard 기본 거부 | Fixed | `905dfc4` |
| HOME-01 | C-10 | MED | features/home | `home.purge_expired_access_logs`(beat 03:30, ACCESS_LOG_RETENTION_DAYS)·`home.aggregate_access_stats`(일정 없음), 소스에 tasks.py | Fixed | `905dfc4` |
| AUTH-01 | C-12 | LOW | features/auth 도식 | AuthService → RefreshTokenStore 직접 | Fixed | `905dfc4` |
| AUTH-02 | C-09 | MED | workflows/authentication | access 는 만료 전 폐기 불가, /me 외 보호 경로는 토큰 클레임만 | Fixed | `b36a58e` |
| IDX-01 | C-15 | LOW | guides/index.html | 줄 단위 서식·끝 개행 | Fixed | `f00b28e` |
| IDX-02 | C-15 | LOW | guides/index.html | README 링크 복원, sequence-diagrams 를 새 문서 쪽으로, 기능 8편·testing 까지 전 문서 링크 | Fixed | `f00b28e` |
| ALL-01 | C-16 | LOW | 새 HTML 19편 | mermaid@11.12.0 고정 로더 + CDN 실패 안내, 라벨 `PROJECT GUIDE`(ADR-005), style.css 줄 단위 | Fixed | `905dfc4` `daf9805` `b36a58e` `f00b28e` |
| RR-01 | C-17 | LOW | docs-guide-review/residual-risk.md | 기존 행 원복, 해결 기록은 새 절로 덧붙임 | Fixed | 기록 커밋 |
| TC-01 | — | LOW | tests/test_docs_references.py 주석 | INDEXED_HTML_GUIDES·SOURCE_HTML_GUIDES 로 정정 | Fixed | `ffb09e7` |
| 부수-2 | — | LOW | 서비스 docstring 5개 | 트랜잭션 경계 = 쓰기 핸들러 커밋(요청 밖은 background_session) | Fixed | `7c8e91c` |

Partial 사유(GS-03·DEP-03): `app/core/middlewares/` 에 Redis 를 쓰는 미들웨어가 없고, `bootstrap.py` 의 Redis 연결 오류 처리기는
Redis 를 실제로 부른 경로에서만 503 을 낸다. README 「운영 배포 체크리스트」도 "Redis 를 쓰지 않는 조회는 그대로 동작" 이라 적는다 — 코드대로 썼다.

## 2차 라운드 — 2026-10-22 (REQ-002, 원 행은 고치지 않는다)

지적 ID 는 재검수 보고(round2)의 것. 커밋: `bab635a` 문서 · `1a47a02` 계약 테스트 · `1cbe48b` 인용 정리 · 기록 커밋(이 절).

| ID | Sev | 위치 | 처리 | Status | 커밋 |
|---|---|---|---|---|---|
| P-N1 | MED | `.env.example` Redis 절 | "캐시·세션 구현은 없다" → 일반 캐시 없음, Redis 는 /admin 서버 세션·refresh 회전 기록·레이트 리밋·Celery. 같은 문장의 `RedisSettings` docstring·ARCHITECTURE 설정 표·server-lifecycle 표도 함께 | Fixed | `bab635a` |
| P-N2 | LOW | README 구조 트리 | Settings 12종 → 9종(`config.py` 의 `BaseSettings` 클래스 9개) | Fixed | `bab635a` |
| P-N3 | MED | features/auth 도식(렌더·원문) | AuthRouter → Rate limiter 간선에 `register·login` 라벨 | Fixed | `bab635a` |
| P-N4 | MED | features/auth 본문·주의점 | 커밋은 DB 를 쓰는 register(DTO 검증 뒤)·login(토큰 발급 뒤, 재해시 저장)만, refresh·logout 은 Redis 원자 연산이라 커밋 없음 | Fixed | `bab635a` |
| P-N5 | MED | `tests/test_docs_guide_site.py` | 설정 표 "코드 기본값" 열을 Settings 필드 기본값과 대조(`DESCRIPTION` 만 축약 표기로 제외) | Fixed | `1a47a02` |
| X-1 | MED | `tests/test_docs_guide_site.py` | `features/*.html` 의 API 행이 OpenAPI × `AccessPolicyGuard` 판정 집합의 부분집합 | Fixed | `1a47a02` |
| X-2 | LOW | 링크 fragment 검사 | **고치지 않음** — 이 저장소는 이미 검사한다: `test_html_guide_relative_links_and_anchors_resolve`(모든 가이드 HTML, `#` 뒤를 대상 HTML id·Markdown 제목 앵커로 확인)·`test_markdown_link_anchors_resolve`. 저장소 밖 복사본에서 HTML·Markdown fragment 를 각각 없는 앵커로 바꾸면 둘 다 1 failed | Not a defect | — |
| X-3 | LOW | app·tests 17개 파일 + ARCHITECTURE 현행 절 | "e2e-policy-2 결정 N" → `integration-e2e ADR-012 결정 N`(design-baseline §3.3), "의존성 통일" → ADR-013. 변경 이력 행은 과거 기록이라 그대로 | Fixed | `1cbe48b` |
| 정정-01 | MED | 이 원장·checklist·run-log Round 1 | 1차의 "FEAT-01 Fixed"·`CONVERGED (Open Fix 0)` 선언은 사실과 달랐다 — features/auth 의 "쓰기 핸들러 모두 커밋"(P-N4)과 P-N1~P-N3·P-N5 가 남아 있었다. 원 행은 두고 이 행으로 정정한다 | Corrected | 기록 커밋 |
| P-F1 | LOW | 미들웨어 모듈·클래스 docstring, `config.py` API 소개, `.env.example` 주석, ARCHITECTURE §6, workflows/request-processing | 병합 후 후속(가로 대조): "모든 요청·요청마다 수집·저장" → `ACCESS_LOG_ENABLED=true` 이고 제외 경로(정확 일치)·확장자(접미사 일치)에 걸리지 않는 요청만(`_should_skip`). server-lifecycle §11 은 이미 판정을 적어 그대로 | 수정됨 — 검수 대기 | `329ad95` |
