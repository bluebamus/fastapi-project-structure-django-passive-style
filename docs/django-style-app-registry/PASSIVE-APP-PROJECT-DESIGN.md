# 이 저장소는 무엇이고, 왜 이렇게 생겼는가

## 1. 이 문서의 역할

**"왜"** 를 다룬다. 폴더 구조·조립 순서·API 목록 같은 **"무엇"** 은
[`docs/guides/ARCHITECTURE.md`](../guides/ARCHITECTURE.md) 가, **"어떻게 쓰나"** 는
[`docs/project-guide/v1.1/`](../project-guide/v1.1/README.md) 가 다룬다.
세 문서가 어긋나면 코드가 정답이고, ARCHITECTURE 가 아키텍처 SSOT 다.

Django 와 동일한 범위와 그렇지 않은 범위는
[`DJANGO-APP-COMPATIBILITY.md`](DJANGO-APP-COMPATIBILITY.md) 를 본다.

## 2. 이 저장소가 푸는 문제

FastAPI 는 라우터와 의존성을 자유롭게 구성할 수 있다. 그 자유가 프로젝트가 커질 때
비용으로 돌아오는 지점이 있다.

- 지금 이 애플리케이션에 **어떤 기능이 설치돼 있는가**? 어디를 보면 알 수 있는가?
- 기능을 하나 빼려면 몇 개 파일을 고쳐야 하는가?
- 라우터·모델·관리자 화면 등록이 기능마다 다른 방식이면, 새 사람은 무엇을 따라야 하는가?

이 저장소의 답은 한 줄이다.

> **앱의 설치 여부와 순서는 사람이 한 곳에서 명시하고, 설치된 앱 내부의 결선은
> 컨벤션이 처리한다.**

| | 결정 주체 |
|---|---|
| 어떤 앱을 설치할지, 어떤 순서로 | 사람 (`config.INSTALLED_APPS`) |
| 설치된 앱의 Router·Models·Admin 결선 | registry (컨벤션) |

이 분업이 이 저장소의 전부다. 나머지는 그 결과다.

## 3. 설계 원칙

### 3.1 설치는 목록에만 있다

`app/features/` 에 디렉터리를 만드는 것으로는 아무 일도 일어나지 않는다.
`config.INSTALLED_APPS` 에 config class 경로를 한 줄 넣어야 Router·Models·Admin·
`ready()` 가 붙는다. 목록에서 빼면 디렉터리가 남아 있어도 전부 떨어진다.

디렉터리 자동 스캔을 쓰지 않는 대가로 얻는 것:

- 설치 범위를 설정 한 곳에서 읽을 수 있다.
- 로드 순서를 목록 순서로 통제한다(**순서가 계약이다** — 새 앱은 뒤에 둔다).
- 실험 중인 앱을 디렉터리째 두고 비활성으로 유지할 수 있다.
- 앱을 빼는 일이 중앙 부트스트랩 수정으로 번지지 않는다.

`main.py` 는 `create_app()` 호출만 남는다. 새 기능을 붙일 때 `main.py`·
`migrations/env.py`·`session.py` 는 손대지 않는다.

### 3.2 URL 은 라우터 파일로 수동 관리한다

경로를 프레임워크가 추론하지 않는다. 세 단계가 각각 자기 조각만 소유한다.

```text
v1/<view>.py       엔드포인트 경로 (/products)
router.py          버전·기능 prefix 와 tag  (/v1/catalog, tags=["Catalog"])
AppConfig          마운트 prefix            (/api)
  → /api/v1/catalog/products
```

registry 는 `api/routers/router.py` 의 `<label>_router` 를 읽어 마운트한다.
**module 이 없는 앱은 라우트가 없는 것으로 넘어가지만, module 은 있는데 공개 이름이
없거나 내부 import 가 깨지면 기동을 실패시킨다** — 오타 하나가 "이 앱은 라우터가
없나 보다" 로 흡수되면 라우트가 사라진 것을 아무도 모른다.

두 앱이 같은 method+path 를 등록하면 조용히 덮지 않고 기동에 실패한다.

### 3.3 기능 중심 구조

계층별 전역 폴더에 모든 Router 나 Service 를 모으지 않는다. 하나의 기능에 필요한
코드는 `app/features/<name>/` 경계 안에 둔다. 기능 단위로 복사·삭제할 수 있어야
"탈착 가능한 앱" 이라는 말이 성립한다.

