"""Profile installer controls on local files; no app, network or model execution."""

import importlib.util
from pathlib import Path
import tempfile
import unittest

from support.paths import repository_root

spec = importlib.util.spec_from_file_location(
    "profile_overlay", repository_root() / "tools/apply_langflow_local_profiles.py"
)
overlay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(overlay)


class ProfileOverlayTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.frontend = self.root / "checkout/src/frontend/src"
        (self.frontend / "components/laomedoErrors").mkdir(parents=True)
        self.source = self.root / "overlay"
        (self.source / "profiles").mkdir(parents=True)
        (self.source / "profiles/Profile.tsx").write_bytes(b"profile asset\n")
        self.inputs = {
            "routes.tsx": 'import LoginPage from "./pages/LoginPage";\n<LoginPage />\n<SignUp />\n',
            "components/core/appHeaderComponent/components/AccountMenu/index.tsx": 'export const AccountMenu = () => {\n    mutationLogout();\n    <HeaderMenu>\n    </HeaderMenu>\n<HeaderMenuItemButton onClick={handleLogout} icon="log-out">\n',
            "components/core/appHeaderComponent/components/HeaderMenu/index.tsx": 'export const HeaderMenuItemButton = ({ icon = "", onClick, children }) => (\n    onClick={onClick}\n',
            "controllers/API/queries/auth/use-post-logout.ts": 'console.error(error);\napi.post(`${getURL("LOGOUT")}`)\n',
            "contexts/authContext.tsx": "      {children}\n",
            "customization/components/custom-settings-password-form-gate.tsx": "  return <>{children}</>;\n",
            "pages/SettingsPage/pages/GeneralPage/index.tsx": "          <ProfilePictureFormComponent\n            userData={userData}\n          />\n",
            "pages/MainPage/pages/empty-page.tsx": "  const handleUserTrack = (key: string) => () => {\n",
        }
        for relative, text in self.inputs.items():
            path = self.frontend / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

    def test_missing_late_anchor_preserves_every_file_and_adds_no_profile_assets(self):
        for relative, code in (
            ("contexts/authContext.tsx", "profile_auth_context_anchor_missing"),
            (
                "customization/components/custom-settings-password-form-gate.tsx",
                "profile_password_gate_anchor_missing",
            ),
            (
                "pages/SettingsPage/pages/GeneralPage/index.tsx",
                "profile_picture_gate_anchor_missing",
            ),
            ("pages/MainPage/pages/empty-page.tsx", "profile_tracking_anchor_missing"),
        ):
            with self.subTest(anchor=relative):
                path = self.frontend / relative
                original = path.read_bytes()
                path.write_bytes(b"unsupported upstream layout\n")
                before = {
                    p: p.read_bytes() for p in self.frontend.rglob("*") if p.is_file()
                }
                with self.assertRaisesRegex(SystemExit, "^" + code + "$"):
                    overlay.apply_profiles(self.root / "checkout", self.source)
                self.assertEqual(
                    {
                        p: p.read_bytes()
                        for p in self.frontend.rglob("*")
                        if p.is_file()
                    },
                    before,
                )
                self.assertFalse(
                    (self.frontend / "components/laomedoProfiles").exists()
                )
                path.write_bytes(original)

    def test_valid_overlay_writes_routes_and_exact_profile_assets(self):
        overlay.apply_profiles(self.root / "checkout", self.source)
        self.assertIn(
            "<ProfileEntryGate><LoginPage />",
            (self.frontend / "routes.tsx").read_text(),
        )
        self.assertIn(
            "<ProfileSessionSync />",
            (self.frontend / "contexts/authContext.tsx").read_text(),
        )
        self.assertEqual(
            (self.frontend / "components/laomedoProfiles/Profile.tsx").read_bytes(),
            b"profile asset\n",
        )
