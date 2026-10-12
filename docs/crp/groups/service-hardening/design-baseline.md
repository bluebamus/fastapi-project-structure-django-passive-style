# Design Baseline — service-hardening (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준(authoritative baseline)**. charter(코드 계약)와 달리
> 이 문서는 *"사용자가 무엇을, 왜 요구했는가"* 의 영속 기록이다. **모든 추가 작업은 여기 기록된
> Active 요구사항과 불가침 제약을 위반하지 않아야 한다**(요구사항 회귀 방지). 새 요청이 올 때마다
> §2 에 append 하고, 설계 결정은 §3 에 ADR 로 고정한다. append-only — 항목은 지우지 않고
> 상태(Active/Superseded)만 바꾼다.
>
> 이 그룹의 ID(REQ·ADR·C·F)는 그룹 안에서만 유효하다. 다른 그룹의 ID 를 가리킬 때는
> `orm-raw-repository ADR-016` 처럼 그룹 이름을 붙인다.

## 0. 질의 수준 (Autonomy Level)

- [ ] 적극(Thorough)
- [x] **보통(Balanced)** — 핵심 갈림길(목적·범위·비가역·계약)만 질문, 자명한 건 기본값 + 한 줄 고지.
- [ ] 간략(Lean)

선택: **보통** · 선택일: 2026-10-12 · 변경 이력: (없음)

> 핵심 갈림길 두 개는 사용자가 요청에서 이미 정했다 — Redis 는 필수(제안 8), 로그인 고도화는
> "전통적인 방식 + FastAPI 최신 실무 코드" 기반의 일반 설계(제안 9). 나머지는 기본값으로 진행하고
> 결정을 §3 에 남긴다.

## 1. 목적 / 배경

2026-10-07 전체 검수(`docs/review/` 의 로컬 보고서, 저장소에 커밋하지 않는다)가 남긴 미착수 지적과
사용자 제안 1~9 를 **운영 가능한 골격**으로 끌어올린다. 범위는 CI 재현성, DSN 조립, ORM 잠금 읽기와
목록 정렬, 접속 로그 수집, 오류 매핑, 테스트 하네스, 시각 정책(UTC 저장), Redis 필수와 Celery 자동
발견, 인증·인가(로그인 고도화)다.

방식은 이 저장소가 이미 쓰는 것을 따른다. 기능 설치는 `config.INSTALLED_APPS` + `apps.py` 의
`AppConfig`, 협력 객체는 `dependencies/*_dependencies.py` 의 provider 함수(`Depends`)가 조립해
생성자로 넘긴다. 같은 목적의 기능은 한 모듈 클래스로 묶고, 테스트는 provider 를
`app.dependency_overrides` 로 바꾸거나 생성자에 가짜를 넣는다.

## 2. 요구사항 레지스터 (append-only)

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-10-12 | "1,2,3,4,5,6,7,8 redis 필수, 9는 전통적인 방식과 fastapi에서 최신 사용하는 실무 코드를 기반으로, 일반적으로 개발되는 설계를 기반으로 작업 계획을 만들고 이를 기반으로 개발을 진행해줘. 각 단계는 단위 테스트가 반드시 진행되어야 한다. 모든 기능은 같은 목적의 기능이 하나의 모듈 클래스로 만들어져야 하고 필수 작업은 반드시 주입을 통해 조합, 데이터 전달, 인증 및 자동 작업 등이 진행되어야 하며…" | 아래 §2-1 의 단계별 도출 요구 D-A1 ~ D-F2. 공통: 단계마다 단위 테스트(가능하면 fail-on-revert), 같은 목적 = 한 모듈 클래스, 조합·데이터 전달·인증·자동 작업은 주입으로 | Active | ADR-001~ADR-022 · C-1~C-15 · charter INV-1~ · ledger F-001~ · run-log Round 1~ |

### 2-1. REQ-001 의 단계별 도출 요구

