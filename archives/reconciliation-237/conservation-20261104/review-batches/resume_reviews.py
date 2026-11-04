"""Serially resume one reviewer session; stop on any uncertain/error request."""
import json
import argparse
from pathlib import Path
import subprocess
import time

r=Path('C:/CodeWorkspace/laomedo');out=r/'claude-review.local/github-consolidation/checkpoint-audit-20261104/review-batches'
rows=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
parser=argparse.ArgumentParser()
parser.add_argument('--resolve-inspected-pending-sha256')
args=parser.parse_args()
progress=json.loads((out/'progress.json').read_text(encoding='utf-8')) if (out/'progress.json').exists() else []
completed={x['name'] for x in progress if x['status']=='response_recorded_verdict_requires_reading'}
pending_resolution=args.resolve_inspected_pending_sha256
for row in rows:
 if row['name'] in completed:
  previous=next(x for x in reversed(progress) if x['name']==row['name'] and x['status']=='response_recorded_verdict_requires_reading')
  assert Path(previous.get('output',str(Path(row['output']).with_suffix('.md')))).is_file()
  continue
 log=Path(row['output'])
 resolving=[]
 if log.exists():
  assert pending_resolution, 'Inspect the failed transcript and explicitly resolve its digest before resuming'
  diagnostic=json.loads((out/'runtime-4-transcript-diagnosis.json').read_text(encoding='utf-8'))
  assert diagnostic['pending_digest']==pending_resolution and any(x.get('error')=='rate_limit' for x in diagnostic['records'])
  resolving=['-ResolvePendingSha256',pending_resolution]
  log=log.with_name(log.stem+'-resumed.log');assert not log.exists()
  pending_resolution=None
 progress.append({'name':row['name'],'status':'running','started':time.time()})
 (out/'progress.json').write_text(json.dumps(progress,indent=2)+'\n',encoding='utf-8')
 command=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(r/'my-skills/05-software_engineering/skill-claude-reviewer/01-scripts/Invoke-ClaudeReview.ps1'),'-WorkspaceRoot',str(r),'-StateDirectory',str(r/'claude-review.local/sessions'),'-CodexSessionId','01a14a4b-331a-72b2-947e-ef8192b3342d','-TimeoutSeconds','600','-PromptFile',row['prompt'],*resolving]
 with log.open('xb') as stream:result=subprocess.run(command,cwd=r,stdout=stream,stderr=subprocess.STDOUT,timeout=650)
 text=log.read_text(encoding='utf-8-sig',errors='replace')
 answers=[]
 for line in text.splitlines():
  try:value=json.loads(line)
  except ValueError:continue
  if 'result' in value:answers.append(value)
 if result.returncode or not answers or answers[-1].get('is_error'):
  progress[-1].update(status='uncertain_or_error_stop_no_retry',returncode=result.returncode)
  (out/'progress.json').write_text(json.dumps(progress,indent=2)+'\n',encoding='utf-8');print(json.dumps(progress[-1]),flush=True);raise SystemExit(1)
 progress[-1].update(status='response_recorded_verdict_requires_reading',seconds=time.time()-progress[-1]['started'])
 log.with_suffix('.md').write_text(answers[-1]['result']+'\n',encoding='utf-8')
 progress[-1]['output']=str(log.with_suffix('.md'))
 (out/'progress.json').write_text(json.dumps(progress,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(progress[-1]),flush=True)
