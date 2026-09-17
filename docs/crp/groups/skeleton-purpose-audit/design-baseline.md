# Design Baseline — skeleton-purpose-audit (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준**. append-only — 항목은 지우지 않고
> 상태(Active/Superseded)만 바꾼다.

## 0. 질의 수준 (Autonomy Level)

- [x] **적극(Thorough)**
- [ ] 보통(Balanced)
- [ ] 간략(Lean)

선택: **적극** · 선택일: 2026-08-25 · 변경 이력: (없음)

## 1. 목적 / 배경

사용자가 이 저장소의 목적을 한 문장으로 다시 못박았다.

> Django 기반의 수동으로 app 을 등록, url 을 라우터 파일을 이용해 수동 관리를 하는
> **프로젝트 기반 골격 구조**를 만드는 것

그 기준으로 코드를 검수하고, 문서를 **골격 사용자에게 필요한 것만** 남기라는 요청이다.

검수 전 상태: docs 44개 / 575KB. 그중 진입 문서와 심화 가이드가 약 90KB 이고, 나머지
약 485KB 는 **이미 끝난 작업의 착수 명세와 이력**이었다. 골격을 받아 쓰는 사람에게
"무엇을 만들 것인가" 를 지시하는 문서는 길만 늘린다.

## 2. 요구사항 레지스터 (append-only)

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-S01 | 2026-08-25 | 저장소 docs 를 학습 | 44개 문서 전편 열람 후 불일치 4건 보고 | Active | 세션 로그 |
| REQ-S02 | 2026-08-25 | 목적(수동 app 등록 + 라우터 파일 수동 URL 관리 골격) 기준으로 코드 검수 | 목적 부합 여부를 실물로 판정하고 골격으로서의 결함을 찾는다 | Active | run-log Round 1 §A |
| REQ-S03 | 2026-08-25 | 불필요한 문서 삭제 | 완료된 착수 명세 5종 + 폐기된 가이드 버전 삭제 | Active | ADR-S02·S03 |
| REQ-S04 | 2026-08-25 | 필요한 문서 업데이트 | 코드와 어긋난 서술을 실물 기준으로 정정 | Active | ledger S-002~S-006 |
| REQ-S05 | 2026-09-17 | "docs 가이드를 모두 업데이트" → "날짜 폴더의 명세를 적합한 폴더에 두고 추적, 참조 갱신" → "남은 작업 진행" | 코드 주석이 인용하는 착수 명세를 저장소 안에서 따라갈 수 있게 한다 | Active | ADR-S06 |
| REQ-S06 | 2026-09-17 | 문서 재구성·최적화 — 삭제된 문서의 정보까지 포함해 중복을 한 문서로 모으고, 꼭 필요한 문서만 남기며, 이 저장소 관점에서만 서술 | 주제마다 소유 문서를 하나로 정하고(진입·아키텍처·개발 + 명세 기준선), 삭제 문서의 여전히 참인 정보를 코드와 대조해 흡수하며, 문서에서 다른 저장소 언급을 없앤다(CRP 이력 제외) | Active | ADR-S07 |
| REQ-S07 | 2026-09-17 | 삭제된 HTML 안내서 2편을 유지(복원·현행화)하고, 서로 일치해야 하는 모든 정보를 검토·갱신하며, 공통 문서 배치(README 색인 · guides 5편 · specs 3편 · crp 이력)를 적용. 후속 지시: 트랜잭션 규칙을 "응답 DTO 검증 → commit" 하나로 통일, `.env.example` 비밀키 예시값을 배포 안전 검증기와 대조, Python 규칙을 전 저장소 공통(>=3.13 / py313 / mypy 3.13)으로 통일 | HTML 안내서가 현재 코드·Markdown 과 모순 없이 README 「문서 안내」에 들어가고, 여러 곳에 나오는 사실(포트·설정 기본값·명령·route 수·수명주기 예산·CI·프로젝트 이름)이 코드와 일치하며, 문서 검사가 HTML 까지 덮는다. 모든 생성·수정 핸들러에서 응답 DTO 검증이 실패하면 500·커밋 0회·DB 불변이다 | Active | ADR-S08 |
| REQ-S08 | 2026-09-17 | 모든 저장소에 같은 규칙 적용: `ENV` 가 staging/production 이면 서명·세션 비밀키가 placeholder 이거나 access·refresh 키가 같을 때 config import 가 실패해야 한다. `.env.example` 비밀키를 규칙이 거부하는 서로 다른 placeholder 로 바꾸고, 로컬 `.env` 를 새 예시 배치로 재구성 | `ACCESS_TOKEN_SECRET_KEY`·`REFRESH_TOKEN_SECRET_KEY`·`SESSION_SECRET_KEY` 중 placeholder(`strip().lower()` 후 빈 값·`your-` 시작·`change-this` 포함)가 있거나 access = refresh 면 위반을 모두 모아 예외 하나로 거부하고, 메시지에는 설정 이름만 싣는다. development/test 는 검사하지 않는다 | Active | ADR-S09 |

