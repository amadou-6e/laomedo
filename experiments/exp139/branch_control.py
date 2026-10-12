import json, runpy, sys
from pathlib import Path
from experiments.exp139 import mailbox_control as fixture

fixture.SCRIPT=fixture.SCRIPT.replace("'-b','fixture-branch'", "'-b','main'").replace("cp.execFileSync('git',['-C','/draft','remote'", "cp.execFileSync('git',['-C','/draft','-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','--allow-empty','-m','baseline']);\n cp.execFileSync('git',['-C','/draft','checkout','--detach']);\n cp.execFileSync('git',['-C','/draft','remote'")
fixture.SCRIPT=fixture.SCRIPT.replace("['network',", "['fixed', 'git switch -c fixture-branch && git push origin HEAD:refs/heads/fixture-branch >/draft/fixed-stdout 2>/draft/fixed-stderr && printf PUSH_CONFIRMED > /draft/fixed-result'],\n ['network',")
source=Path(fixture.__file__).read_text()
source=source[source.index('def probe():'):source.index("if __name__==")]
source=source.replace("assert expected['push']['exit']==0 and expected['push']['result']=='PUSH_CONFIRMED'", "assert expected['push']['exit']==1 and expected['push']['result']=='absent'\n        assert expected['fixed']['exit']==0 and expected['fixed']['result']=='PUSH_CONFIRMED'")
namespace=dict(vars(fixture))
exec(compile(source,fixture.__file__,'exec'),namespace)
result=namespace['probe']()
result['claim']='detached_missing_branch_fails_before_mediation; explicit_branch_creation_enables_fake_push'
target=Path(fixture.__file__).with_name('BRANCH-CONTROL.json')
target.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps({'model_turns':0,'provider_writes':0,'branch_negative_and_positive_controls':True}))