| ID | 단계 | 도출된 요구사항 | 연결 |
|---|---|---|---|
| D-A1 | A (제안 1) | CI 의 모든 `uv sync` 가 `--locked` 로 락과 `pyproject.toml` 의 불일치를 실패로 만든다. 주석·문서도 사실대로 고친다 | ADR-001 · C-15 · F-004 |
| D-A2 | A (제안 2) | DSN 은 `sqlalchemy.engine.URL.create()` 로 조립한다. 비밀번호의 특수문자(`@ : / % # ?`)가 왕복하고, Alembic 에는 `%` 를 `%%` 로 넘기며, Redis URL 의 비밀번호는 퍼센트 인코딩한다 | ADR-002 · C-6 · F-003 |
| D-A3 | A (제안 3) | ORM 잠금 읽기(`with_for_update()`)는 writer 로 가고 읽기 전용 세션에서 거부된다. 범용 목록(`get_all`)은 `created_at DESC, PK DESC` 기본 정렬, `created_at desc` 단일 키 쿼리에는 `id desc` 보조 키 | ADR-003 · ADR-004 · C-7 · C-8 · F-001 · F-002 |
| D-B | B (제안 4·5) | 클라이언트 IP 는 신뢰 홉 수로만 해석, 500 응답도 접속 로그에 남김, 민감 query 마스킹, 컬럼 길이로 자르기, null PATCH 422, DB 오류 코드별 변환, 리포트 날짜 상한, 남은 리뷰 버그 | ADR-005~ADR-008 · F-005~F-013 |
| D-C | C (제안 6) | 엔드포인트 테스트용 세션 override 헬퍼 하나(read-only 는 `mark_read_only` 경유), MySQL 방언 스모크, 설정 patch 순서 의존 제거 | ADR-009 · F-014~F-016 |
| D-D | D (제안 7) | DB 는 UTC·마이크로초로 저장, 응답은 오프셋 포함 ISO 8601, 리포트는 설정 시간대의 영업일 기준 | ADR-010 · C-9 · F-017 |
| D-E | E (제안 8) | Redis 필수 유지, `get_redis` provider, `/ready` 가 DB·Redis 를 모두 확인, Celery 태스크를 기능별 `tasks` 모듈로 옮기고 워커 include 를 `INSTALLED_APPS` 에서 만든다 | ADR-011 · ADR-012 · C-10 · F-018 · F-019 |
| D-F1 | F1 (제안 9 前半) | `PasswordHasher`(Argon2, bcrypt 점진 이전), `TokenService`(iss/aud/jti/nbf), `RefreshTokenStore`(회전·재사용 탐지), `RateLimiter`(Redis 고정 창), 엔드포인트 register/login/refresh/logout/me | ADR-013~ADR-016 · F-020 · F-021 |
| D-F2 | F2 (제안 9 後半) | 상태 없는 `Principal`, 소유권 `OwnershipPolicy`, 슈퍼유저 2단계, 라우트 정책, `scripts/create_superuser.py`. SQLAdmin 정책은 그대로 | ADR-017~ADR-020 · C-11 · C-13 · F-022~F-025 |

