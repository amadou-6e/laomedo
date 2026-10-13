"""Bounded, metadata-only projection of host-owned native Codex run evidence.

Raw text, commands, arguments, environment values and tool results are never
returned. Full content inspection needs a separate redaction/privacy contract.
"""
import json
from pathlib import Path
import re
import stat
from uuid import UUID

MAX_RECORD = 1024 * 1024
MAX_TRACE = 32 * 1024 * 1024
MAX_LINE = 256 * 1024
PAGE_SIZE = 200
STATES = {'prepared','running','completed','failed','cancelled','timeout','interrupted','unknown'}
ITEMS = {'userMessage','agentMessage','reasoning','commandExecution','fileChange','dynamicToolCall','mcpToolCall','webSearch','imageView','plan','contextCompaction'}
EFFORTS = {'none','minimal','low','medium','high','xhigh','max'}

def identifier(value):
    return value if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',value) else None

def number(value): return value if type(value) is int and value >= 0 else None

def model(value):
    return value if isinstance(value,str) and re.fullmatch(r'(?:gpt|o[134]|claude|codex)[A-Za-z0-9_.:/-]{0,80}',value) else None

def member(value, choices, default=None):
    return value if isinstance(value,str) and value in choices else default

def linked(path):
    info=path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info,'st_file_attributes',0) & getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',1024))

def safe_file(root, path):
    root=Path(root).absolute(); path=Path(path).absolute()
    if not path.is_relative_to(root): raise ValueError('inspection_path_denied')
    for candidate in (path,*path.parents):
        if linked(candidate):raise ValueError('inspection_path_denied')
        if candidate==root:break
    if not path.is_file():raise ValueError('inspection_unavailable')
    return path

def read_json(root,path):
    path=safe_file(root,path)
    with path.open('rb') as stream:
        raw=stream.read(MAX_RECORD+1)
    if len(raw)>MAX_RECORD:raise ValueError('inspection_record_limit')
    value=json.loads(raw)
    if not isinstance(value,dict):raise ValueError('inspection_unavailable')
    return value

def validation(value):
    if not isinstance(value,dict):return None
    errors=[]
    for error in value.get('errors',[])[:64] if isinstance(value.get('errors'),list) else []:
        if not isinstance(error,dict):continue
        code=member(error.get('code'),{'required','type_mismatch','nonempty','enum','minimum','maximum','min_length','max_length','object_required','submission_too_large','invalid_json_value','requirements_unbound','requirements_revision_mismatch','task_outcome_mismatch'},None)
        path=error.get('path')
        if code:errors.append({'code':code,'path':path if isinstance(path,str) and re.fullmatch(r'(?:/[A-Za-z0-9_]+)*',path) and len(path)<=128 else ''})
    return {'contract_status':member(value.get('contract_status'),{'accepted','rejected'},'unknown'),'errors':errors}

def run_id(value):
    try:
        if str(UUID(value))!=value:raise ValueError()
    except (ValueError,TypeError,AttributeError):raise ValueError('invalid_run_id') from None
    return value

