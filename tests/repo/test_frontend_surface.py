from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "apps" / "web"
DASHBOARD = WEB / "src" / "app" / "(main)" / "dashboard"

ALLOWED_DASHBOARD_DIRS = {"_components", "[...not-found]", "roles", "users"}


def test_dashboard_has_no_unrelated_showcase_routes() -> None:
    actual = {path.name for path in DASHBOARD.iterdir() if path.is_dir()}
    assert actual <= ALLOWED_DASHBOARD_DIRS, sorted(actual - ALLOWED_DASHBOARD_DIRS)


def test_top_level_demo_mail_and_chat_are_removed() -> None:
    main = WEB / "src" / "app" / "(main)"
    assert not (main / "chat").exists()
    assert not (main / "mail").exists()


def test_hosted_demo_telemetry_and_support_ctas_are_removed() -> None:
    layout = (WEB / "src" / "app" / "layout.tsx").read_text(encoding="utf-8")
    dashboard_layout = (
        WEB / "src" / "app" / "(main)" / "dashboard" / "layout.tsx"
    ).read_text(encoding="utf-8")
    sidebar = (
        WEB
        / "src"
        / "app"
        / "(main)"
        / "dashboard"
        / "_components"
        / "sidebar"
        / "app-sidebar.tsx"
    ).read_text(encoding="utf-8")
    nav = (
        WEB
        / "src"
        / "app"
        / "(main)"
        / "dashboard"
        / "_components"
        / "sidebar"
        / "nav-main.tsx"
    ).read_text(encoding="utf-8")
    assert "@vercel/analytics" not in layout
    assert "<Analytics" not in layout
    assert "SupportCard" not in sidebar
    assert "Quick Create" not in nav
    assert ">Inbox<" not in nav
    assert "GitHubRepositoriesMenu" not in dashboard_layout


def test_social_demo_auth_is_removed() -> None:
    social = WEB / "src" / "app" / "(main)" / "auth" / "_components" / "social-auth"
    assert not social.exists()
    for version in ("v1", "v2"):
        for page_name in ("login", "register"):
            page = (
                WEB
                / "src"
                / "app"
                / "(main)"
                / "auth"
                / version
                / page_name
                / "page.tsx"
            )
            text = page.read_text(encoding="utf-8")
            assert "GoogleButton" not in text
            assert "Continue with Google" not in text