현재 설치된 앱 8개는 그 구조의 참조 구현이기도 하다.

| 앱 | 역할 |
|---|---|
| `home` | 접속 로그 조회·통계, 로그 sink 결선(`ready()` 사용 예) |
| `blog` · `reply` · `sns` · `user` | 기본 CRUD 참조 구현 |
| `auth` | 가입·로그인·토큰 (모델을 자기 것으로 갖지 않는 앱의 예) |
| `catalog` | **ORM 예제** — `BaseRepository` |
| `reports` | **Raw SQL 예제** — `RawRepositoryBase` |

마지막 두 개는 도메인 기능이 아니라 학습용이다. 같은 구조에서 데이터 접근만 갈렸을 때
코드가 어떻게 달라지는지 나란히 보여준다.

### 3.4 예측 가능한 계층과 트랜잭션 경계

```text
Router → Depends(get_<name>_service) → Service → Repository → AsyncSession → DB
     ↑ commit() 은 여기서
```

| 계층 | 책임 | 하지 않는 일 |
|---|---|---|
| Router(view) | HTTP 입출력, **커밋 시점 결정** | ORM 쿼리, 도메인 규칙 |
| Dependency | 세션 종류 선택, Service 조립 | 비즈니스 실행, 커밋 |
| Service | 유스케이스와 도메인 규칙 | HTTP 객체, SQL 문자열 |
| Repository | 데이터 접근 (ORM 또는 Raw) | 커밋, HTTP 상태 결정 |

**커밋은 쓰기 핸들러 본문이 한 번 한다.** Repository 도 Service 도 Dependency 도
스스로 커밋하지 않고, 예외로 빠져나가면 세션 dependency 의 teardown 이 rollback 한다.

> 이전에는 의존성이 `yield` 이후에 커밋했다. FastAPI 상위 버전에서 yield dependency 의
> 종료 코드가 **응답 전송 후** 실행되도록 바뀌면서, 커밋이 실패해도 클라이언트는 이미
> `201` 을 받은 상태가 됐다. 커밋을 핸들러로 옮기면 실패가 응답 코드에 정직하게 반영된다.
> 구조 증거: `tests/test_read_path_no_commit.py`.

별도의 UnitOfWork 계층은 두지 않는다. 한 요청에서 여러 aggregate 를 복잡하게 조율해야
하는 프로젝트라면 추가할 수 있지만, 기본 골격에서는 계층 수와 학습 비용을 줄이는 쪽을
택했다.

## 4. 의도적으로 선택하지 않은 것

### 4.1 디렉터리 자동 스캔

`app/features/*` 를 순회해 모든 앱을 자동 활성화하지 않는다. 앱을 만들면 곧바로
붙는 편의가 있지만, 설치 범위와 순서가 파일 시스템 상태에 암묵적으로 의존한다.
자동 스캔은 형제 저장소(active-style)가 담당하고, 여기서는 명시성을 유지한다.

### 4.2 기능 간 강한 결합

기능 앱의 탈착성을 위해 기능 간 직접 import·FK·relationship 을 기본 예제의 중심으로
삼지 않는다. 실제 제품에서 관계를 추가할 수 있지만, 그때는 앱 제거 가능성과 migration
순서를 함께 설계해야 한다.

### 4.3 Admin 인증

SQLAdmin 에 인증 백엔드를 **만들지 않는다**(영구 비목표). 대신 사고와 의도를 구분한다.

- 개발 기본값은 `ADMIN=true` 다 — 받자마자 DB 를 들여다볼 수 있어야 한다는 판단.
  그 말은 **`/admin` 에 자격증명이 없다**는 뜻이다.
- production/staging 에서는 `ADMIN_UNAUTHENTICATED_ACK` 승인 없이 기동을 거부한다.

관리자 API 를 권한으로 보호하는 Dependency 는 이 저장소에 없다. 필요하면 새로
설계할 일이며, 있다고 전제하지 않는다.

## 5. 확장 시 지켜야 할 원칙

- 앱 설치 여부는 `config.INSTALLED_APPS` 에서만 결정한다.
- `app/core` 에 특정 기능 앱 import 를 추가하지 않는다. 기능이 core 에 붙어야 하면
  등록 훅으로 연결한다(예: `access_log_sink.register_sink()`).
