# 운영 배포 체크리스트

이 문서만 보고 운영 배포에 필요한 보안 설정과 마이그레이션 절차를 끝낼 수 있어야 한다.
값의 의미는 [`.env.example`](../.env.example)에 각 항목별로 적혀 있다.

---

## 1. 배포 전 설정 (필수)

### 1-1. 애플리케이션

| 키 | 운영 값 | 안 하면 |
|---|---|---|
| `DEBUG` | `false` | `/docs`·`/openapi.json`이 공개되고, 시작 시 `create_all()`이 돌아 Alembic과 스키마 관리 주체가 둘로 갈린다 |
| `ENV` | `production` | Admin 차단 검증이 동작하지 않는다(아래 1-2) |
| `ADMIN` | `false` | — 애초에 `production`에서 `true`면 **서버가 기동을 거부**한다 |
| `ADMIN_API_TOKEN` | 난수 문자열 | 접속로그·사용자 API가 전부 401로 닫힌다(안전하지만 못 쓴다) |
| `HOST` | 배포 환경에 맞게 | 기본 `127.0.0.1`은 컨테이너 외부에서 접근되지 않는다 |

토큰 생성:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 1-2. Admin은 운영에 존재하지 않는다

SQLAdmin에는 **인증이 없다**(설계 결정). 따라서 안전은 로그인이 아니라 노출 차단으로 확보한다:

- `ADMIN` 기본값은 `false`다. 명시적으로 켠 경우에만 뜬다.
- `ENV=production` + `ADMIN=true` 조합은 **설정 로드 단계에서 거부**되어 서버가 기동하지 않는다.
- 운영 데이터를 화면으로 봐야 한다면 Admin이 아니라 별도 도구를 쓴다.

### 1-3. CORS

`CORS_ALLOW_ORIGINS=["*"]`와 `CORS_ALLOW_CREDENTIALS=true`는 **함께 쓸 수 없다**(CORS 스펙).
설정 로드 시 거부되어 서버가 뜨지 않는다. 자격 증명이 필요하면 Origin을 명시한다:

```env
CORS_ALLOW_ORIGINS=["https://app.example.com"]
CORS_ALLOW_CREDENTIALS=true
```

> 운영에서 wildcard Origin 자체를 금지할지는 정하지 않았다. 공개 API라면 정상 구성일 수 있어
> 일률 금지의 근거가 없다고 판단했다. 조직 정책이 있다면 배포 파이프라인에서 검사한다.

### 1-4. 접속 로그 — 프록시와 개인정보

**리버스 프록시/로드밸런서 뒤에 둔다면 반드시 설정한다:**

```env
ACCESS_LOG_TRUSTED_PROXIES=["10.0.0.0/8"]
```

설정하지 않으면 `X-Forwarded-For`/`X-Real-IP`를 **무시하고** 실제 TCP 피어(즉 프록시)의
주소를 기록한다. 안전하지만 모든 로그의 IP가 프록시 주소가 된다.

반대로 프록시가 없는데 설정하면 **누구나 IP를 위조**할 수 있다. 실제 배치와 일치시킨다.

그 밖의 기본 동작(별도 설정 없이 적용됨):

- 민감한 query parameter(`token`·`password`·`api_key` 등)의 **값**은 `[REDACTED]`로 저장된다.
- 세션 ID는 원문 대신 `SESSION_SECRET_KEY` 기반 HMAC으로 저장된다.
  → **`SESSION_SECRET_KEY`를 운영 값으로 바꾼다.** 기본값을 쓰면 해시가 예측 가능해진다.
- 보존 기간은 `ACCESS_LOG_RETENTION_DAYS`(기본 90일)다.

### 1-5. 비밀 값 교체

기본값이 그대로 남아 있으면 안 되는 항목:

- `SESSION_SECRET_KEY`
- `ACCESS_TOKEN_SECRET_KEY` / `REFRESH_TOKEN_SECRET_KEY` (현재 미사용이지만 기본값 방치는 피한다)
- `MYSQL_PASSWORD`
- `ADMIN_API_TOKEN`

