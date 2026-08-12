# Django식 수동 앱 Registry 문서 세트

## 목적

이 폴더는 `fastapi-default-project-structure`를 기반으로 Django식 수동 앱 등록과 application registry lifecycle을 FastAPI에 도입하기 위해 작성된 분석, 설계, 요구 명세 및 개발 계획을 하나의 추적 단위로 관리한다.

구현과 검토는 아래 권장 순서로 문서를 읽는다.

## 문서 목록

| 순서 | 문서 | 역할 | 상태 |
|---|---|---|---|
| 1 | [`PASSIVE-APP-PROJECT-DESIGN.md`](PASSIVE-APP-PROJECT-DESIGN.md) | 현재 passive-style 프로젝트의 목적, 구조, 설계 원칙과 개발 이력 | 현재 구조 이해용 기준 문서 |
| 2 | [`PRODUCTION-READINESS-DEVELOPMENT-PLAN.md`](PRODUCTION-READINESS-DEVELOPMENT-PLAN.md) | 기존 구조 검증에서 발견한 운영 준비 문제와 개선 계획 | 역사적 검토 자료. 일부 항목은 이후 `main`에서 구현됨 |
| 3 | [`DJANGO-STYLE-MANUAL-APP-INTEGRATION-PLAN.md`](DJANGO-STYLE-MANUAL-APP-INTEGRATION-PLAN.md) | default 기준선 재구축, Django 대응 요구사항, 상세 설계, 개발·브랜치·통합 계획 | 향후 구현의 실행 명세이자 최우선 문서 |

## 문서 간 관계

```text
PASSIVE-APP-PROJECT-DESIGN
  현재 목적과 구조를 설명
            │
            ├── PRODUCTION-READINESS-DEVELOPMENT-PLAN
            │     과거 문제와 개선 과정의 근거
            │
            └── DJANGO-STYLE-MANUAL-APP-INTEGRATION-PLAN
                  default 최신 기준선 위에 재구축할 목표 상태와 실행 명세
```

문서가 충돌하면 다음 우선순위를 적용한다.

1. 사용자가 확정한 최신 요구사항
2. `DJANGO-STYLE-MANUAL-APP-INTEGRATION-PLAN.md`의 `FR/CR/NFR/BC/SEC/AC` 명세
3. 현재 코드와 자동화된 테스트
4. 목적·설계 문서
5. 역사적 운영 준비 계획

코드가 현재 명세보다 앞서 변경된 경우에는 코드를 무조건 되돌리지 않고, 변경 이유와 테스트를 확인한 뒤 명세 또는 구현을 함께 갱신한다.

## 요구사항 ID 체계

| 접두사 | 의미 | 정의 위치 |
|---|---|---|
| `FR-*` | 기능 요구사항 | 통합 계획 §5.2 |
| `CR-*` | Django 대응·호환 요구사항 | 통합 계획 §5.3 |
| `NFR-*` | 결정성·안정성·오류 가시성 등 비기능 요구사항 | 통합 계획 §5.4 |
| `BC-*` | `fastapi-default-project-structure` 기능 보존 요구사항 | 통합 계획 §5.5 |
| `SEC-*` | Admin 지연 로딩, 경로 이탈 방지 등 보안 요구사항 | 통합 계획 §5.6 |
| `AC-*` | 자동 검증 가능한 인수 조건 | 통합 계획 §5.7 |

개발 commit, PR, 테스트 이름과 검증 보고서에는 관련 ID를 기록한다. 구현 완료는 요구사항이 하나 이상의 `AC-*`에 연결되고 해당 검증 증거가 남아 있을 때만 인정한다.

## 변경 관리 규칙

1. 요구사항을 추가하거나 변경할 때 통합 계획의 정의와 §5.8 추적성 표를 함께 수정한다.
2. 개발 단계가 바뀌면 대상 Phase, 파일, 검증 수단 및 완료 조건을 함께 수정한다.
3. 구현 중 새로운 위험이 발견되면 통합 계획의 위험 표와 관련 `SEC-*` 또는 `NFR-*`를 갱신한다.
4. 과거 판단을 보존할 필요가 있으면 기존 문서를 삭제하거나 덮어쓰기보다 상태를 명시하고 후속 문서를 연결한다.
5. 문서 이동이나 이름 변경 시 이 인덱스, 저장소 `README.md`, `docs/ARCHITECTURE.md` 및 내부 상대 링크를 함께 검증한다.

## 저장소 기준점

- default 구현 기준선: `fastapi-default-project-structure` `a980b71`
- passive-style 참조점: `fastapi-project-structure-django-passive-style` `85153fb`
- 실제 구현 착수 전에는 두 저장소의 원격 최신 상태와 working tree를 다시 확인하고 기준점이 바뀌면 통합 계획을 갱신한다.
