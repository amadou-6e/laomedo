"""Run the exact proposed bootstrap with dummy mounts and a stub app-server."""
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch
from experiments.exp139.bindings import MailboxAppServer
from experiments.exp139.helper_control import IMAGE, ROOT
from laomedo.agents.local_runner import AppServer


def probe():
    with tempfile.TemporaryDirectory(prefix='laomedo139-startup-') as temporary:
        root=Path(temporary)
        (root/'bin').mkdir()
        (root/'capability').write_text('DUMMY_CAPABILITY')
        stub=(root/'bin/codex')
        stub.write_text('#!/bin/sh\n'
            'test -f /draft/.git/laomedo-mediation/ready || exit 2\n'
            'test -f /home/runner/.codex/config.toml || exit 2\n'
            'test "$GIT_EXEC_PATH" = /run/laomedo/bin || exit 2\n'
            'test "$LAOMEDO_MEDIATION_FILE_STDIO" = 1 || exit 2\n'
            'printf \'{"bootstrap_ready":true,"model_turns":0,"provider_writes":0}\\n\'\n',newline='\n')
        stub.chmod(0o755)
        command=['docker','run','--rm','-i','--pull=never','--network','none',
            '--cap-drop','ALL','--security-opt','no-new-privileges','--user','10001:10001',
            '--tmpfs','/draft:rw,mode=1777',
            '--tmpfs','/home/runner/.codex:rw,mode=0700,uid=10001,gid=10001',
            '--mount',f'type=bind,source={root},target=/fixture,readonly',
            '--mount',f'type=bind,source={root / "capability"},target=/run/laomedo/capability,readonly',
            '--mount',f'type=bind,source={ROOT / "laomedo/agent_mediation_client.mjs"},target=/run/laomedo/mediate.mjs,readonly',
            '--mount',f'type=bind,source={ROOT / "src/laomedo/agents/resources/runner-config.toml"},target=/config.toml,readonly',
            '--env','LAOMEDO_MEDIATOR_URL=http://host.docker.internal:1/v1/mediate',
            '--env','LAOMEDO_MEDIATOR_INSTANCE='+'0'*32,
            '--env','PATH=/fixture/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
            '--workdir','/draft',IMAGE,'sh','-c','original bootstrap','bootstrap','app-server','--stdio']
        # Capture the production rewrite, including its profile arguments.
        with patch.object(AppServer,'__init__',return_value=None) as parent:
            MailboxAppServer(command,root)
        executed=parent.call_args.args[0]
        result=subprocess.run(executed,input=b'',capture_output=True,timeout=15)
        if result.returncode: raise ValueError('exact_bootstrap_failed')
        record=json.loads(result.stdout.decode().splitlines()[-1])
        assert record['bootstrap_ready']
        return {**record,'container_network':'none','credential_fixture':'dummy_only',
                'app_server':'stub','bootstrap':'exact_MailboxAppServer_rewrite'}


if __name__=='__main__':
    result=probe()
    Path(__file__).with_name('STARTUP-CONTROL.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result))
