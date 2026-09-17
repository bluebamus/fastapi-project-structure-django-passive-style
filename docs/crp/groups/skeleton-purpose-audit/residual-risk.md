# Residual Risk — skeleton-purpose-audit

> 이번 그룹에서 **닫지 않고 넘기는** 위험. 조건이 오면 다시 연다.

| ID | 위험 | 왜 지금 닫지 않나 | 다시 열 조건 |
|---|---|---|---|
| RS-01 | 생성기가 `dependencies/`·`schemas/`·`repositories/` 를 만들지 않는다 (S-009) | 골격은 최소여야 한다. 쓰지 않을 빈 디렉터리를 만드는 것보다 필요할 때 만드는 편이 낫고, 문서도 그 계층을 **선택**으로 표기한다 | 새 앱을 만드는 사람이 그 계층을 매번 손으로 만들며 불편을 보고하면 |
| RS-02 | **CRP 이력 문서가 삭제된 설계 문서를 가리킨다.** `orm-raw-repository/{charter,design-baseline,completion-report}.md` 와 `learning-path/{charter,audit-report,ledger,design-baseline}.md` 가 `docs/orm-raw-repository/2026-08-13/*` 와 `project-guide/v1.0/` 를 참조한다 | CRP 문서는 **그 시점의 기록**이라 append-only 다. 당시 실재했던 파일을 참조하는 것이 정상이고, 지금 고치면 이력을 소급 수정하는 것이 된다. 문서 참조 검사는 진입 문서와 현행 가이드만 훑으므로(RL-04) 게이트도 깨지지 않는다 | CRP 이력을 "현행 참조" 로 쓰기 시작하면 |
| RS-03 | `blog`·`reply`·`sns`·`user` 네 앱이 거의 동일한 CRUD 를 반복한다 | 골격의 참조 구현으로서 "같은 구조가 반복된다" 는 것 자체가 보여주는 값이 있다. 줄이면 migration·테스트·골든 스냅샷이 함께 움직이는 큰 변경이고, 사용자 요구는 문서 정리였다 | 예제 앱 수를 줄이자는 결정이 내려지면 — 그때는 어느 것을 남길지가 먼저다 |
| RS-04 | 삭제한 문서의 내용을 다시 필요로 할 수 있다 (요구사항 ID 체계 `FR/CR/NFR/BC/SEC/AC`) | git 이 갖고 있다(`git log --diff-filter=D -- docs/`). 같은 내용을 두 곳에 두면 한쪽이 낡고, 낡은 쪽을 누가 읽을지 통제할 수 없다 | ID 체계로 추적해야 하는 새 작업이 생기면 — 그때는 되살리는 것이 아니라 그 작업의 CRP 그룹에서 새로 정의한다 |
| RS-05 | `ADR-S03` 이 `learning-path` 의 `ADR-L01`·`INV-L3`(v1.0 보존)을 뒤집었다 | 뒤집은 이유를 ADR 로 남겼다 — v1.0 은 존재하지 않는 세션 API 를 가르쳤고, 보존 이유였던 "이력" 은 git 이 이미 갖고 있다. 다만 **다른 그룹의 불변식을 이 그룹이 무효화한 것**은 사실이다 | 버전 폴더를 다시 늘리게 되면(v1.2 신설 등) 보존 정책을 처음부터 정한다 |

> **2026-09-17 갱신 (ADR-S06).** RS-02 의 `docs/orm-raw-repository/2026-08-13/*` 부분과 RS-04 는
> 명세 3종을 `docs/specs/orm-raw-repository/` 에 되살려 **해소**했다. `orm-raw-repository` 그룹 문서는
> 새 경로를 가리킨다. `learning-path` 문서의 옛 경로와 `project-guide/v1.0/` 참조는 당시 기록으로 남긴다.
