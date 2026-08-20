# 프로젝트 가이드 문서 인덱스 (v1.1)

| 항목 | 값 |
|---|---|
| 문서 버전 | 1.1.0 |
| 작성일 | 2026-08-20 |
| 대상 프로젝트 | fastapi-project-structure-django-passive-style |
| 적용 코드 기준 | Git `b88f654` (ORM/Raw Repository Phase 0~7 반영) |
| 문서 상태 | 현재 구현 기준 |
| 이전 버전 | [v1.0](../v1.0/README.md) — 2026-08-18 기준. 기록으로 남기며 현행 참조가 아니다 |

## 목적

이 문서 세트는 Django의 수동 앱 등록 방식을 차용한 FastAPI 프로젝트 구조를 처음 접하는
개발자가 전체 구조, 조립 순서, 요청 처리, 데이터 접근, 기능별 흐름과 운영 주의사항을
빠르게 파악하도록 돕는다. 코드에 존재하는 현재 동작만 기준으로 한다.

**v1.0 과의 차이**: v1.0 은 Phase 3 시점의 코드를 서술했고 ORM/Raw 두 계층을 "향후 계획"
으로 다뤘다. v1.1 은 Phase 7 까지 구현된 현재 코드를 기준으로 하며, Raw 계층과 두 참조
예제(`app/features/catalog/repositories/product_repository.py`,
`app/features/reports/repositories/sales_report_repository.py`)를 현재 기능으로 서술한다.

## 권장 읽기 순서

1. [프로젝트 개요](01-project-overview.md)
2. [시스템 설계](02-system-design.md)
3. [핵심 구성요소와 기능](03-core-components-and-features.md)
4. [전체 요청 워크플로](04-request-workflow.md)
5. [앱 등록 및 기동 워크플로](05-app-registry-and-startup-workflow.md)
6. [데이터 접근 및 트랜잭션 워크플로](06-data-and-transaction-workflow.md)
7. [기능별 워크플로](07-feature-workflows.md)
8. [운영·보안·품질 워크플로](08-operations-security-quality-workflow.md)
9. [ORM 과 Raw 중 무엇을 쓸 것인가](09-orm-vs-raw-decision.md)

데이터 접근 방식을 고르는 것이 이 구조에서 가장 먼저 마주치는 갈림길이다. 급하면
9번을 먼저 읽어도 된다 — 6번과 7번이 그 결정을 실제 코드로 보여준다.

## 문서 범위

| 문서 | 주요 질문 |
|---|---|
| 프로젝트 개요 | 이 프로젝트는 무엇이며 어떤 기술과 기능을 제공하는가? |
| 시스템 설계 | 모듈 경계와 의존 방향은 어떻게 구성되는가? |
| 핵심 구성요소와 기능 | 핵심 패키지와 공개 기능의 책임은 무엇인가? |
| 전체 요청 워크플로 | HTTP 요청이 응답으로 변환되는 전체 과정은 무엇인가? |
| 앱 등록 및 기동 워크플로 | 기능 앱이 언제, 어떤 순서로 활성화되는가? |
| 데이터 및 트랜잭션 | 읽기·쓰기 라우팅, 커밋, 롤백은 어디서 처리되는가? |
| 기능별 워크플로 | Auth, Blog, Reply, SNS, User, Home, Catalog, Reports는 어떻게 동작하는가? |
| 운영·보안·품질 | 배포 전 확인할 설정, 보안 경계, 테스트 절차는 무엇인가? |
| ORM vs Raw 결정 | 새 기능에서 어느 Repository 계열을 골라야 하는가? |

## 두 Repository 계열 — 어디를 보면 되는가

| 계열 | 기반 클래스 | 참조 예제 |
|---|---|---|
| ORM | `app/core/repositories/repository_base.py` · `app/core/repositories/crud_base.py` | `app/features/catalog/repositories/product_repository.py` |
| Raw SQL | `app/core/repositories/raw_repository_base.py` · `app/core/repositories/raw_crud_base.py` | `app/features/reports/repositories/sales_report_repository.py` |

선택 기준은 9번 문서에 있다. 두 계열은 상속 관계가 없고, 갈라지는 지점은 Repository
구현 하나뿐이다 — 서비스·라우터·스키마의 작성 방식은 같다.

## 관련 기존 문서

- [루트 README](../../../README.md): 설치와 기본 사용법
- [기존 아키텍처 문서](../../ARCHITECTURE.md): 앱 레지스트리 중심 상세 설계
- [빠른 시작](../../QUICKSTART.md): 로컬 실행 절차
- [Django 스타일 앱 레지스트리 문서](../../django-style-app-registry/README.md): 설계 결정과 호환성 자료
- [ORM/Raw Repository 설계 문서](../../orm-raw-repository/2026-08-13/requirements.md):
  `docs/orm-raw-repository/2026-08-13/requirements.md` — 2026-08-13 시점의 **설계 결정
  기록**이다. 구현은 Phase 0~7 로 완료됐으므로, 현재 동작은 이 인덱스의 문서들을 본다.

## 표기 규칙

- `현재`: 기준 커밋에서 코드로 확인된 동작
- `조건부`: 환경 설정에 따라 활성화되는 동작
- 경로는 저장소 루트를 기준으로 표기한다.

## 변경 이력

| 문서 버전 | 작성일 | 변경 내용 |
|---|---|---|
| 1.1.0 | 2026-08-20 | Phase 4~7(ORM/Raw Repository, catalog·reports 예제) 반영. 09 결정 문서 추가. 세션 Dependency 이름을 코드 실물로 정정 |
| 1.0.0 | 2026-08-18 | 현재 코드 기준 프로젝트 가이드 문서 세트 최초 작성 |
