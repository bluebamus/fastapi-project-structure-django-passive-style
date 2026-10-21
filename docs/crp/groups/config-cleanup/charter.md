# Charter — config-cleanup  (Charter v0.1 / 2026-10-19)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항(REQ-001)·불가침 제약(C-1~C-3)과 모순될 수 없다.

## 1. 인벤토리 (Scope Inventory)

| 영역 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 설정 | `config.py` | 소스 | `SMTPSettings`·`UploadSettings`·`get_smtp_settings`·`get_upload_settings`·`smtp_settings`·`upload_settings`·`SESSION_EXPIRE_SECONDS` 삭제, `validate_deployment_safety` 의 `SMTP_PASSWORD` 항목 삭제, `SessionSettings` docstring |
| 예시 | `.env.example` | 설정 | SMTP 절·업로드 절·`SESSION_EXPIRE_SECONDS` 줄 삭제 |
| 테스트 | `tests/core/test_settings_contract.py`(3절 추가), `tests/core/test_deployment_safety.py`, `tests/core/test_security_hardening.py` | 테스트 | 계약 테스트 · SMTP 항목 정리 |
| 문서 | `README.md`, `docs/guides/ARCHITECTURE.md`, `docs/guides/workflows/admin-authentication.html`, `docs/guides/workflows/server-lifecycle.html`, `docs/crp/groups/config-cleanup/` | 문서 | 만료 정본 표·업그레이드 노트·지운 설정 제거 |

- 착수 기준선 커밋: `6aae442` (main)
- 마이그레이션: 변경 없음 · 의존성: 변경 없음(`python-multipart` 유지, ADR-004)
- 과거 CRP 그룹 문서는 범위 밖(append-only 이력)

## 2. 계약 (Contract)

### 2-1. 불변식
- INV-1: 모든 설정 필드는 운영 코드(테스트 제외)에서 읽힌다 — 예외는 `UNREAD_ALLOWED` 의 사유 붙은 5건뿐 (`test_every_setting_field_is_read_by_source_code`)
- INV-2: `SMTP_*`·`UPLOAD_*`·`SESSION_EXPIRE_SECONDS` 가 환경에 남아도 모든 설정 클래스 생성이 성공하고 속성이 없다 (`test_removed_keys_left_in_environment_are_ignored`)
- INV-3: `.env.example` ↔ 설정 필드 양방향 일치(기존 계약 유지)
- INV-4: 세션·토큰 만료의 기본값·뜻은 README "세션·토큰 만료" 표 한 곳에 있다

### 2-2. 비목표
- `ApiSettings`·미사용 로그 설정의 삭제(ADR-003 — 별도 결정)
- 지운 키를 기동 거부로 감지하는 것(ADR-001)

## 3. 인수 기준 (GATE 3)
- [x] `.env` 없는 저장소 밖 사본에서 `pytest -m "not mysql and not browser"` 통과, skip·xfail·xpass 0
- [x] `mysql`·`browser` 마커는 로컬 `--collect-only` 만
- [x] `ruff check`·`ruff format --check`·mypy(1.20.2 순수 Python 빌드) 클린
- [x] 새 테스트의 fail-on-revert 결과가 run-log 에 있다
- [x] `review_gate --fast` 결과가 run-log 에 있다(네트워크 단계 결과 포함)

## 4. 변경 이력
- v0.1 (2026-10-19): 최초 작성.
- v0.2 (2026-10-19, Round 2 · REQ-002): 범위에 `ApiSettings`·`API_VERSION` 삭제와 로그 설정 연결을 더한다 — §2-2 의 첫 비목표는 이 개정으로 범위 안이 됐다.
  인벤토리 추가: `app/utils/logs/config.py`·`setup.py`·`formatters.py`, `app/celery/app.py`, `tests/utils/test_log_settings.py`·`conftest.py`·`test_log_redaction.py`,
  `docs/guides/DEVELOPMENT.md`·`feature-development-guide.html`. INV-1 은 예외 없이(`UNREAD_ALLOWED` 삭제, ADR-006), INV-2 에 `API_VERSION` 추가.
  INV-5: 로그 설정 기본값이면 출력 줄은 변경 전과 같다(`test_default_output_line_is_unchanged`). INV-6: 비밀값 가리기는 사용자 포맷에서도 유지
  (`test_app_handlers_redact_traceback_message_and_stack[user-format]`). 착수 기준선 `80d56a9`. 마이그레이션·의존성 변경 없음.