## 3. 설계 결정 기록 (ADR)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-S01 | 2026-08-25 | 생성기가 만든 골격은 이 저장소의 게이트를 **그대로 통과해야 한다**. `operation_id` 를 생성기가 직접 짓는다 | 골격 생성기가 자기 게이트를 통과하지 못하면 "만들자마자 빨간불" 이 첫 경험이 된다. 문서로 우회 안내를 다는 것은 결함을 사용자에게 떠넘기는 것이다 | Active | — |
| ADR-S02 | 2026-08-25 | 완료된 착수 명세(요구명세·개발계획·워크플로 지침·통합 계획·운영 준비 계획)를 **삭제한다** | 전부 "무엇을 만들 것인가" 를 다루는데 이미 만들어졌다. 결정의 근거는 CRP 그룹 문서와 git 이력에 남는다 — 같은 내용을 두 곳에 두면 한쪽이 낡는다 | **Partially superseded (→ ADR-S06)** — 명세 3종만 | — |
| ADR-S03 | 2026-08-25 | `docs/project-guide/v1.0/` 를 **삭제한다** | v1.0 은 존재하지 않는 세션 API 3종을 가르친다(learning-path L-007). 버전 폴더를 보존하는 이유가 "이력" 인데, 그 이력은 git 이 이미 갖고 있다. 틀린 문서를 검색 결과에 남겨 두는 대가가 더 크다 | Active | **learning-path ADR-L01·INV-L3** |
| ADR-S04 | 2026-08-25 | 태그 선언(`tags_metadata.py`)은 생성기가 자동 추가하지 않고 **붙여 넣을 항목을 출력**한다 | `config.INSTALLED_APPS` 와 같은 중앙 파일이다. 사람이 결정하는 것과 컨벤션이 처리하는 것의 경계를 생성기가 넘지 않는다 | Active | — |
| ADR-S05 | 2026-08-25 | 검사에서 면제 목록(`HISTORICAL_DOCS`)을 없앤다 | 면제 대상 파일이 사라졌다. 존재하지 않는 파일을 면제하는 집합은 아무것도 하지 않으면서 검사 범위가 좁아 보이게 만든다 — 이 저장소가 반복해 고쳐 온 "헛도는 검사" 와 같은 부류다 | Active | — |
| ADR-S06 | 2026-09-17 | 요구명세·개발계획·워크플로 지침 3종을 `docs/specs/orm-raw-repository/` 에 **되살린다**(통합 계획·운영 준비 계획은 삭제 유지). `orm-raw-repository` 그룹 문서의 경로를 새 위치로 바꾼다. | `app/core/resources.py`·`bootstrap.py`·`app/celery/lifecycle.py`·테스트 docstring 등 15곳 이상이 `development-plan §9.4` 형태로 근거를 인용한다 — git 이력에만 있으면 인용을 따라갈 수 없다. 사용자 지시(2026-09-17): 명세는 날짜 없는 폴더에 두고 추적한다(세 저장소 공통 구조). "한쪽이 낡는다"(ADR-S02)는 사본이 아니라 원본 하나만 두므로 해당하지 않는다. | Active | ADR-S02 (일부) |
| ADR-S07 | 2026-09-17 | 현행 문서를 `README.md`(진입·빠른 시작·구조·API·**유일한 문서 색인**)·`docs/guides/ARCHITECTURE.md`(동작 레퍼런스·운영·변경 이력)·`docs/guides/DEVELOPMENT.md`(작성 절차·규칙·테스트) 3종으로 통합한다. `docs/guides/QUICKSTART.md`·`docs/project-guide/v1.1/`(10)·`docs/django-style-app-registry/`(3)·HTML 안내서 2종·`docs/specs/orm-raw-repository/README.md` 는 내용을 흡수한 뒤 삭제한다. 명세 3종은 고정 기준선으로 유지하되 다른 저장소 이름만 중립화한다. 문서 검사는 대상 문서를 새 소유 문서로 옮기고, 학습 경로 검사(`project-guide/`·`09-orm-vs-raw-decision.md` 링크)는 `ARCHITECTURE.md`·`DEVELOPMENT.md`·`DEVELOPMENT.md#orm-raw`(+앵커 실재)·사라진 문서 위치 미참조 검사로 대체한다. | 같은 주제가 MD·HTML·버전 가이드·registry 문서에 4중으로 있었고 서로 어긋났다(예: 운영 Admin 차단 존재 여부, 공개 API 수 18/30 vs 22/37, 파일 로그 조건, `exists()` 시그니처). 원본이 하나여야 낡지 않는다(ADR-S02 의 근거와 같다). 삭제한 계획서의 요구 ID 는 코드 주석이 계속 인용하므로 의미 색인을 ARCHITECTURE §2.8 에 남긴다. | **Partially superseded (→ ADR-S08)** — HTML 안내서 2종 삭제분 | ADR-S06 의 폴더 README(색인 단일화), learning-path 의 v1.1 가이드 형태(내용은 흡수) |
| ADR-S08 | 2026-09-17 | HTML 안내서 2종(`docs/guides/server-lifecycle-guide.html`·`feature-development-guide.html`)을 **되살려 유지**한다. 역할은 Markdown 정본의 흐름 요약이며(표·수치는 MD 와 같은 값 또는 링크), 다른 저장소 비교를 쓰지 않는다. README 「문서 안내」는 `문서 / 역할 / 언제 보나` 표로 README → ARCHITECTURE → DEVELOPMENT → HTML 2종 → 명세 3종 → crp 순서를 고정한다. 문서 검사는 **추가만** 한다 — HTML 의 `<code>` 경로·`data-source`(+`data-symbol` 정의)·상대 링크·앵커·꺾쇠 이스케이프·부록 설정 목록, Markdown 링크 앵커, README 색인 순서. `RETIRED_DOC_LOCATIONS` 에서는 되살린 두 파일명만 뺀다. 코드는 설명 텍스트만 고친다(설정 값·응답 불변) — `/api/v1/catalog/products` 는 `active_only=false` 경로가 정렬하지 않는다는 문서(DEVELOPMENT §3.4)가 코드와 일치하므로 정렬을 추가하지 않고 OpenAPI 설명을 고친다. **후속(같은 날)**: 쓰기 핸들러 순서를 `response = X.model_validate(obj)` → `await service.commit()` → `return response` 하나로 통일한다(auth register·blog/reply/sns/user/catalog 생성·수정 11곳). 회귀 테스트 `tests/test_validate_before_commit.py` 를 먼저 추가해 기존 코드에서 11건 실패(커밋 1회)를 확인한 뒤 순서를 바꿔 통과시켰다. OpenAPI 는 바이트 단위로 동일하다. `.env.example` 비밀키는 대조할 검증기가 `config.py` 에 없다 — production 에서 예시값·코드 기본값이 그대로 로드된다(미해결, 검증기 추가는 운영 기동 동작을 바꾸므로 별도 결정). Python 규칙은 `requires-python >=3.13`·ruff `py313`·mypy `3.13`(`.python-version` 3.14 유지)이며 새 대상이 보고한 UP043·UP035(7건)만 ruff 자동 수정했다. | 사용자 지시(2026-09-17): HTML 두 편은 남긴다. 흐름형 HTML 은 Markdown 레퍼런스와 독자·용도가 달라 흡수로 대체되지 않았다. 되살린 사본에는 삭제 전 상태의 불일치(사라진 문서 링크, 다른 저장소 비교, `SKU 안정 정렬` 약속, 미사용 설정을 쓰는 것처럼 읽히는 설명)가 남아 있었고, 검사가 HTML 을 보지 않아 드러나지 않았다 — ADR-S05 가 말한 "헛도는 검사" 와 같은 부류라 검사 범위를 넓힌다. | Active | ADR-S07 (HTML 삭제분) |
| ADR-S09 | 2026-09-17 | `config.py` 끝에 `is_placeholder_secret()` 과 `validate_deployment_safety()` 를 추가하고 `_validate_cross_settings()` 다음에 모듈 수준에서 호출한다. 예외 타입은 기존 운영 가드와 같은 `ValueError`. 기존 가드(무인증 /admin, SQL echo)의 동작·메시지·순서는 바꾸지 않는다 — SQL echo 위반이 있으면 그 오류가 먼저 난다. `.env.example` 세 비밀키는 코드 기본값과 같은 `change-this-…` placeholder 로 통일한다. 테스트 `tests/core/test_deployment_safety.py` 를 먼저 추가해 29건 실패를 확인한 뒤 구현했다(자식 프로세스 `import config` 비정상 종료 포함). | ADR-S08 이 미해결로 남긴 항목이다 — 예시값·코드 기본값이 운영에서 그대로 로드되면 누구나 JWT 를 위조할 수 있다. 세 클래스(App·JWT·Session)에 걸친 조건이라 한 클래스의 validator 로는 볼 수 없어, 교차 검증과 같은 자리(import 시점 모듈 함수)에 둔다. `_validate_cross_settings()` 에 합치지 않은 이유: 그 함수의 첫 위반 즉시 실패 동작을 유지하면서 비밀키 위반만 모아 알리기 위해서다. 규칙 문구는 여러 저장소에 같은 사양으로 적용된다. | Active | — |