## 3. 설계 결정 기록 (ADR — 확정 후 불변)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-10-12 | CI 의 `uv sync --frozen` 을 모두 `uv sync --locked` 로 바꾼다. 계약 테스트가 `ci.yml` 에 `--frozen` 이 없고 `uv sync --locked` 가 있음을 확인한다 | `--frozen` 은 락을 **검사하지 않고** 그대로 설치한다 — 기존 주석("어긋나면 실패")은 사실이 아니었다. `--locked` 가 그 의미다. 로컬 게이트(`scripts/review_gate.py`)는 작업 트리를 `rglob` 으로 훑지 않으므로 파일 목록 교체 대상이 없다 | Accepted | |
| ADR-002 | 2026-10-12 | `DatabaseSettings` 의 `MYSQL_URL`·`MYSQL_WRITER_URL`·`MYSQL_REPLICA_URLS`·`ALEMBIC_URL` 은 문자열이 아니라 `sqlalchemy.engine.URL` 을 돌려준다. 마스킹은 `URL.render_as_string(hide_password=True)`. `ALEMBIC_URL` 은 `ALEMBIC_DATABASE_URL` 이 있으면 `make_url`, 없으면 writer URL 의 drivername 만 `mysql+pymysql` 로 바꾼다. `migrations/env.py` 는 `render_as_string(hide_password=False).replace("%", "%%")` 를 넘긴다. `REDIS_URL` 은 비밀번호를 `urllib.parse.quote(pw, safe="")` 로 인코딩한다 | 문자열 연결은 `@`·`:`·`/`·`#` 가 든 비밀번호에서 조용히 다른 서버·계정으로 해석되고, `%` 는 Alembic 의 ConfigParser 보간에서 터진다. IPv6 대괄호도 `URL` 이 렌더링 시 처리한다 | Accepted | |
| ADR-003 | 2026-10-12 | ORM `Select` 에 `_for_update_arg` 가 있으면 쓰기로 판정한다 — 라우터는 writer 로 보내고(이후 세션 sticky), 읽기 전용 세션은 실행 전에 `ReadOnlyRoutingError` 로 거부한다 | Raw 경로는 이미 `for_update=True` → `write_intent` 로 같은 규칙을 지킨다(orm-raw-repository ADR-017). replica 에서 잡은 잠금은 primary 의 행을 보호하지 못한다 | Accepted | |
| ADR-004 | 2026-10-12 | `BaseRepository.get_all` 은 기본 정렬 `created_at DESC, <PK> DESC` 를 갖는다(모델에 `created_at` 이 없으면 PK 만). 공개 메서드는 늘리지 않는다(8개 유지). `created_at desc` 단일 키 쿼리에는 `id desc` 보조 키를 붙인다. `sku` 처럼 유일한 키로 정렬하는 쿼리는 그대로 둔다 | 정렬 없는 `OFFSET/LIMIT` 은 페이지 사이 중복·누락을 만든다. `created_at` 은 동률이 생기므로(초 단위 저장·일괄 삽입) 유일 키 보조 정렬이 필요하다. 메서드 수 고정은 orm-raw-repository ADR-016·C-22 | Accepted | |
| ADR-005 | 2026-10-12 | 클라이언트 IP 는 core 의 모듈 클래스 `ClientIPResolver` 가 정한다. 설정 `TRUSTED_PROXY_HOPS: int = 0`. 0 이면 `request.client.host`, N 이면 `X-Forwarded-For` 목록 + 직접 피어에서 **오른쪽 N번째**. `ipaddress.ip_address` 검증에 실패하면 직접 피어. `X-Real-IP` 는 hops>0 이고 XFF 가 없을 때만 | 헤더를 무조건 믿으면 누구나 기록 IP 를 위조한다. 신뢰는 "몇 홉의 프록시를 운영하는가" 라는 배포 사실로만 정한다 | Accepted | |
| ADR-006 | 2026-10-12 | 접속 로그 미들웨어는 `call_next` 예외 시 status 500 으로 기록한 뒤 다시 raise 한다. query_string 의 민감 키(설정 `ACCESS_LOG_SENSITIVE_QUERY_KEYS`)는 값을 `***` 로 바꾼다. 세션 쿠키 이름은 설정에서 읽는다. 문자열 길이 자르기는 **home 기능**이 모델 컬럼 길이(`Model.__table__.c[name].type.length`)로 한다 | 가장 기록이 필요한 장애 요청이 빠지고, 긴 헤더 하나로 기록을 피할 수 있었다. core 는 모델을 모르므로 길이는 모델을 아는 기능이 정한다(숫자를 두 번 적지 않는다) | Accepted | |
| ADR-007 | 2026-10-12 | 공통 Update 스키마 기반 클래스(`PatchSchema`)가 `model_fields_set` 안의 None 을 nullable 허용 목록(`ClassVar`) 밖이면 422 로 거부한다. DB 오류 변환은 기존 단일 변환 경계에서 코드별로 나눈다: 1062/UNIQUE → 409, 1048·1364/NOT NULL → 422, 1452 → 422, 1451 → 409, 그 외 500. 메시지에 원문·SQL 을 싣지 않는다 | MySQL 에서 `{"title": null}` 이 500 이 되고 SQLite 에서는 409 라 단위 테스트가 가렸다. 원문 비노출은 orm-raw-repository C-12·C-20 | Accepted | |
| ADR-008 | 2026-10-12 | 리포트 날짜 범위는 1970-01-01..9998-12-31, 최대 366일. 넘으면 422 | `date.max + 1일` 의 `OverflowError` 가 500 이 되고, 상한 없는 범위는 과대 스캔이다 | Accepted | |
| ADR-009 | 2026-10-12 | 엔드포인트 테스트의 세션 override 는 공용 헬퍼 한 곳에서 만든다 — writer 는 `using_writer`, read-only 는 `mark_read_only` 를 거친 세션을 yield 한다. MySQL 방언 스모크는 `mysql` 마커로 CI 가 돌린다 | override 가 읽기 전용 마킹을 우회해 GET 핸들러의 몰래 쓰기를 HTTP 테스트가 못 잡았다 | Accepted | |
| ADR-010 | 2026-10-12 | 시각은 DB 에 **UTC·마이크로초**로 저장한다. `UTCDateTime` TypeDecorator(impl `DateTime()`, MySQL variant `DATETIME(fsp=6)`): bind 는 aware → UTC 변환 후 tzinfo 제거, naive 는 `ValueError`; result 는 tzinfo=UTC 부착. 시각 생성은 한 곳(`utc_now`). 응답은 오프셋 포함 ISO 8601. 리포트는 설정 `TIME_ZONE` 의 영업일 기준으로 집계한다. Celery `enable_utc=True`. 기존 값은 Alembic 리비전이 `CONVERT_TZ(col,'+09:00','+00:00')` 로 옮긴다 | `DateTime(timezone=True)` 가 MySQL 에서 tz·마이크로초를 모두 잃어 KST 와 UTC 벽시계가 섞였다. naive 를 거부해야 조용한 오해가 생기지 않는다 | Accepted | |
| ADR-011 | 2026-10-12 | **Redis 는 필수다.** 클라이언트는 lifespan 이 소유하고 주입 provider `get_redis(request) -> Redis`(core) 하나로 꺼낸다. `/ready` 는 DB 와 Redis 를 각 2초 안에 ping 하고 하나라도 실패하면 503(원문 없음) | 사용자 결정("8 redis 필수"). 리뷰가 제시한 `REDIS_REQUIRED` 선택 플래그안은 채택하지 않는다 — 레이트 리밋·refresh 회전이 Redis 를 실제로 쓰게 되므로 선택일 수 없다 | Accepted | |
| ADR-012 | 2026-10-12 | Celery 태스크는 기능별 `tasks` 모듈에 둔다. `AppConfig.tasks_module`(기본 `"tasks"`)을 router/models/admin 모듈과 같이 `import_optional` 로 import 하고, 워커의 include 는 `INSTALLED_APPS` 로 만든다. 워커 기동 시 모델 등록도 같은 경로. 태스크 본문의 서비스 조립은 그 기능의 provider 함수를 재사용한다 | 중앙 `app/celery/tasks.py` 가 home 을 직접 import 해 `INSTALLED_APPS` 에서 앱을 빼도 워커가 계속 그 앱을 끌어왔다. Django 의 `autodiscover_tasks` 와 같은 방식이다 | Accepted | |
| ADR-013 | 2026-10-12 | 비밀번호는 인증 기능의 `PasswordHasher` 가 다룬다 — `pwdlib[argon2]` 의 Argon2 로 해시하고, 기존 bcrypt 해시(`$2` 접두사)는 기존 규칙(72바이트 절단)으로 검증한 뒤 성공하면 Argon2 새 해시를 돌려준다(로그인 시 재해시 저장 = 점진 이전). 타이밍 균등화 더미 해시도 Argon2. 의존성 `pwdlib[argon2]`, dev `fakeredis` 를 `uv add` 로 추가한다 | FastAPI 공식 문서가 현재 권하는 방식이 pwdlib + Argon2 다. 기존 사용자를 한 번에 재설정시키지 않고 로그인할 때 옮긴다. fakeredis 는 Redis 를 쓰는 실물 클래스를 가짜 없이 시험하기 위한 것이다 | Accepted | |
| ADR-014 | 2026-10-12 | 토큰은 core security 의 `TokenService`(PyJWT)가 발급·검증한다. claims `sub, type, iat, nbf, exp, jti, iss, aud` + access 는 `username`, `su` / refresh 는 `fam`. decode 는 `algorithms=[설정]`, `audience`, `issuer`, `options={"require": [...]}`, `leeway`. 설정 `JWT_ISSUER`·`JWT_AUDIENCE`·`JWT_LEEWAY_SECONDS`, `JWT_ALGORITHM` 은 `Literal["HS256","HS384","HS512"]`, `ACCESS_TOKEN_EXPIRE_MINUTES` 기본 15 | 기존 토큰은 `sub/type/iat/exp` 뿐이라 발급자·대상 혼동과 재사용을 막을 수 없었다. 검증을 core 에 두어야 기능끼리 import 하지 않고 인증을 주입할 수 있다 | Accepted | |
| ADR-015 | 2026-10-12 | refresh 토큰은 회전한다. `RefreshTokenStore`(core security, Redis): 발급 시 `auth:rt:{jti}` → `{fam, sub}`(TTL = refresh 만료), `auth:user:{sub}:fams` 에 fam 추가. 회전은 `GETDEL` 로 jti 를 소비하고, 없으면 **재사용 탐지** → family 폐기(`auth:fam:{fam}:revoked`) → 401. `revoke_family`·`revoke_user` 제공 | 탈취된 refresh 토큰이 7일간 유효하고 재사용을 알 수 없었다. GETDEL 하나로 원자성이 충분하다(경쟁 시 한쪽만 성공) | Accepted | |
| ADR-016 | 2026-10-12 | 레이트 리밋은 core security 의 `RateLimiter`(Redis 고정 창: INCR + 첫 hit 에 EXPIRE)가 한다. 설정 `AUTH_LOGIN_RATE_LIMIT`(ip+username), `AUTH_LOGIN_IP_RATE_LIMIT`(ip), `AUTH_REGISTER_RATE_LIMIT`(ip). 로그인 성공 시 ip+username 카운터 삭제. 초과는 `TooManyRequestsException`(429, `Retry-After`). 라우트 의존성(`Depends`)으로 건다 — 핸들러 본문이 아니다 | 크리덴셜 스터핑과 해시 연산으로 인한 스레드풀 점유를 막는다. 고정 창은 단순하고 Redis 명령 두 개로 끝난다 | Accepted | |
| ADR-017 | 2026-10-12 | 인증 주입은 core security 의 상태 없는 `Principal`(id, username, is_superuser)과 `get_current_principal`(Bearer → `TokenService` 검증, **DB 조회 없음**), `require_superuser`, `CurrentPrincipal` 타입 별칭으로 한다. 인증 성공 시 `request.state.user_id` 를 채운다. DB 조회(`get_current_user`)는 사용자 엔티티가 필요한 곳에서만 | 기능이 인증을 쓰려고 user 기능을 import 하면 계층 규칙이 깨진다. core 하나만 의존하면 된다. access 만료가 짧아(15분) 상태 없는 판정의 위험이 작다 | Accepted | |
| ADR-018 | 2026-10-12 | 소유권은 core security 의 `OwnershipPolicy.ensure_can_modify(owner_id, principal)` 한 곳에서 판정한다 — 소유자 또는 슈퍼유저, 아니면 403. blog/sns/reply 에 `author_id` 를 더하고(기존 행은 NULL = 슈퍼유저만 수정), 서비스 메서드가 principal 을 인자로 받아 호출한다 | 같은 판정이 기능마다 흩어지면 하나가 빠진다. 서버가 작성자를 채워 요청 본문의 author 를 믿지 않는다(IDOR 방지) | Accepted | |
| ADR-019 | 2026-10-12 | 권한은 **슈퍼유저/일반 2단계**다. `users.is_superuser` 를 더하고, 운영 도구 `scripts/create_superuser.py` 가 서비스·리포지토리를 background 세션으로 조립해 만든다(이미 있으면 승격) | 골격이 RBAC 를 세분화하면 복사한 쪽이 지워야 할 것이 늘어난다. Django `createsuperuser` 와 같은 역할 | Accepted | |
| ADR-020 | 2026-10-12 | SQLAdmin 정책은 바꾸지 않는다 — `/admin` 인증 백엔드는 **영구 비목표**로 유지하고, 배포 환경의 `ADMIN_UNAUTHENTICATED_ACK` 확인과 기동 WARNING(orm-raw-repository ADR-007·ADR-036·C-10)을 그대로 둔다 | API 인증과 관리 화면 인증은 별개 결정이다. 이번 요청은 API 인증만 다룬다 | Accepted | |
| ADR-021 | 2026-10-12 | 기존 그룹의 "인증 체계 개편/도입은 범위 밖" 비목표를 **이 그룹에 한해 대체(supersede)** 한다 — orm-raw-repository charter §2-4 의 "인증 체계 개편", 같은 그룹 residual-risk 잔여 위험 10번(예제 API 무인증), skeleton-purpose-audit charter §2-4 의 "인증 체계 도입". 두 그룹의 design-baseline 변경 이력에 상태 갱신 한 줄을 남긴다(append-only) | 그 비목표들은 각 그룹의 작업 범위를 좁힌 것이지 영구 금지가 아니었다(orm-raw-repository R-001 도 "인증은 로그인 고도화에서 붙인다" 고 적었다). 사용자가 2026-10-12 에 로그인 고도화(제안 9)를 명시 요청했다 | Accepted | orm-raw-repository charter §2-4 "인증 체계 개편" · residual-risk 10번 · skeleton-purpose-audit charter §2-4 "인증 체계 도입" |
| ADR-022 | 2026-10-12 | 협력 객체는 생성자 인자로 받고, 조립은 provider 함수(`Depends`)가 한다. 구현이 하나뿐인 Protocol·팩토리는 만들지 않는다 — Redis 를 쓰는 클래스는 fakeredis 로 실물을 시험한다. 커밋은 핸들러가 응답 DTO 검증 후 1회 하고, 의존성 함수는 커밋하지 않는다 | 사용자 요구("필수 작업은 반드시 주입을 통해"). 단일 구현 추상화는 읽는 비용만 늘린다. 커밋 위치는 orm-raw-repository ADR-008 | Accepted | |

