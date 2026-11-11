"""Install the local-profile UI alongside the maintained pinned viewer overlay."""

from pathlib import Path
import shutil


def apply_profiles(checkout: Path, source: Path):
    """Require exact pinned anchors; never silently edit an unrelated frontend."""
    frontend = checkout / "src/frontend/src"
    target = frontend / "components/laomedoProfiles"
    if target.exists() or not (frontend / "components/laomedoErrors").is_dir():
        raise SystemExit("profile_overlay_requires_fresh_viewer_overlay")
    routes = frontend / "routes.tsx"
    text = routes.read_text(encoding="utf-8")
    for before, after in (
        (
            'import LoginPage from "./pages/LoginPage";',
            'import LoginPage from "./pages/LoginPage";\nimport ProfileEntryGate from "@/components/laomedoProfiles/ProfileEntryGate";',
        ),
        ("<LoginPage />", "<ProfileEntryGate><LoginPage /></ProfileEntryGate>"),
        ("<SignUp />", "<ProfileEntryGate><SignUp /></ProfileEntryGate>"),
    ):
        if text.count(before) != 1:
            raise SystemExit("profile_route_anchor_missing")
        text = text.replace(before, after)
    menu = (
        frontend / "components/core/appHeaderComponent/components/AccountMenu/index.tsx"
    )
    menu_text = menu.read_text(encoding="utf-8")
    for before, after in (
        (
            "export const AccountMenu = () => {",
            'import useProfileSessionActions from "@/components/laomedoProfiles/useProfileSessionActions";\n\nexport const AccountMenu = () => {\n  const profileSession = useProfileSessionActions();',
        ),
        ("    mutationLogout();", '    profileSession.signOut("logout");'),
        ("    <HeaderMenu>", "    <><HeaderMenu>"),
        ("    </HeaderMenu>", "    </HeaderMenu>{profileSession.notice}</>"),
        (
            '<HeaderMenuItemButton onClick={handleLogout} icon="log-out">',
            '{profileSession.enabled && <HeaderMenuItemButton disabled={profileSession.busy} onClick={() => profileSession.signOut("switch")} icon="user">Switch profile</HeaderMenuItemButton>}\n              <HeaderMenuItemButton disabled={!profileSession.ready || profileSession.busy} onClick={handleLogout} icon="log-out">',
        ),
    ):
        if menu_text.count(before) != 1:
            raise SystemExit("profile_menu_anchor_missing")
        menu_text = menu_text.replace(before, after)
    header = (
        frontend / "components/core/appHeaderComponent/components/HeaderMenu/index.tsx"
    )
    header_text = header.read_text(encoding="utf-8")
    old_signature = (
        'export const HeaderMenuItemButton = ({ icon = "", onClick, children }) => ('
    )
    if header_text.count(old_signature) != 1:
        raise SystemExit("profile_header_anchor_missing")
    header_text = header_text.replace(
        old_signature,
        'export const HeaderMenuItemButton = ({ icon = "", onClick, children, disabled = false }) => (',
    )
    header_text = header_text.replace(
        "    onClick={onClick}", "    onClick={onClick}\n    disabled={disabled}", 1
    )
    header.write_text(header_text, encoding="utf-8")
    logout = frontend / "controllers/API/queries/auth/use-post-logout.ts"
    logout_text = logout.read_text(encoding="utf-8")
    if logout_text.count("console.error(error);") != 1:
        raise SystemExit("profile_logout_anchor_missing")
    logout.write_text(
        logout_text.replace(
            "console.error(error);", 'console.error("Sign-out request failed.");'
        ).replace(
            'api.post(`${getURL("LOGOUT")}`)',
            'api.post(`${getURL("LOGOUT")}`, undefined, { timeout: 15000 })',
        ),
        encoding="utf-8",
    )
    auth_context = frontend / "contexts/authContext.tsx"
    auth_text = auth_context.read_text(encoding="utf-8")
    auth_anchor = "      {children}"
    if auth_text.count(auth_anchor) != 1:
        raise SystemExit("profile_auth_context_anchor_missing")
    auth_text = (
        'import ProfileSessionSync from "@/components/laomedoProfiles/ProfileSessionSync";\n'
        + auth_text
    )
    auth_text = auth_text.replace(
        auth_anchor, "      <ProfileSessionSync />\n" + auth_anchor
    )
    auth_context.write_text(auth_text, encoding="utf-8")
    password_gate = (
        frontend / "customization/components/custom-settings-password-form-gate.tsx"
    )
    gate_text = password_gate.read_text(encoding="utf-8")
    if gate_text.count("  return <>{children}</>;") != 1:
        raise SystemExit("profile_password_gate_anchor_missing")
    gate_text = (
        'import ProfileIdentityMutationGate from "@/components/laomedoProfiles/ProfileIdentityMutationGate";\n'
        + gate_text
    )
    gate_text = gate_text.replace(
        "  return <>{children}</>;",
        "  return <ProfileIdentityMutationGate>{children}</ProfileIdentityMutationGate>;",
    )
    password_gate.write_text(gate_text, encoding="utf-8")
    general = frontend / "pages/SettingsPage/pages/GeneralPage/index.tsx"
    general_text = general.read_text(encoding="utf-8")
    for before, after in (
        (
            "          <ProfilePictureFormComponent",
            "          <ProfileIdentityMutationGate><ProfilePictureFormComponent",
        ),
        (
            "            userData={userData}\n          />",
            "            userData={userData}\n          /></ProfileIdentityMutationGate>",
        ),
    ):
        if general_text.count(before) != 1:
            raise SystemExit("profile_picture_gate_anchor_missing")
        general_text = general_text.replace(before, after)
    general_text = (
        'import ProfileIdentityMutationGate from "@/components/laomedoProfiles/ProfileIdentityMutationGate";\n'
        + general_text
    )
    general.write_text(general_text, encoding="utf-8")
    empty_page = frontend / "pages/MainPage/pages/empty-page.tsx"
    empty_text = empty_page.read_text(encoding="utf-8")
    tracking_anchor = "  const handleUserTrack = (key: string) => () => {"
    if empty_text.count(tracking_anchor) != 1:
        raise SystemExit("profile_tracking_anchor_missing")
    empty_text = (
        'import { profileMode } from "@/components/laomedoProfiles/api";\n'
        + empty_text.replace(
            tracking_anchor,
            "  const handleUserTrack = (key: string) => async () => {\n"
            "    // Profile mode refuses user-record mutations, including optional tracking.\n"
            "    if (await profileMode().catch(() => true)) return;",
        )
    )
    empty_page.write_text(empty_text, encoding="utf-8")
    shutil.copytree(source / "profiles", target)
    routes.write_text(text, encoding="utf-8")
    menu.write_text(menu_text, encoding="utf-8")