## 4. 불가침 제약

- **INV-S1** 목적 3요소를 깨지 않는다 — ① 설치 SSOT 는 `config.INSTALLED_APPS`,
  ② URL 은 라우터 파일 계층이 소유, ③ 디렉터리 자동 스캔 없음
- **INV-S2** 문서가 코드에 없는 공개 심볼·기능을 가르치지 않는다
- **INV-S3** 삭제한 문서를 가리키는 참조를 남기지 않는다 (문서·테스트·CI 주석 포함)
- **INV-S4** `scripts/review_gate.py` 8단계가 통과한다
- **INV-S5** 공개 API 경로·응답 스키마는 이번 그룹에서 바뀌지 않는다

## 5. 변경 이력

| 날짜 | 변경 |
|---|---|
| 2026-08-25 | 최초 작성 — REQ-S01~S04, ADR-S01~S05, INV-S1~S5 |
| 2026-09-17 | REQ-S05 · ADR-S06 — 착수 명세 3종 복원(`docs/specs/orm-raw-repository/`), ADR-S02 일부 supersede |
| 2026-09-17 | REQ-S06 · ADR-S07 — 문서 3종 통합(README·ARCHITECTURE·DEVELOPMENT), 가이드·registry·HTML·명세 README 삭제, 문서 검사 대상 이전 |
| 2026-09-17 | REQ-S07 · ADR-S08 — HTML 안내서 2종 복원·현행화, README 문서 안내 표(문서/역할/언제 보나) 개편, 코드 설명·`pyproject.toml` 이름·`API_DESCRIPTION` 정합화, 문서 검사에 HTML·앵커 추가, ADR-S07 일부 supersede. 후속: 쓰기 핸들러 "DTO 검증 → commit" 통일(테스트 선행), Python >=3.13/py313 통일, `.env.example` 비밀키 검증기 부재 기록 |
| 2026-09-17 | REQ-S08 · ADR-S09 — staging/production 비밀키 placeholder·동일 키 기동 거부(`validate_deployment_safety()`), `.env.example` 비밀키 예시·생성 명령 갱신, README·ARCHITECTURE §3.2/§7/§11.1·server-lifecycle-guide.html 반영 |
