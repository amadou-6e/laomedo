"""Run the unmodified production CLI with credential-free urllib mutation auditing."""
import json,os,runpy,sys,time
from pathlib import Path
from urllib.parse import urlsplit


def main():
    audit=Path(os.environ['VALIDATION_HTTP_AUDIT_FILE']);module=sys.argv[1];sys.argv=sys.argv[1:]
    def observe(event,args):
        if event!='urllib.Request':return
        url,_,_,method=args
        parsed=urlsplit(url)
        if parsed.hostname!='api.github.com' or method not in {'POST','PATCH','PUT','DELETE'}:return
        with audit.open('a',encoding='utf-8') as output:output.write(json.dumps({'method':method,'path':parsed.path,'at':time.time()})+'\n')
    sys.addaudithook(observe);runpy.run_module(module,run_name='__main__')

if __name__=='__main__':main()
