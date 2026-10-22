"""Observed OpenCode message snapshots, scoped to one accepted runner attempt.

These are native HTTP records, not a claim that an SSE stream was captured.
"""
from datetime import datetime, timezone
import json
from .runner_activity import receipt
from .agent_activity_cost import estimate


def retain_messages(root, session, messages):
    value = receipt({'method':'opencode/messageSnapshot','params':{'sessionID':session,'messages':messages}})
    raw = json.dumps(value, ensure_ascii=False) + '\n'
    retained = len(raw.encode('utf8')) <= 1024 * 1024
    if not retained:
        value = receipt({'method':'opencode/captureLimit','params':{'sessionID':session}})
        raw = json.dumps(value) + '\n'
    with (root / 'activity-events.jsonl').open('a', encoding='utf8') as target:
        target.write(raw)
    return retained


def _at(value, fallback):
    if type(value) not in {int,float}:
        return fallback
    try:
        return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        return fallback


def project(events, *, root_thread=None, model=None):
    messages = {}
    for event in events:
        raw=event['raw']; native=raw.get('event',raw)
        if native.get('method') != 'opencode/messageSnapshot':
            continue
        params=native.get('params',{})
        if params.get('sessionID') != root_thread:
            continue
        for message in params.get('messages',[]):
            if not isinstance(message,dict):
                continue
            info=message.get('info') or {}
            if info.get('sessionID') != root_thread or not isinstance(info.get('id'),str):
                continue
            messages[info['id']]=(message,raw.get('received_at',event['received_at']))
    turns={};items=[];totals=[];points=[]
    for identity,(message,received) in messages.items():
        info=message['info']; role=info.get('role');times=info.get('time') or {}
        if role not in {'user','assistant'}:
            continue
        turn_id=identity if role=='user' else info.get('parentID')
        started=_at(times.get('created'),received);ended=_at(times.get('completed'),None)
        if turn_id:
            turn=turns.setdefault(turn_id,{'id':turn_id,'thread':root_thread,'started':started,'ended':None,'status':'running'})
            turn['started']=min(turn['started'],started)
            if ended:
                turn.update(ended=max(turn.get('ended') or ended,ended),status='failed' if info.get('error') else 'completed')
        parts=message.get('parts',[])
        text='\n'.join(part.get('text','') for part in parts if isinstance(part,dict) and part.get('type')=='text')
        # Retain the original native record in every projected message source.
        if text or role=='user':
            item={'id':identity,'type':'userMessage' if role=='user' else 'agentMessage',
                  'text':text,'native':message,'provider':'opencode'}
            items.append({'id':identity,'thread':root_thread,'turn':turn_id,'started':started,
                          'ended':ended if role=='assistant' else started,'item':item})
        for part in parts:
            if not isinstance(part,dict) or part.get('type')!='tool':
                continue
            state=part.get('state') or {};native_time=state.get('time') or {};inputs=state.get('input') or {}
            command=inputs.get('command') if isinstance(inputs,dict) else None
            item={'id':part.get('id') or part.get('callID'),'type':'commandExecution' if isinstance(command,str) else 'toolCall',
                  'toolName':part.get('tool'),'native':part,'provider':'opencode','status':state.get('status')}
            if isinstance(command,str):
                output=state.get('output');exit_code=(state.get('metadata') or {}).get('exit')
                # The isolated command worker returns a JSON result envelope.
                # Keep the native part intact while rendering stdout/stderr as text.
                try:
                    result=json.loads(output) if isinstance(output,str) else None
                except (ValueError,TypeError):
                    result=None
                if isinstance(result,dict) and isinstance(result.get('stdout'),str) and isinstance(result.get('stderr'),str) and type(result.get('exit_code')) is int:
                    output=result['stdout']+result['stderr'];exit_code=result['exit_code']
                item.update(command=command,aggregatedOutput=output,exitCode=exit_code)
            if not item['id']:
                continue
            items.append({'id':item['id'],'thread':root_thread,'turn':turn_id,
                          'started':_at(native_time.get('start'),started),
                          'ended':_at(native_time.get('end'),ended),'item':item})
        if role=='assistant':
            tokens=info.get('tokens');cache=(tokens.get('cache') or {}) if isinstance(tokens,dict) else {}
            values=[tokens.get(key) for key in ('input','output','reasoning')] if isinstance(tokens,dict) else []
            values.extend(cache.get(key) for key in ('read','write'))
            if len(values)!=5 or any(type(value) is not int or value<0 for value in values):
                totals.append(None)
                continue
            fresh,output,reasoning,read,write=values
            # OpenCode stores non-cached input and non-reasoning output separately.
            usage={'inputTokens':fresh+read+write,'cachedInputTokens':read,'cacheWriteInputTokens':write,
                   'outputTokens':output+reasoning,'reasoningOutputTokens':reasoning,
                   'totalTokens':fresh+read+write+output+reasoning}
            totals.append(usage)
            cumulative={key:sum(total[key] for total in totals) for key in usage} if all(total is not None for total in totals) else None
            if cumulative is not None:
                points.append({'at':ended or received,'thread':root_thread,'usage':cumulative,'cost':estimate(model,cumulative)})
    usage={key:sum(total[key] for total in totals) for key in totals[0]} if totals and all(total is not None for total in totals) else None
    cost=estimate(model,usage);cost.update(per_thread={root_thread:estimate(model,usage)},model_provenance={root_thread:'native OpenCode response metadata'})
    return {'turns':list(turns.values()),'items':sorted(items,key=lambda item:item['started']),
            'threads':[{'id':root_thread,'parent':None}] if root_thread else [],
            'usage':usage,'usage_by_thread':{root_thread:usage},'usage_points':points,
            'telemetry':[],'telemetry_coverage':'not observed; native OpenCode HTTP message snapshots only',
            'uncorrelated_thread_count':0,'clock':'native message timestamps; runner receipt fallback',
            'cost':cost,'cost_reason':cost.get('reason') or cost['basis']}
