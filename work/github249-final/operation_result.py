"""Read one real host intent result without modifying it."""
import json,sqlite3,sys
from pathlib import Path


def main():
 kind,request_id=sys.argv[1:];assert kind in {'issue','pr'};root=Path('C:/CodeWorkspace/laomedo');e=root/'claude-review.local/github-249-20261106';state=Path(json.loads((e/'runtime-path.json').read_text())['path']);targets=json.loads((state/'live-targets.json').read_text());table='issue_node_intents' if kind=='issue' else 'pr_node_intents'
 with sqlite3.connect('file:'+(state/(kind+'.db')).as_posix()+'?mode=ro',uri=True) as db:row=db.execute('SELECT result FROM '+table+' WHERE grant_ref=? AND request_id=?',(targets[kind]['grant_ref'],request_id)).fetchone()
 if row and row[0]:print(json.dumps(json.loads(row[0])['operation']))
 else:print('{}')

if __name__=='__main__':main()
