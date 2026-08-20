# 학습 경로 검수 보고서

| 항목 | 값 |
|---|---|
| 작업 그룹 | `learning-path` |
| 검수일 | 2026-08-20 |
| 검수 기준 | "이 구조를 쓰는 개발자가 **Django 스타일 수동 등록**과 **ORM/Raw 워크플로**를 이해하고 학습할 수 있는가" |
| 대상 | `main` (`aec451d`) |
| 판정 | **부분 달성** — Django 스타일 ✅ / ORM·Raw 학습 경로 ❌ |

> 이 문서는 다음 세션이 **바로 착수할 수 있도록** 쓰였다. §3 에 작업 목록이,
> §4 에 순서가, §5 에 완료 판정 기준이 있다.

---

## 1. 무엇을 검수했나

목적이 "동작이 옳은가" 가 아니라 **"학습자가 이해할 수 있는가"** 이므로 세 축으로 봤다.

| 축 | 질문 |
|---|---|
| A. 진입 경로 | 처음 온 사람이 읽는 문서가 두 주제를 다루는가 |
| B. 코드 자체 | 코드를 열었을 때 그 코드가 학습을 돕는가 |
| C. 심화 경로 | 진입 문서에서 상세 문서로 이어지는가 |

---

## 2. 측정 결과

### 2-1. Django 스타일 수동 등록 — **달성** ✅

| 문서 | `INSTALLED_APPS` | `AppConfig` |
|---|---|---|
| `README.md` | 11회 | 5회 |
| `docs/QUICKSTART.md` | 4회 | 1회 |
| `docs/ARCHITECTURE.md` | 12회 | 7회 |
| `docs/project-guide/v1.0/` | 5개 파일 | — |

세 진입 문서 전부가 다루고, 핵심 개념("디렉터리를 만드는 것만으로는 설치되지 않는다")도
명시돼 있다. `docs/django-style-app-registry/DJANGO-APP-COMPATIBILITY.md` 로 심화 경로도 있다.

**이 축은 목적을 달성했다. 손댈 필요 없다.**

### 2-2. ORM/Raw 워크플로 — **미달성** ❌

| 키워드 | README | QUICKSTART | ARCHITECTURE | project-guide |
|---|---|---|---|---|
| `Raw` | **1회** | **0** | **0** | 5개 파일 |
| `RawRepositoryBase` | **0** | **0** | **0** | **0** |
| `catalog` (ORM 예제) | **0** | **0** | 1회* | **0** |
| `reports` (Raw 예제) | **0** | **0** | 1회* | **0** |

\* `INSTALLED_APPS` 목록에 이름만 등장

**학습자가 진입 문서 3종을 전부 읽어도 다음을 모른다:**

1. Raw Repository 계층이 존재한다는 사실
2. 언제 ORM 을 쓰고 언제 Raw 를 쓰는지 판단 기준
3. Phase 5 에서 "나란히 비교하라고" 만든 예제 두 개의 존재
4. Raw 를 쓸 때 지켜야 하는 규칙(named binding, `query_name`, intent, commit 금지)

### 2-3. 코드 자체 — **달성** ✅

예제 두 개가 서로를 가리킨다. 한쪽을 열면 반대쪽을 찾을 수 있다.

| 파일 | 상대 참조 |
|---|---|
| `catalog/repositories/product_repository.py` | reports 2회 |
| `reports/repositories/sales_report_repository.py` | catalog 1회 |

Base 클래스 docstring 에도 규칙과 근거가 들어 있다(`raw_crud_base.py`, `raw_repository_base.py`).
**코드 층은 학습을 돕는다. 손댈 필요 없다.**

### 2-4. 심화 경로 — **끊김** ❌

내용은 있는데 **도달할 수 없다.**

| 문서 | 무엇이 있나 | 문제 |
|---|---|---|
| `docs/orm-raw-repository/2026-08-13/workflow-guide.md` | ORM·Raw 워크플로 전체(1003줄) | **설계 문서**로 분류돼 날짜 폴더 아래 있다. 진입 문서가 가리키지 않는다 |
| `docs/orm-raw-repository/2026-08-13/requirements.md` §4.4 | "Raw SQL 사용 원칙" — 선택 기준 | 위와 같음. 요구명세는 학습자가 읽을 문서가 아니다 |
| `docs/project-guide/v1.0/` (8개 문서) | 학습용으로 쓰인 유일한 문서 묶음 | **진입 문서 3종이 참조 0회.** 발견할 방법이 없다 |

