# Design Baseline — docs-guide-review (기준 설계 문서)

> 이 그룹의 요구사항·결정의 단일 기준. append-only — 항목은 지우지 않고 상태만 바꾼다.
> 이 그룹의 ID(REQ·ADR·C·F·R)는 그룹 안에서만 유효하다.

## 0. 질의 수준 (Autonomy Level)

- [ ] 적극(Thorough)
- [ ] 보통(Balanced)
- [x] **간략(Lean)** — 지적 목록과 수정 명세가 이미 정해져 있다. 코드가 정답이므로 갈림길이 없다.

선택: **간략** · 선택일: 2026-10-21 · 변경 이력: (없음)

## 1. 목적 / 배경

main `8553cdc` 기준 가이드 문서 6개(`docs/guides/index.html`·ARCHITECTURE·DEVELOPMENT·`workflows/*.html` 3개)를 코드와 대조한
검수에서 26건(WRONG 8 · OUTDATED 5 · MISSING 5 · INCONSISTENT 5 · UNCLEAR 3)과 누락 8항목이 나왔다. 전부 고치고 README 의 같은 사실도 맞춘다.

## 2. 요구사항 레지스터 (append-only)

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-10-21 | "88건 모두 수정하고 README 도 같이 고쳐줘" | ① 지적 F01~F26 과 누락 표를 전부 고친다 ② README 에서 같은 사실이 틀린 곳을 고친다(새 종류의 검수는 하지 않고 보고만) ③ 코드·테스트 동작은 바꾸지 않는다 | Active | ledger F-01~F-26 |

## 3. 설계 결정 (ADR)

| ADR | 결정 | 이유 |
|---|---|---|
| ADR-001 | 코드가 정답 — 문서만 고친다. 지적이 코드와 맞지 않으면 고치지 않고 보고한다 | 문서 정합성 검수의 전제 |
| ADR-002 | 기준일 표기는 커밋 해시(main `8553cdc`)로 쓴다 | "현재 작업 트리"는 언제 읽어도 참이라 기준이 되지 못한다 |
| ADR-003 | `docs/guides/index.html` 은 색인이 아니라 브라우저용 진입 링크 목록으로 정의한다 — 색인은 README 「문서 안내」 하나 | 두 색인이 생기면 어긋난다(F24) |

## 4. 불가침 제약

- C-1 코드·테스트 동작 변경 금지
- C-2 다른 저장소 언급·비교 금지
- C-3 HTML 은 html.parser 오류 0, EOL(LF) 보존
