import json
from pathlib import Path
from laomedo.skills.registry.store import SkillStore
root=Path('C:/CodeWorkspace/laomedo');e=root/'claude-review.local/github-249-20261106';state=Path(json.loads((e/'runtime-path.json').read_text())['path'])
workspace=state/'workspace';workspace.mkdir(exist_ok=True);(workspace/'README.md').write_text('# GitHub operation validation\nRead-only agent context. Do not edit files or run commands.\n',encoding='utf-8')
store=SkillStore(state/'registry')
try:revision=store.import_skill('pr-feedback-title',root/'.tools/github-restored-245/examples/github/title-skill')
except Exception as error:
 if str(error)!='skill_already_exists':raise
 revision=store.resolve('pr-feedback-title')
(e/'live-skill.json').write_bytes(json.dumps(revision,indent=2).encode('utf-8'))
print('Prepared isolated workspace and imported real instruction skill; no model dispatch.')
