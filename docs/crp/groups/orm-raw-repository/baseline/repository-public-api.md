# 기준선 — BaseRepository 공개 API 사용처 (Phase 0)

> **[2026-08-19 갱신] Phase 3b 에서 이 분석에 따라 공개 계약을 28개 → 8개로 좁혔다.**
> 아래 §1 의 실사용 7개에 `exists` 를 더한 것이 현재 계약이며,
> `tests/core/test_repository_base.py::test_public_contract_is_exactly_these_eight`
> 가 그것을 고정한다. §2 의 20개는 **제거됐다**(호출부 0건 확인 후).
> 이 문서는 그 결정의 근거로 보존한다 — 숫자를 다시 늘리려면 여기부터 반박해야 한다.

> `development-plan.md` Phase 0 의 첫 항목. **Phase 3(공개 계약 축소)의 근거 자료**다.

> 측정 시점: 2026-08-18 · 대상: `app/core/repositories/repository_base.py` 의 `BaseRepository`


공개 메서드 **28개** 중 기능 코드(`app/features/`)가 실제로 호출하는 것은 **7개**다. 나머지 21개는 **호출부가 테스트뿐**이다 — 즉 그 메서드를
검증하기 위해 존재하는 테스트만 있고, 그것을 쓰는 기능은 없다.


## 1. 기능이 실제로 쓰는 메서드

| 메서드 | 시그니처 | 기능 호출 | 테스트 호출 |
|---|---|---:|---:|
| `create` | `(data: dict[str, Any])` | 8 | 21 |
| `get_by_id` | `(id: str)` | 4 | 3 |
| `get_one` | `(**filters: Any)` | 2 | 2 |
| `get_all` | `(skip: int=0, limit: int=100)` | 6 | 2 |
| `count` | `(**filters: Any)` | 9 | 12 |
| `update` | `(id: str, data: dict[str, Any])` | 6 | 2 |
| `delete` | `(id: str)` | 9 | 6 |

### 호출 위치 (기능 코드)

- **`create`**
  - `app/core/apps/registry.py:104`
  - `app/features/auth/services/auth_service.py:44`
  - `app/features/blog/services/blog_service.py:29`
  - `app/features/home/services/user_access_log_service.py:41`
  - `app/features/reply/services/reply_service.py:29`
  - `app/features/sns/services/sns_service.py:29`
  - `app/features/user/services/user_service.py:34`
  - `app/utils/pagination/pagination.py:18`
- **`get_by_id`**
  - `app/features/blog/services/blog_service.py:34`
  - `app/features/reply/services/reply_service.py:34`
  - `app/features/sns/services/sns_service.py:34`
  - `app/features/user/services/user_service.py:39`
- **`get_one`**
  - `app/features/auth/services/auth_service.py:72`
  - `app/features/user/repositories/user_repository.py:17`
- **`get_all`**
  - `app/core/services/services_base.py:19`
  - `app/features/blog/services/blog_service.py:46`
  - `app/features/home/services/user_access_log_service.py:50`
  - `app/features/reply/services/reply_service.py:46`
  - `app/features/sns/services/sns_service.py:46`
  - `app/features/user/services/user_service.py:51`
- **`count`**
  - `app/features/blog/services/blog_service.py:47`
  - `app/features/home/repositories/user_access_log_repository.py:150`
  - `app/features/home/repositories/user_access_log_repository.py:168`
  - `app/features/home/repositories/user_access_log_repository.py:184`
  - `app/features/home/services/user_access_log_service.py:100`
  - `app/features/home/services/user_access_log_service.py:51`
  - `app/features/reply/services/reply_service.py:47`
  - `app/features/sns/services/sns_service.py:47`
  - `app/features/user/services/user_service.py:52`
- **`update`**
  - `app/celery/app.py:17`
  - `app/features/blog/services/blog_service.py:54`
  - `app/features/reply/services/reply_service.py:54`
  - `app/features/sns/services/sns_service.py:54`
  - `app/features/user/services/user_service.py:59`
  - `app/utils/authenticator/auth.py:59`