---

## 2. 마이그레이션 절차

운영은 `DEBUG=false`라 시작 시 테이블을 만들지 **않는다**. Alembic이 유일한 스키마 경로다.

```bash
# 1. 현재 리비전 확인
uv run alembic current

# 2. 적용
uv run alembic upgrade head

# 3. 확인 — 5개 테이블이 있어야 한다
#    users / blog_posts / replies / sns_posts / user_access_logs
```

- Alembic은 항상 **primary(쓰기) 서버**에서 실행한다. replica는 읽기 전용이다.
- DSN을 따로 주려면 `ALEMBIC_DATABASE_URL`을 쓴다(미설정 시 primary DSN에서 유도).
- 롤백은 `uv run alembic downgrade -1`. 왕복(head → base → head)은 CI가 매번 검증한다.

---

## 3. 접속 로그 정리 작업 등록

보존 기간이 지난 로그는 자동으로 사라지지 않는다. 스케줄러에 등록한다.

```python
# celery beat 예시
beat_schedule = {
    "purge-old-access-logs": {
        "task": "home.purge_old_access_logs",
        "schedule": crontab(hour=4, minute=0),  # 매일 04:00
    },
}
```

반복 실행해도 안전하다(지울 것이 없으면 0을 반환). Admin 화면의 접속로그 삭제는
막혀 있다 — 감사 기록의 삭제는 클릭이 아니라 이 정책이 담당한다.

---

## 4. 배포 후 확인

```bash
# 헬스체크
curl -s https://<host>/health

# API 문서가 닫혔는지 (DEBUG=false면 404)
curl -s -o /dev/null -w '%{http_code}\n' https://<host>/docs

# Admin이 없는지 (404)
curl -s -o /dev/null -w '%{http_code}\n' https://<host>/admin

# 관리자 API가 토큰 없이는 401인지
curl -s -o /dev/null -w '%{http_code}\n' https://<host>/api/v1/home/access-logs

# 토큰이 있으면 200인지
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "Authorization: Bearer $ADMIN_API_TOKEN" \
  https://<host>/api/v1/home/access-logs
```

기대값: `200` / `404` / `404` / `401` / `200`

---

## 5. 새 앱을 추가할 때

이 저장소는 **수동 등록(passive)** 이다. 디렉터리를 만드는 것만으로는 앱이 켜지지 않는다.

```bash
python -m scripts.new_app <name> [--with-admin]
```

생성기가 마지막에 출력하는 안내대로 `config.py`의 `INSTALLED_APPS`에 이름을 추가한다.
등록하지 않으면 라우터·모델·Admin 중 무엇도 연결되지 않는다.

새 엔드포인트를 추가했다면 **인증이 필요한지 판단**하고, 필요하면
`app/utils/authenticator`의 `require_admin`을 라우터에 건다. 판단 결과와 무관하게
`tests/core/test_endpoint_inventory.py`의 목록을 갱신해야 CI가 통과한다.

---

## 6. CI가 막아주는 것

`.github/workflows/ci.yml`이 아래를 검사한다. 로컬에서 같은 명령으로 재현할 수 있다.

| 검사 | 명령 |
|---|---|
| 린트 | `uv run ruff check` |
| 포맷 | `uv run ruff format --check` |
| 타입 | `uv run mypy .` |
| 보안 정적분석 | `uv run bandit -r app config.py main.py -x '*/tests/*' -q` |
| 테스트 + 커버리지 게이트 | `rm -f .coverage .coverage.*` 후 `uv run pytest --cov` |
| 마이그레이션 왕복 | `uv run pytest tests/core/test_migration_chain.py` |

커버리지 측정 전 `.coverage*`를 지우는 이유: 이전 실행의 데이터가 남아 있으면
branch/statement 형식이 섞여 `Can't combine branch coverage data with statement data`로 실패한다.
