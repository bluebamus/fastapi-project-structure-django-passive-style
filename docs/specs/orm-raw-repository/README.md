# ORM/Raw Repository 설계 명세

ORM(`BaseRepository`)과 Raw SQL(`RawCRUDBase`·`RawRepositoryBase`) 이중 데이터 접근 구조를 만들 때
확정한 **원본 명세 3종**이다. 2026-08-13에 작성했고, 2026-08-25 skeleton-purpose-audit 에서
삭제됐다가 2026-09-17에 이 폴더로 되살려 git 추적 대상으로 두었다. 코드 주석이 이 문서의
절(`development-plan §9.4` 등)을 근거로 인용하므로, 인용 대상이 저장소 안에 있어야 한다.

| 문서 | 내용 | 참조하는 곳 |
|---|---|---|
| [`requirements.md`](requirements.md) | 요구 명세 — 요구 ID의 원본 | CRP orm-raw-repository design-baseline |
| [`development-plan.md`](development-plan.md) | 설계·실행 순서 (Phase·§9 자원 수명 등) | `app/core/resources.py`, `app/core/bootstrap.py`, `app/celery/lifecycle.py` 등 코드 주석과 테스트 docstring |
| [`workflow-guide.md`](workflow-guide.md) | 구현 지침·예시 코드 | CRP orm-raw-repository charter |

- 이 문서들은 **착수 시점의 기준선**이다. 현재 코드의 사용법은 [`../../guides/`](../../guides/) 와
  [`../../project-guide/v1.1/`](../../project-guide/v1.1/) 를 본다.
- 결정의 근거와 이후 변경 이력은 [`../../crp/groups/orm-raw-repository/`](../../crp/groups/orm-raw-repository/) 에 있다.
- 날짜 이름 폴더(`YYYY-MM-DD/`)는 `.gitignore` 가 로컬 작업 기록으로 제외하므로 명세를 그 아래 두지 않는다.