- **`delete`**
  - `app/core/repositories/crud_base.py:95`
  - `app/features/blog/api/routers/v1/blog.py:104`
  - `app/features/blog/services/blog_service.py:62`
  - `app/features/reply/api/routers/v1/reply.py:104`
  - `app/features/reply/services/reply_service.py:62`
  - `app/features/sns/api/routers/v1/sns.py:104`
  - `app/features/sns/services/sns_service.py:62`
  - `app/features/user/api/routers/v1/user.py:108`
  - `app/features/user/services/user_service.py:67`

## 2. 기능 호출 0건 — 테스트만 있는 메서드

| 메서드 | 시그니처 | 테스트 호출 |
|---|---|---:|
| `bulk_create` | `(data_list: list[dict[str, Any]])` | 1 |
| `get_by_id_or_raise` | `(id: str)` | 2 |
| `get_many` | `(skip: int=0, limit: int=100, **filters: Any)` | 1 |
| `exists` | `(id: str)` | 8 |
| `exists_by` | `(**filters: Any)` | 2 |
| `get_by_id_with` | `(id: str, relations: list[str] | None=None, strategy: str='selectin')` | 1 |
| `get_one_with` | `(relations: list[str] | None=None, strategy: str='selectin', **filters: Any)` | 1 |
| `get_many_with` | `(relations: list[str] | None=None, strategy: str='selectin', skip: int=0, limit: int=100, **filters: Any)` | 1 |
| `get_all_with` | `(relations: list[str] | None=None, strategy: str='selectin', skip: int=0, limit: int=100)` | 1 |
| `get_by_ids_with` | `(ids: list[str], relations: list[str] | None=None, strategy: str='selectin')` | 1 |
| `get_partial` | `(columns: list[str], skip: int=0, limit: int=100, **filters: Any)` | 1 |
| `get_by_id_partial` | `(id: str, columns: list[str])` | 2 |
| `get_in_batches` | `(batch_size: int=100, relations: list[str] | None=None, **filters: Any)` | 1 |
| `get_with_join` | `(join_model: type, join_condition: Any, relations: list[str] | None=None, skip: int=0, limit: int=100, **filters: Any)` | 0 |
| `count_with_relation` | `(relation: str, **filters: Any)` | 0 |
| `bulk_update` | `(ids: list[str], data: dict[str, Any])` | 1 |
| `update_by` | `(data: dict[str, Any], **filters: Any)` | 1 |
| `bulk_delete` | `(ids: list[str])` | 1 |
| `delete_by` | `(**filters: Any)` | 1 |
| `get_or_create` | `(defaults: dict[str, Any] | None=None, **filters: Any)` | 2 |
| `update_or_create` | `(defaults: dict[str, Any] | None=None, **filters: Any)` | 2 |

## 3. 이 표에서 읽어야 할 것

`get_with_join` 과 `count_with_relation` 은 **테스트 호출조차 0건**이다. 나머지 19개는
"이 메서드가 동작하는가"를 확인하는 테스트만 달려 있고 그것을 쓰는 기능이 없다.

공개 계약이 넓으면 대가가 실재한다.

* Raw Base(`RawRepositoryBase`)를 **같은 넓이로** 맞추려면 28개를 두 번 구현해야 한다.
  ORM/Raw 가 "Repository 구현만 다르다"(ADR-002)는 계약이 28개짜리 계약이 되는 것이다.
* 넓은 계약은 전부 회귀 대상이다 — 21개가 기능 없이 테스트 유지비만 만든다.
* `get_by_id(id: str)` 처럼 PK 타입이 `str` 로 고정된 것도 계약 폭이 넓어 눈에 안 띈다
  (development-plan §5.3 의 `BaseRepository[ModelT, PrimaryKeyT]` 로 교정 예정).

### Phase 3 로 넘기는 결정

이 문서는 **삭제 목록이 아니라 근거 자료**다. 실제 축소는 Phase 3 에서 하고, 그때
호환 wrapper 를 통한 점진 전환(development-plan Phase 3)을 따른다. Phase 0 에서는
**현재 상태를 고정**하는 것까지가 범위다.

> 참고: sibling 저장소 `fastapi-default-project-structure` 는 같은 분석 뒤 공개 계약을
> **최소 CRUD 8개**로 좁혔다(`9a38050`). 이 저장소의 목표치도 그 근방이 될 것이나,
> 숫자를 먼저 정하지 않는다 — 위 §1 의 실사용 7개가 출발점이다.
