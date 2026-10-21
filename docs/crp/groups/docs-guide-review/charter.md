# Charter — docs-guide-review  (Charter v0.1 / 2026-10-21)

> 검수의 닫힌 정의. 상위 기준은 `design-baseline.md`(REQ-001·C-1~C-3).

## 1. 인벤토리

| 영역 | 경로 | 종류 |
|---|---|---|
| 가이드 | `docs/guides/ARCHITECTURE.md`·`docs/guides/DEVELOPMENT.md`·`docs/guides/index.html` | 문서 |
| 안내서 | `docs/guides/workflows/{server-lifecycle,feature-development,admin-authentication}.html` | 문서 |
| 진입 | `README.md` | 문서 |

- 착수 기준선 커밋: `8553cdc` (main)
- 코드·마이그레이션: 변경 없음

## 2. 계약

- 문서의 값·순서·이름이 코드(`app/core/bootstrap.py`·`app/core/resources.py`·`config.py`·`migrations/versions/`·`.github/workflows/ci.yml`·`compose.test.yaml` 등)와 같다.
- 같은 사실은 모든 문서에서 같은 값이다.

## 3. 합격 기준

- `tests/test_docs_consistency.py`·`tests/test_docs_references.py`·`tests/test_docs_secret_examples.py` 통과
- 링크·앵커 검사 broken 0, HTML 파싱 오류 0, main 대비 EOL 변경 0
- ledger 의 모든 항목이 Fixed 또는 사유가 있는 Wont-fix