- Router 에서 직접 ORM 을 쓰지 않는다. Service·Repository 는 커밋하지 않는다.
- 선택 모듈 내부 오류를 무시하지 않는다.
- 새 모델은 migration 과 스키마 정합 테스트를 함께 추가한다.
- 기능을 제거할 때 Router 뿐 아니라 Models·Admin·migration 영향을 함께 확인한다
  (**목록에서 빼도 테이블은 지워지지 않는다** — `DJANGO-APP-COMPATIBILITY.md` §7).
- 문서와 코드가 충돌하면 코드를 검증한 뒤 문서를 갱신한다.

## 6. 테스트가 보장하는 구조적 계약

이 저장소의 테스트는 CRUD 성공만 보지 않는다. 위 원칙이 조용히 깨지는 것을 막는다.

| 계약 | 검증 위치 |
|---|---|
| 수동 등록 — 미등록 앱은 어디에도 없다 | `tests/core/apps/test_manual_registration.py` |
| 등록 순서 보존, 중복 name·label 거부 | `tests/core/apps/test_population_order.py` · `test_registry_errors.py` |
| 선택 모듈 부재와 내부 import 실패 구분 | `tests/core/apps/test_optional_modules.py` |
| 컨벤션 결선과 route 충돌 | `tests/core/apps/test_wiring.py` |
| core 가 웹 스택에 의존하지 않음 | `tests/core/apps/test_core_independence.py` |
| `ADMIN=false` 에서 sqladmin 미로드 | `tests/core/test_admin_lazy_loading.py` |
| 트랜잭션 경계 — 조회는 커밋 0회 | `tests/test_read_path_no_commit.py` |
| migration metadata == 등록 모델 | `tests/core/test_alembic_metadata.py` |
| 문서가 코드와 어긋나지 않음 | `tests/test_docs_consistency.py` · `tests/test_docs_references.py` |

## 7. 어떻게 여기까지 왔는가

설계가 한 번에 정해진 것이 아니라 몇 번 뒤집혔다. 되돌아온 자리를 남겨 둔다 —
같은 자리를 다시 밟지 않기 위해서다.

| 시점 | 변화 |
|---|---|
| 2026-06 | `fastapi-default-project-structure` 를 기반으로 passive-style 분기. 수동 등록 SSOT 확립 |
| 2026-07 | 한때 표준 FastAPI 배선(`main.py` 의 `include_router` 나열)으로 되돌렸다 |
| 2026-08-11 | `app/domains` → `app/features` 로 개명. SQLAdmin ModelView 소유권을 기능으로 이전 |
| 2026-08-12 | default `a980b71` tracked tree 위에 **Django app registry lifecycle 이식**. `app/core/apps/` 신설, 설치 SSOT 를 `config.INSTALLED_APPS` 로 일원화 |
| 2026-08-13 | 인메모리 레이트 리밋 제거 — 워커별로 갈라져 실질 한도를 보장하지 못했다. 필요하면 프록시·게이트웨이 단에서 건다 |
| 2026-08-19 | ORM/Raw 두 Repository 계열과 예제 2종(`catalog`·`reports`) 추가 |
| 2026-08-20 | 학습 경로 정비 — `project-guide/v1.1` 신설, 진입 문서와 심화 문서를 연결하고 검사로 잠갔다 |

2026-07 의 되돌림이 특히 값지다. 명시적 `include_router` 나열은 "무엇이 설치됐는지"를
`main.py` 에서 볼 수 있게 해주지만, 앱이 늘수록 그 파일이 모든 기능 추가의 공유
편집 지점이 된다. registry 로 돌아온 것은 그 비용을 다시 지불하지 않기로 한 결정이다.

## 8. 이 저장소의 성격

세 가지를 결합한 FastAPI 개발용 기본 구조다.

1. **Django 식 명시적 앱 관리** — 설치 앱과 순서를 `INSTALLED_APPS` 로 통제
2. **FastAPI 식 조립과 의존성 주입** — `APIRouter` 와 `Depends` 를 그대로 쓴다
3. **기능별 계층 분리** — 기능 앱 안에서 Router·Dependency·Service·Repository·Model 일관

핵심 가치는 자동화가 아니라 **명시적인 선택과 반복 가능한 결선의 균형**이다.
앱을 쓸지는 사람이 결정하고, 쓰기로 한 앱을 붙이는 반복 작업은 registry 가 한다.
