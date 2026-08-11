"""Tests for scripts/new_app.py scaffolding generator (convention-based, gen-2)."""


def test_generator_creates_bootable_app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app" / "features").mkdir(parents=True)
    # run generator pointed at temp root
    from scripts.new_app import scaffold

    scaffold("widget", root=tmp_path, category="domain")

    assert (tmp_path / "app/features/widget/api/routers/router.py").exists()


def test_generator_no_config_py(tmp_path, monkeypatch):
    """컨벤션 기반이므로 config.py 는 생성하지 않는다(디렉터리=앱 선언)."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app" / "features").mkdir(parents=True)
    from scripts.new_app import scaffold

    scaffold("widget", root=tmp_path, category="domain")

    assert not (tmp_path / "app/features/widget/config.py").exists()


def test_generator_router_is_parameterized(tmp_path, monkeypatch):
    """Generated router.py must contain the correct router variable name."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app" / "features").mkdir(parents=True)
    from scripts.new_app import scaffold

    scaffold("widget", root=tmp_path, category="domain")

    router_text = (tmp_path / "app/features/widget/api/routers/router.py").read_text(
        encoding="utf-8"
    )
    assert "widget_router = APIRouter()" in router_text


def test_generator_creates_all_required_dirs(tmp_path, monkeypatch):
    """All required subdirectories and __init__.py files are created."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app" / "features").mkdir(parents=True)
    from scripts.new_app import scaffold

    scaffold("widget", root=tmp_path)

    base = tmp_path / "app" / "features" / "widget"
    assert (base / "__init__.py").exists()
    assert (base / "models" / "__init__.py").exists()
    assert (base / "schemas" / "__init__.py").exists()
    assert (base / "services" / "__init__.py").exists()
    assert (base / "repositories" / "__init__.py").exists()
    assert (base / "tests" / "__init__.py").exists()
    assert (base / "api" / "routers" / "v1" / "__init__.py").exists()
    assert (base / "dependencies" / "__init__.py").exists()
    assert (base / "dependencies" / "widget_dependencies.py").exists()


def test_generator_optional_admin(tmp_path, monkeypatch):
    """--with-admin flag creates admin.py with an admin_views list."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app" / "features").mkdir(parents=True)
    from scripts.new_app import scaffold

    scaffold("widget", root=tmp_path, with_admin=True)

    admin_path = tmp_path / "app/features/widget/admin.py"
    assert admin_path.exists()
    assert "admin_views" in admin_path.read_text(encoding="utf-8")


def test_generator_no_worker_dir(tmp_path, monkeypatch):
    """worker/ 는 더 이상 생성하지 않는다(app/celery 가 대체)."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app" / "features").mkdir(parents=True)
    from scripts.new_app import scaffold

    scaffold("widget", root=tmp_path)

    assert not (tmp_path / "app/features/widget/worker").exists()


def test_generator_multiword_pascal_case(tmp_path, monkeypatch):
    """Multi-word snake_case names are converted to proper PascalCase class names."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app" / "features").mkdir(parents=True)
    from scripts.new_app import scaffold

    scaffold("user_profile", root=tmp_path, category="domain", with_admin=True)

    admin_text = (tmp_path / "app/features/user_profile/admin.py").read_text(encoding="utf-8")
    assert "UserProfileModel" in admin_text
    assert "UserProfileAdmin" in admin_text
    router_text = (tmp_path / "app/features/user_profile/api/routers/router.py").read_text(
        encoding="utf-8"
    )
    assert "user_profile_router = APIRouter()" in router_text


# ---------------------------------------------------------------------------
# 이 저장소는 수동 등록(passive)이다 — INSTALLED_APPS 에 이름을 넣지 않으면
# 생성된 앱은 결선되지 않는다. 생성기가 "자동 발견 / 중앙 파일 수정 불필요" 라고
# 말하면 사용자는 정상 생성된 줄 알고 존재하지 않는 엔드포인트를 디버깅하게 된다.
# 자매 저장소(active-style)와의 핵심 차이도 흐려진다 (계획서 P1-3).
# ---------------------------------------------------------------------------

_FALSE_CLAIMS = ["자동 발견", "자동발견", "중앙 파일 수정 불필요"]


def test_next_steps_tells_user_to_register_in_installed_apps():
    from scripts.new_app import next_steps

    text = next_steps("widget", with_admin=False)

    assert "INSTALLED_APPS" in text
    assert '"widget",' in text, "복사해 붙일 수 있는 등록 예제가 있어야 한다"


def test_next_steps_makes_no_auto_discovery_claim():
    from scripts.new_app import next_steps

    text = next_steps("widget", with_admin=True)

    for claim in _FALSE_CLAIMS:
        assert claim not in text, f"수동 등록 저장소에서 '{claim}' 은 사실이 아니다"


def test_generated_admin_template_makes_no_auto_discovery_claim(tmp_path, monkeypatch):
    """생성된 파일 안에 남은 문구도 같은 오해를 만든다."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app" / "features").mkdir(parents=True)
    from scripts.new_app import scaffold

    scaffold("widget", root=tmp_path, with_admin=True)

    admin_text = (tmp_path / "app/features/widget/admin.py").read_text(encoding="utf-8")
    for claim in _FALSE_CLAIMS:
        assert claim not in admin_text, f"생성된 admin.py 에 '{claim}' 이 남아 있다"


def test_module_docstring_makes_no_auto_discovery_claim():
    import scripts.new_app as mod

    for claim in _FALSE_CLAIMS:
        assert claim not in (mod.__doc__ or ""), f"모듈 독스트링에 '{claim}' 이 남아 있다"