---

## 3. 결함 목록

| ID | 심각도 | 무엇이 | 근거 |
|---|---|---|---|
| **L-001** | **HIGH** | Raw 층이 진입 문서에서 통째로 누락 | `RawRepositoryBase` 가 README·QUICKSTART·ARCHITECTURE **전부 0회** |
| **L-002** | **HIGH** | `docs/project-guide/v1.0/` 가 Phase 4~7 을 모른다 | 최종 갱신 `2026-08-18 16:48`, Raw 층 도입 `2026-08-20 09:18` — **이틀 뒤처짐**. `RawRepositoryBase`·`catalog`·`reports` 0회 |
| **L-003** | MED | 진입 문서가 `project-guide` 를 가리키지 않는다 | 참조 **0회**. 학습용 문서 8개가 고아 상태 |
| **L-004** | MED | ORM/Raw **선택 기준**이 학습 문서에 없다 | `requirements.md §4.4` 에만 존재 — 요구명세는 학습 경로가 아니다 |
| **L-005** | LOW | README 제목이 `FastAPI **Default** Project Structure` | 이 저장소는 passive-style. 학습자가 보는 **첫 문장**이 정체성과 어긋난다 |
| **L-006** | LOW | README 구조 트리에 예제 두 개가 없다 | `<name>` 일반형만 있고 `catalog`·`reports` 실물이 안 보인다 |

### 결함의 성격

만든 것이 잘못된 게 아니다. **만든 것과 가르치는 것 사이가 끊겼다.**

Phase 4~7 은 Raw Base·예제 두 개·게이트·검사를 모두 만들었고 CI 도 통과한다. 그런데 그
과정이 CRP 문서(`docs/crp/groups/orm-raw-repository/`)와 설계 문서에만 기록됐다.
**학습자가 읽는 문서는 Phase 3 시점에 멈춰 있다.**

---

## 4. 작업 목록 (착수용)

### T-1. `docs/project-guide/v1.0` → `v1.1` 갱신 — **가장 큰 작업**

`v1.0` 을 남기고 `v1.1` 을 새로 만든다(버전 폴더 규약 유지).

| 문서 | 추가·수정할 것 |
|---|---|
| `03-core-components-and-features.md` | `RawCRUDBase`·`RawRepositoryBase` 계층 추가. `BaseRepository` 공개 계약이 8개로 좁혀진 것 반영(ADR-016) |
| `06-data-and-transaction-workflow.md` | Raw 경로의 트랜잭션 규칙. intent 기반 read/write 판정(ADR-017), commit 금지, read-only 세션 차단 |
| `07-feature-workflows.md` | **ORM(`catalog`) / Raw(`reports`) 두 워크플로를 나란히**. 이 문서가 핵심 산출물 |
| `05-app-registry-and-startup-workflow.md` | 세션 Dependency 이름 변경 반영(ADR-009 — 옛 이름 제거됨) |
| `08-operations-security-quality-workflow.md` | `scripts/review_gate.py` 8단계, `pytest -m mysql/browser` |
| `README.md` (guide 내) | v1.1 목차 |

**새로 쓸 문서 1개** — `09-orm-vs-raw-decision.md`:
- 언제 ORM, 언제 Raw (`requirements.md §4.4` 를 학습자 언어로)
- Raw 를 쓸 때의 규칙 5가지: named binding / `query_name` 상수 / intent 명시 /
  commit 금지 / `RowMapping` → DTO 검증
- 두 예제의 파일 대조표

### T-2. 진입 문서에 학습 경로 연결

| 파일 | 작업 |
|---|---|
| `README.md` | ① 제목 `Default` → `Django Passive Style` (L-005) ② 구조 트리에 `catalog`·`reports` 실물 추가 (L-006) ③ "핵심 패턴" 에 Raw Repository 절 추가 ④ 최상단에 학습 경로 안내(→ QUICKSTART → project-guide) |
| `docs/QUICKSTART.md` | "새 기능 추가" 절에 **ORM/Raw 선택** 한 문단 + 예제 두 개 위치 |
| `docs/ARCHITECTURE.md` | 계층 설명에 Raw Base 추가. `project-guide` 로의 링크 |

