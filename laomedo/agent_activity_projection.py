"""Project native notifications without summing cumulative token snapshots."""


def project(events, *, root_thread=None, model=None):
    turns, items, threads, latest, baselines = {}, {}, {}, {}, {}
    points = []
    telemetry = []
    diagnostics = []
    previous = {}
    invalid_usage = set()
    for receipt in events:
        raw=receipt['raw']
        if raw.get('method') == 'capture/usageBaseline':
            baselines.update({key:(value or {}).get('total',{}) for key,value in raw['threads'].items()})
            continue
        event=raw.get('event',raw)
        params=event.get('params',{})
        method=event.get('method',event.get('type','unknown'))
        if method == 'claude/result':
            diagnostics.append(params)
        if method == 'otel/record':
            telemetry.append(params)
            continue
        timestamp=raw.get('received_at',receipt['received_at'])
        thread=params.get('threadId')
        turn=params.get('turn',{})
        turn_id=params.get('turnId') or turn.get('id')
        if method == 'thread/started':
            value=params.get('thread',{})
            if value.get('id'):
                threads[value['id']]={'id':value['id'],'parent':value.get('parentThreadId')}
        if turn_id and (method.startswith('turn/') or method.startswith('item/')):
            key=(thread,turn_id)
            lane=turns.setdefault(key,{'id':turn_id,'thread':thread,'started':timestamp,'ended':None,'status':'running'})
            if method == 'turn/completed':
                lane.update(ended=timestamp,status=turn.get('status','completed'))
        item=params.get('item')
        if isinstance(item,dict) and item.get('id'):
            key=(thread,item['id'])
            value=items.setdefault(key,{'id':item['id'],'thread':thread,'turn':turn_id,'started':timestamp,'ended':None,'item':item})
            if method == 'item/updated' and value['ended'] is None:
                value['item'] = item
            if method == 'item/completed':
                if value['ended'] and value['item'] != item:
                    value['conflicting_receipts']=True
                value.update(ended=timestamp,item=item)
            child=item.get('agentThreadId')
            if child:
                threads[child]={'id':child,'parent':thread}
            if item.get('type') in {'collabAgentToolCall','collabAgentSpawnToolCall'}:
                for child in item.get('receiverThreadIds',[]):
                    threads.setdefault(child,{'id':child,'parent':thread})
        if method == 'thread/tokenUsage/updated' and thread:
            total=params.get('tokenUsage',{}).get('total')
            if total is None and params.get('usage_scope') in {'native_session_cumulative', 'terminal_receipt_unavailable'}:
                invalid_usage.add(thread)
                latest[thread]=None
            if isinstance(total,dict):
                base=baselines.get(thread,{})
                keys=('inputTokens','cachedInputTokens','cacheWriteInputTokens','outputTokens','reasoningOutputTokens','totalTokens')
                delta={key:total[key]-base.get(key,0) for key in keys
                       if type(total.get(key)) is int and type(base.get(key,0)) is int}
                if any(type(total.get(key)) is int and total[key]<value for key,value in previous.get(thread,{}).items()):
                    invalid_usage.add(thread)
                previous[thread]={key:total[key] for key in keys if type(total.get(key)) is int}
                if thread in invalid_usage or any(value<0 for value in delta.values()):
                    latest[thread]=None
                else:
                    latest[thread]=delta
                    from .agent_activity_cost import estimate
                    points.append({'at':timestamp,'thread':thread,'usage':delta,
                                   'cost':estimate(model if thread == root_thread else None,delta)})
    related={root_thread} if root_thread else set(latest)|{value['thread'] for value in turns.values()}
    changed=True
    while changed:
        before=len(related)
        related.update(value['id'] for value in threads.values() if value['parent'] in related)
        changed=len(related)!=before
    uncorrelated=set(latest)-related
    latest={key:value for key,value in latest.items() if key in related}
    turns={key:value for key,value in turns.items() if value['thread'] in related}
    items={key:value for key,value in items.items() if value['thread'] in related}
    points=[point for point in points if point['thread'] in related]
    usage=None
    if latest and all(value is not None for value in latest.values()):
        usage={key:sum(value[key] for value in latest.values())
               for key in ('inputTokens','cachedInputTokens','cacheWriteInputTokens','outputTokens','reasoningOutputTokens','totalTokens')
               if all(key in value for value in latest.values())}
    if related-set(latest):
        usage=None
    from .agent_activity_cost import estimate
    models={root_thread:model} if root_thread and model else {}
    model_provenance={root_thread:'native runner effective model'} if root_thread and model else {}
    observed_models={}
    for record in telemetry:
        attrs=record.get('attributes',{})
        thread=attrs.get('conversation.id')
        observed_model=attrs.get('model') or attrs.get('gen_ai.response.model')
        if isinstance(thread,str) and isinstance(observed_model,str):
            observed_models.setdefault(thread,set()).add(observed_model)
    for thread,values in observed_models.items():
        if thread in models and (len(values)!=1 or models[thread] not in values):
            models[thread]=None
        elif thread not in models and len(values)==1:
            models[thread]=next(iter(values))
            model_provenance[thread]='runtime-reported OTLP metadata; not independently attested'
    for point in points:
        point['cost']=estimate(models.get(point['thread']),point['usage'])
    # Child model and usage must be independently observed; do not price all
    # child activity at the parent's model or claim an inclusive known total.
    cost=estimate(models.get(root_thread),latest.get(root_thread))
    per_thread={thread:estimate(models.get(thread),latest.get(thread)) for thread in related}
    if len(related)>1:
        if all(value['amount'] is not None for value in per_thread.values()):
            cost={**cost,'amount':sum(value['amount'] for value in per_thread.values()),'reason':None}
        else:
            cost={**cost,'amount':None,'reason':'Inclusive subagent pricing requires independently confirmed child models and usage.'}
    cost['per_thread']=per_thread
    cost['model_provenance']=model_provenance
    if any(thread != root_thread for thread in related):
        cost['basis']+='; child model attribution is runtime-reported, not independently attested'
    cost_reason=cost.get('reason') or cost['basis']
    return {'turns':list(turns.values()),'items':list(items.values()),'threads':list(threads.values()),
            'diagnostics':[value for value in diagnostics if value.get('threadId') in related],
            'telemetry':telemetry,'telemetry_coverage':'observed; exporter flush completeness unverified' if telemetry else 'not observed',
            'uncorrelated_thread_count':len(uncorrelated),
            'usage':usage,'usage_by_thread':latest,'usage_points':points,
            'clock':'runner receipt time','cost':cost,
            'cost_reason':cost_reason}
