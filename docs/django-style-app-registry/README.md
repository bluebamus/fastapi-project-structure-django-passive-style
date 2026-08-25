# Django식 수동 앱 Registry 문서 세트

## 목적

이 폴더는 이 저장소의 정체성인 **Django식 수동 앱 등록**이 무엇이고, Django 와 어디까지
같고 어디부터 다른지를 설명한다.

## 문서 목록

| 문서 | 역할 |
|---|---|
| [`PASSIVE-APP-PROJECT-DESIGN.md`](PASSIVE-APP-PROJECT-DESIGN.md) | 이 저장소가 왜 존재하고 어떤 설계 원칙을 따르는가 |
| [`DJANGO-APP-COMPATIBILITY.md`](DJANGO-APP-COMPATIBILITY.md) | Django 와 **동일·확장·비지원** 범위 구분, `ready()` 제약, 앱 제거 시 주의 |

동작을 "어떻게 쓰는가"는 [`docs/project-guide/v1.1/`](../project-guide/v1.1/README.md),
구조의 정본은 [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) 다.

## 문서가 충돌하면

1. 현재 코드와 통과하는 테스트
2. [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) (아키텍처 SSOT)
3. 이 폴더의 두 문서

코드가 문서보다 앞서 변경됐다면 코드를 되돌리지 말고, 변경 이유와 테스트를 확인한 뒤
문서를 갱신한다.

## 삭제된 착수 문서

구축을 지시하던 계획 문서 두 편(`DJANGO-STYLE-MANUAL-APP-INTEGRATION-PLAN.md`,
`PRODUCTION-READINESS-DEVELOPMENT-PLAN.md`)은 구축이 끝난 뒤 삭제했다. "무엇을 만들
것인가"를 다루는 문서라, 이미 만들어진 지금은 골격을 쓰는 사람에게 길만 늘린다.
그 문서들이 정의하던 `FR/CR/NFR/BC/SEC/AC` 요구사항 ID 도 함께 사라졌다 — 결정의 근거가
필요하면 git 이력(`git log -- docs/django-style-app-registry/`)에서 읽는다.

지금 살아 있는 계약은 문서가 아니라 **테스트**다. 무엇이 보장되는지 알고 싶으면
`tests/core/apps/` 와 `tests/test_docs_consistency.py` 를 본다.
