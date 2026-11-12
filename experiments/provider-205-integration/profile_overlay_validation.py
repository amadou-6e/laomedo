"""Compare profile-stage outputs against exact public pinned frontend sources."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    root = Path('C:/CodeWorkspace/laomedo')
    upstream = root / '.tools/275/provider-integration-upstream'
    revision = 'fec71dca901949c09ed4d63315804337cd2eb13d'
    paths = [
        'routes.tsx',
        'components/core/appHeaderComponent/components/AccountMenu/index.tsx',
        'components/core/appHeaderComponent/components/HeaderMenu/index.tsx',
        'controllers/API/queries/auth/use-post-logout.ts',
        'contexts/authContext.tsx',
        'customization/components/custom-settings-password-form-gate.tsx',
        'pages/SettingsPage/pages/GeneralPage/index.tsx',
        'pages/MainPage/pages/empty-page.tsx',
    ]
    source = root / 'frontend/langflow-skill-viewer'
    with tempfile.TemporaryDirectory(prefix='laomedo-profile-stage-') as directory:
        temporary = Path(directory)
        old = temporary / 'previous.py'
        old.write_bytes(subprocess.check_output(['git','-C',str(root),'show','97ea2c3c:tools/apply_langflow_local_profiles.py']))
        versions = [load(old,'previous_profile_stage'),load(root/'tools/apply_langflow_local_profiles.py','corrected_profile_stage')]
        results = []
        for index, version in enumerate(versions):
            checkout = temporary / str(index)
            frontend = checkout / 'src/frontend/src'
            (frontend/'components/laomedoErrors').mkdir(parents=True)
            for relative in paths:
                path = frontend/relative
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(subprocess.check_output(['git','-C',str(upstream),'show',revision+':src/frontend/src/'+relative]))
            version.apply_profiles(checkout,source)
            results.append({p.relative_to(frontend).as_posix():p.read_bytes() for p in frontend.rglob('*') if p.is_file()})
        assert results[0] == results[1], 'profile_stage_generated_output_changed'
        print(json.dumps({'upstream':revision,'generated_files':len(results[1]),'byte_identical':True,'scope':'actual pinned source transformation; no browser, model, credentials or service execution'}))


if __name__ == '__main__':
    main()