def inspect_run(state, selected, after=0):
    selected=run_id(selected)
    if type(after) is not int or not 0<=after<=1000000:raise ValueError('invalid_inspection_cursor')
    root=Path(state).absolute();directory=root/'runs'/selected
    record=read_json(root,directory/'record.json')
    if record.get('run_id')!=selected:raise ValueError('inspection_identity_mismatch')
    try:ledger=read_json(root,root/'turn-ledger.json')
    except (ValueError,OSError):ledger={}
    used=number(ledger.get('attempted_turns'));cap=number(ledger.get('max_authorized_turns'))
    answer=record.get('answer');outcome='unknown';syntax=None
    if isinstance(answer,str):
        try:
            submission=json.loads(answer)
            if isinstance(submission,dict) and member(submission.get('task_outcome'),{'success','failure'}):outcome=submission['task_outcome']
        except json.JSONDecodeError as error:
            syntax={'code':'invalid_json','reason':'extra_data' if error.msg=='Extra data' else 'invalid_syntax','line':error.lineno,'column':error.colno}
    summary={'run_id':selected,'thread_id':identifier(record.get('thread_id')),
        'request_id':identifier(record.get('client_request_id')),
        'executor_status':member(record.get('status'),STATES,'unknown'),
        'task_outcome':outcome,'evidence_complete':record.get('evidence_complete') if type(record.get('evidence_complete')) is bool else None,
        'completion_basis':member(record.get('completion_basis'),{'native_trace_closure','process_exit'},None),
        'requested_model':model(record.get('requested_model')),'effective_model':model(record.get('effective_model')),
        'requested_effort':member(record.get('requested_effort'),EFFORTS,None),
        'effective_effort':member(record.get('effective_effort'),EFFORTS,None),
        'error_category':member(record.get('error_category'),{'turn_timeout','runner_restarted','container_termination_unverified','outstanding_command_completion_unknown','model_turn_cap_reached','turn_dispatch_rejected','native_error','cancelled_by_user'},None),
        'precheck':{'installed':record.get('precheck',{}).get('installed') if isinstance(record.get('precheck'),dict) and type(record['precheck'].get('installed')) is bool else None,
                    'call_count':number(record.get('precheck',{}).get('call_count')) if isinstance(record.get('precheck'),dict) else None},
        'output_validation':validation(record.get('output_validation')),'output_syntax':syntax,
        'output_retries':number(record.get('output_retries')),'output_correction_count':number(record.get('output_correction_count')),
        'output_correction_blocked':member(record.get('output_correction_blocked'),{'side_effect_safety_unverified','model_turn_cap_reached'},None),
        'budget':{'used':used,'cap':cap,'remaining':max(0,cap-used) if cap is not None and used is not None else None},
        'usage':{key:number(record.get('usage',{}).get(key)) if isinstance(record.get('usage'),dict) else None for key in ('input_tokens','output_tokens','cached_input_tokens')}}
    events=[];trace_status='complete';next_cursor=None;scanned=0
    if not (directory/'raw-events.jsonl').exists():
        return {'schema_version':'laomedo.agent-inspection.v1','summary':summary,'events':[], 'trace_status':'missing','next_cursor':None,'content_policy':'metadata_only'}
    trace=safe_file(root,directory/'raw-events.jsonl')
    with trace.open('rb') as stream:
        for index in range(1000001):
            raw=stream.readline(MAX_LINE+1)
            if not raw:break
            scanned+=len(raw)
            if len(raw)>MAX_LINE or scanned>MAX_TRACE:trace_status='limited';break
            if index<after:continue
            if not raw.endswith(b'\n'):
                trace_status='incomplete';break
            try:event=json.loads(raw)
            except (ValueError,UnicodeError):trace_status='invalid';break
            if not isinstance(event,dict):trace_status='invalid';break
            method=event.get('method');params=event.get('params')
            if not member(method,{'item/started','item/completed','turn/started','turn/completed','error'}) or not isinstance(params,dict):continue
            item=params.get('item') if isinstance(params.get('item'),dict) else {}
            kind=item.get('type')
            projected={'sequence':index,'event_type':method,'item_type':member(kind,ITEMS,'unknown'),
                'item_id':identifier(item.get('id')),'turn_id':identifier(params.get('turnId') or (params.get('turn') if isinstance(params.get('turn'),dict) else {}).get('id')),
                'tool':identifier(item.get('tool')) if kind=='dynamicToolCall' else None,
                'exit_code':item.get('exitCode') if type(item.get('exitCode')) is int else None,
                'duration_ms':number(item.get('durationMs')),'content_withheld':True}
            events.append(projected)
            if len(events)==PAGE_SIZE:next_cursor=index+1;trace_status='paged';break
        else:trace_status='limited'
    return {'schema_version':'laomedo.agent-inspection.v1','summary':summary,'events':events,
            'trace_status':trace_status,'next_cursor':next_cursor,'content_policy':'metadata_only'}

def list_runs(state):
    root=Path(state).absolute();rows=[]
    for directory in (root/'runs').iterdir():
        if len(rows)>=100:break
        if not directory.is_dir():continue
        try:
            selected=run_id(directory.name);record=read_json(root,directory/'record.json')
            if record.get('run_id')!=selected:continue
            rows.append({'run_id':selected,'status':member(record.get('status'),STATES,'unknown')})
        except (ValueError,OSError):continue
    return {'schema_version':'laomedo.agent-history.v1','runs':rows,'limit':100,'order':'filesystem','truncated':len(rows)==100}
