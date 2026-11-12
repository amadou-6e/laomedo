import os
import sys
import tempfile
from pathlib import Path

repo = Path('C:/CodeWorkspace/laomedo')
root = Path(tempfile.mkdtemp(prefix='laomedo-layout-preview-'))
(root / 'langflow').mkdir()
(root / 'registry').mkdir()
values = {
    'LANGFLOW_CONFIG_DIR': str(root / 'langflow'),
    'LFX_CONFIG_DIR': str(root / 'langflow'),
    'LANGFLOW_DATABASE_URL': 'sqlite:///' + (root / 'langflow/flow.db').as_posix(),
    'LANGFLOW_FRONTEND_PATH': str(repo / '.tools/275/provider-integration-upstream/src/frontend/build'),
    'LANGFLOW_COMPONENTS_PATH': str(repo / 'components'),
    'LAOMEDO_COMPONENT_DIR': str(repo / 'components/laomedo'),
    'LANGFLOW_AUTO_LOGIN': 'true',
    'LANGFLOW_DO_NOT_TRACK': 'true',
    'LAOMEDO_SKILL_STORE': str(root / 'registry'),
    'LAOMEDO_AGENT_ACTIVITY_DB': str(root / 'activity.db'),
}
os.environ.update(values)
os.chdir(root)
sys.path.insert(0, str(repo / 'src'))
import laomedo
import uvicorn
laomedo.__path__.append(values['LAOMEDO_COMPONENT_DIR'])
print('PRIVATE_PREVIEW_ROOT=' + str(root), flush=True)
uvicorn.run('laomedo.integrations.langflow.viewer:create_app', factory=True, host='127.0.0.1', port=17876)