## 4. 불가침 제약 (INVARIANT REQUIREMENTS — 추가 작업이 위반 금지)

- C-1: 각 단계는 새 동작마다 단위 테스트를 갖고, 가능하면 수정 전 코드에서 실패함을 확인한다(fail-on-revert) — REQ-001
- C-2: 같은 목적의 기능은 한 모듈 클래스에 모은다(`ClientIPResolver`·`PasswordHasher`·`TokenService`·`RefreshTokenStore`·`RateLimiter`·`OwnershipPolicy` 등) — REQ-001
- C-3: 조합·데이터 전달·인증·자동 작업은 주입으로 한다 — 협력 객체는 생성자 인자, 조립은 provider 함수. 핸들러 본문이 협력 객체를 직접 만들지 않는다 — REQ-001 (ADR-022)
- C-4: 계층 규칙을 지킨다 — `app/core` → `app/features` 금지, 기능 간 import 금지(문서화된 auth→user 예외만), `app/utils` → 상위 계층 금지 (orm-raw-repository C-11 유지)
- C-5: 커밋은 쓰기 핸들러가 응답 DTO 검증 후 1회 한다. 의존성 함수·Repository·Service 는 커밋하지 않는다 (orm-raw-repository ADR-008 유지)
- C-6: DSN 은 문자열 연결로 만들지 않는다 — `URL.create()`/`make_url()` 로 만들고, 비밀번호는 로그·응답에 `***` 로만 나온다 — ADR-002
- C-7: 잠금 읽기(ORM `with_for_update()`·Raw `for_update=True`)는 writer 에서만 실행되고 읽기 전용 세션에서는 거부된다. 라우터 on/off 와 무관하다 — ADR-003
- C-8: 범용 목록 조회는 결정적 순서를 갖는다(유일 키 보조 정렬 포함). `BaseRepository` 공개 메서드는 8개 그대로다 (orm-raw-repository C-22) — ADR-004
- C-9: DB 시각은 UTC 로 저장하고 naive datetime 은 저장 경계에서 거부한다 — ADR-010
- C-10: Redis 는 필수다 — API 기동은 Redis ping 이 성공해야 하고 `/ready` 는 DB·Redis 를 모두 본다 — ADR-011
- C-11: API 인증은 core 의 `get_current_principal` 주입 하나로 한다. 기능이 인증을 위해 다른 기능을 import 하지 않는다 — ADR-017
- C-12: 비밀번호·토큰·민감 query 값·DB 원문은 로그·접속 로그·응답에 원문으로 남지 않는다 (orm-raw-repository C-5·C-12·C-13 확장) — ADR-006
- C-13: SQLAdmin 정책(무인증 허용 + 배포 환경 확인 플래그 + WARNING)은 이 그룹에서 바꾸지 않는다 — ADR-020
- C-14: Celery 워커는 `INSTALLED_APPS` 에 없는 기능을 import 하지 않는다 — ADR-012
- C-15: CI 의 의존성 설치는 `uv sync --locked` 다 — 락이 `pyproject.toml` 과 어긋나면 실패한다 — ADR-001

## 5. 변경 이력
- v0.1 (2026-10-12): 최초 작성. REQ-001(단계별 도출 D-A1~D-F2), ADR-001~ADR-022, C-1~C-15 등재. ADR-021 로 orm-raw-repository·skeleton-purpose-audit 의 인증 비목표를 이 그룹에 한해 대체.

---
> **연동:** charter 의 계약/불변식은 이 문서의 Active 요구사항·불가침 제약과 **모순되면 안 된다**
> (모순 시 design-baseline 이 우선 — charter 를 고친다). run-log 는 라운드별로 어떤 Req/ADR 를
> 충족·참조했는지 적는다.
