# Charter — docs-guide-site  (Charter v0.1 / 2026-10-22)

> 수정의 닫힌 정의. 상위 기준은 `design-baseline.md`(REQ-001·ADR-001~005).

## 1. 인벤토리

| 영역 | 경로 | 종류 |
|---|---|---|
| 허브 | `docs/guides/index.html`·`docs/guides/assets/style.css` | 문서 |
| 새 HTML 19편 | `docs/guides/{getting-started,architecture,reference,development,operations,features}/`·`docs/guides/workflows/{request-processing,authentication,sequence-diagrams}.html` | 문서 |
| 진입 | `README.md`·`docs/guides/ARCHITECTURE.md`(변경 이력 한 줄) | 문서 |
| docstring | `app/features/{blog,reply,sns,user,home}/services/*.py` | 주석 |
| 테스트 | `tests/test_docs_guide_site.py`(신규)·`tests/test_docs_references.py`(주석·서식) | 테스트 |

- 착수 기준선 커밋: `6f7dc70` (main) · 원본 커밋: `4d346ee`
- 코드 동작·마이그레이션: 변경 없음

## 2. 계약

- 문서의 값·순서·이름이 코드(`app/core/bootstrap.py`·`app/core/resources.py`·`app/core/security/access.py`·`config.py`·`app/features/*/api/routers/v1/*.py`)와 같다.
- 같은 사실은 README·ARCHITECTURE·DEVELOPMENT·HTML 에서 같은 값이다.

## 3. 합격 기준

- `tests/test_doc*.py` 통과(계약 테스트는 수정 전 생성물에서 실패를 먼저 확인)
- 링크 검사 broken 0, HTML 태그 균형 오류 0, 끝 개행, LF
- ledger 의 모든 항목이 Fixed 또는 사유가 있는 Partial/Wont-fix
