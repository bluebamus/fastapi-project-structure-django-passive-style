# Run Log — config-cleanup (라운드 로그 + 수렴 판정)

## 라운드 기록

### Round 0 — 2026-10-19 (base SHA: `6aae442`) · 참조 조사
- **트리거:** 사용자 요청 REQ-001
- **조사:** `git grep -i -E "smtp|session_expire|upload"`(uv.lock 제외) — 참조는 `config.py`·`.env.example`·`README.md`(0단계 표·자주 막히는 지점)·
  `docs/guides/ARCHITECTURE.md`(§3.2 표 2곳·검증 표 2곳·§11.3)·`admin-auth-guide.html`(만료 표)·`server-lifecycle-guide.html`(클래스 표·검증 문단 2곳·부록)·
  `tests/core/test_deployment_safety.py`·`tests/core/test_security_hardening.py`·과거 CRP 그룹 문서(이력, 고치지 않음). app·scripts·migrations·CI·compose 에는 없었다.
- **소비처 확인:** AST 로 운영 코드의 속성 접근을 모으면 세 묶음 필드는 `SMTPSettings` 자체 validator(`self.SMTP_TLS`·`self.SMTP_SSL`)와
  배포 안전 검사(`smtp_settings.SMTP_PASSWORD`) 말고는 읽히지 않았다. 그 밖의 미사용 필드는 `API_VERSION`·`LOG_CONSOLE_ENABLED`·`LOG_CONSOLE_FORMAT`·`LOG_FILE_FORMAT`·`LOG_DATE_FORMAT`.
- **python-multipart:** `OAuth2PasswordRequestForm`(API 로그인)·`admin_auth.py` 의 `request.form()`(관리 로그인·CSRF)·sqladmin 폼이 쓴다 → 유지(ADR-004).
- **신규 finding:** LOW 3 → ledger F-001~F-003
- **수렴 판정:** `NOT CONVERGED` (Open Fix 2)

### Round 1 — 2026-10-19 · 삭제 · 만료 정본 · 계약 테스트
- **변경:** `config.py`(클래스 2개·팩토리 2개·전역 인스턴스 2개·`SESSION_EXPIRE_SECONDS` 삭제, 배포 안전 검사의 SMTP 항목 삭제, docstring), `.env.example`,
  `tests/core/test_deployment_safety.py`(비밀번호 키 2종으로, `test_empty_optional_passwords_are_allowed` → `test_empty_redis_password_is_allowed`),
  `tests/core/test_security_hardening.py`, `tests/core/test_settings_contract.py`(3절), README(만료 표·업그레이드 노트·0단계 표·자주 막히는 지점),
  ARCHITECTURE(§3.2·§7·§11.1 #13·§11.3·§12), admin-auth-guide(만료 표·운영 표), server-lifecycle-guide(클래스 표·검증 문단·부록).
- **새 테스트와 fail-on-revert** (`config.py` 를 저장소 밖 임시 경로에 복사해 두고 바꿔 실행 → 복사본으로 복원, `cmp` 로 확인):

  | 테스트 | main 의 `config.py` | `SESSION_EXPIRE_SECONDS` 한 필드만 되살림 |
  |---|---|---|
  | `test_every_setting_field_is_read_by_source_code` | 실패 | 실패 |
  | `test_removed_keys_left_in_environment_are_ignored[SessionSettings]` | 실패 | 실패 |
  | `test_removed_keys_left_in_environment_are_ignored[SMTPSettings]`·`[UploadSettings]` | 실패(클래스가 있어 수집됨) | — |
  | (기존) `test_every_config_field_is_documented_in_env_example` | 실패 | 실패 |

- **정리(ponytail):** 계약 테스트의 검사 파일 목록을 기존 `_python_sources()` 재사용으로 줄이고, 전역 인스턴스 부재만 보던 중복 테스트를 지웠다
  (같은 되돌림을 읽힘 계약이 이미 잡는다). 정리 뒤 fail-on-revert 를 다시 돌려 위 표와 같은 결과를 확인했다.
- **검사:** `.env` 없는 저장소 밖 클론에서 `pytest -m "not mysql and not browser"` 1230 passed · 36 deselected · skip/xfail/xpass 0.
  `-m "mysql or browser" --collect-only` 36 수집(실행 안 함). `ruff check`·`ruff format --check`(383 파일) 클린. mypy 1.20.2(순수 Python 빌드) 222 파일 문제 없음.
  `ENV=test uv run python -m scripts.review_gate --fast`(클론) 7단계 전체 통과(pip-audit 포함). 마이그레이션 변경 없음.
- **신규 finding:** 0
- **수렴 판정:** `CONVERGED` (Open Fix 0, F-003 은 R-001 로 수용)
