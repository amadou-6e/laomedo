"""Versioned API-equivalent estimates, never subscription invoices."""
from decimal import Decimal

CATALOG_DATE = '2026-10-15'
RATES = {
    'gpt-6-luna': ('0.1','0.01','0.5'),
    'gpt-6.1-sol': ('2','0.1','10'),
}
SOURCES = {model:{'url':f'https://developers.openai.com/api/docs/models/{model}',
                  'fetched_at':'2026-10-15','tier':'Standard','currency':'USD'} for model in RATES}


def estimate(model, usage):
    metadata={'currency':'USD','catalog_date':CATALOG_DATE,'model':model,
              'basis':'API-equivalent token estimate; assumes Standard tier, no regional premium; excludes tool fees; not a subscription charge',
              'source':f'https://developers.openai.com/api/docs/models/{model}' if model in RATES else None}
    metadata['source_record']=SOURCES.get(model)
    def unknown(reason):
        return {**metadata,'amount':None,'reason':reason}
    if model not in RATES:
        return unknown('Effective model has no verified price entry.')
    if not isinstance(usage,dict):
        return unknown('Token usage is unavailable.')
    keys=('inputTokens','cachedInputTokens','outputTokens')
    if any(type(usage.get(key)) is not int or usage[key]<0 for key in keys):
        return unknown('Token categories are incomplete.')
    inputs,cached,outputs=(usage[key] for key in keys)
    if cached>inputs:
        return unknown('Cached input exceeds input.')
    if usage.get('cacheWriteInputTokens',0):
        return unknown('Cache-write overlap semantics have not been verified.')
    if inputs>272000:
        return unknown('Per-request context lengths are needed to apply long-context prices.')
    rates=[Decimal(value) for value in RATES[model]]
    amount=((inputs-cached)*rates[0]+cached*rates[1]+outputs*rates[2])/Decimal(1000000)
    return {**metadata,'amount':float(amount),'reason':None}