### T-3. 학습 경로 자체를 기계로 잠그기

`tests/test_docs_references.py` 를 확장한다. 지금은 "죽은 참조가 없는가" 만 본다 —
**"학습에 필요한 것이 있는가"** 는 아무도 안 본다.

```python
# 진입 문서가 반드시 다뤄야 하는 개념
REQUIRED_IN_ENTRY_DOCS = {
    "INSTALLED_APPS", "AppConfig",          # Django 스타일
    "RawRepositoryBase", "BaseRepository",  # ORM/Raw 두 계층
    "catalog", "reports",                   # 예제 두 개
}
```

L-001·L-002 가 다시 생기면 실패해야 한다. 이게 없으면 다음 Phase 에서 또 끊긴다.

### T-4. 문서 최신성 검사

`project-guide` 가 이틀 뒤처진 것을 아무도 몰랐다. 코드의 공개 심볼이 바뀌었는데
가이드가 그 이름을 모르면 실패하는 검사를 둔다(T-3 에 함께).

---

## 5. 완료 판정 기준

작업이 끝났는지는 **아래를 전부 만족할 때** 판정한다.

- [ ] `RawRepositoryBase` 가 README·QUICKSTART·ARCHITECTURE 중 **최소 2곳**에 등장
- [ ] `catalog`·`reports` 가 README 구조 트리에 실물로 등장
- [ ] "언제 ORM, 언제 Raw" 판단 기준이 **학습 문서**(설계 문서 아님)에 존재
- [ ] 진입 문서에서 `project-guide` 로의 링크 존재
- [ ] `project-guide v1.1` 이 Phase 4~7 산출물을 반영
- [ ] T-3 검사가 있고, 위 항목을 지우면 **실패**한다(fail-on-revert 확인)
- [ ] `scripts/review_gate.py` 8단계 통과
- [ ] 학습자 시나리오 수동 검증: "README 만 읽고 Raw 기능을 하나 만들 수 있는가"

---

## 6. 권장 순서

```
1. T-1 (project-guide v1.1)     ← 내용의 원천. 여기서 쓴 것을 나머지가 참조한다
2. T-2 (진입 문서 연결)          ← 1 이 있어야 가리킬 대상이 생긴다
3. T-3 + T-4 (기계 검사)         ← 1·2 를 잠근다. 순서상 마지막이어야 무엇을 잠글지 안다
4. 게이트 + 커밋
```

**T-1 을 먼저 하는 이유**: T-2 는 "어디를 가리킬지" 가 정해져야 쓸 수 있고, T-3 은
"무엇을 잠글지" 가 정해져야 쓸 수 있다. 반대 순서로 하면 두 번 고치게 된다.

---

## 7. 하지 않아도 되는 것

검수에서 **문제없음**으로 확인된 것들이다. 건드리지 말 것.

- **코드의 학습 안내** — 예제 두 개가 서로를 가리키고, Base docstring 에 규칙과 근거가 있다
- **Django 스타일 문서화** — 진입 문서 3종 + 전용 심화 문서까지 갖췄다
- **`docs/orm-raw-repository/2026-08-13/`** — 설계 문서로서는 완결돼 있다. 학습 문서로
  옮기지 말고, 학습 문서가 **그 내용을 다시 쓰는** 방향이 맞다(대상 독자가 다르다)
- **CRP 기록** — `docs/crp/groups/orm-raw-repository/` 는 "왜 그렇게 했나"의 원본이다

---

## 8. 참고 — 근거 명령

이 보고서의 수치는 아래로 재현한다.

```bash
# 2-1, 2-2 키워드 분포
for kw in INSTALLED_APPS AppConfig Raw RawRepositoryBase catalog reports; do
  printf "%-20s README=%s QUICK=%s ARCH=%s\n" "$kw" \
    "$(grep -c "$kw" README.md)" \
    "$(grep -c "$kw" docs/QUICKSTART.md)" \
    "$(grep -c "$kw" docs/ARCHITECTURE.md)"
done

# 2-4 project-guide 참조 여부
grep -c "project-guide" README.md docs/QUICKSTART.md docs/ARCHITECTURE.md

# L-002 시점 대조
git log -1 --format="%ci" -- docs/project-guide/
git log -1 --format="%ci" -- app/core/repositories/raw_repository_base.py
```
