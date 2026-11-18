"""Bounded real assistant command acceptance; private session remains in memory."""
import json, urllib.request, time
from pathlib import Path
from uuid import uuid4
ROOT=Path("C:/CodeWorkspace/laomedo")
meta=json.loads((ROOT/".tools/assistant-291-live.json").read_text())
base=meta["base"]
def call(path,body=None,token=None):
    headers={"Content-Type":"application/json","Origin":base}
    if token: headers["Authorization"]="Bearer "+token
    r=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
    return json.load(urllib.request.urlopen(r,timeout=180))
token=call("/api/v1/auto_login")["access_token"]
chat=call("/api/v1/laomedo/assistant/conversations",{"model":"gpt-6-luna","effort":"low"},token)
(ROOT/".tools/assistant-293-chat.json").write_text(json.dumps({"conversation":chat["id"],"base":base}))
prompt="Use Laomedo MCP list_native_commands and list_native_agents. Report the supported built-in commands briefly and whether native agents are supported. Then propose /status with no arguments for human approval using the actual observed catalog revision and a new operation_key. Do not approve or execute it yourself."
call("/api/v1/laomedo/assistant/conversations/"+chat["id"]+"/messages",{"text":prompt,"client_message_id":str(uuid4())},token)
print("conversation",chat["id"],flush=True)
for _ in range(240):
    d=call("/api/v1/laomedo/assistant/conversations/"+chat["id"],token=token)
    state=d.get("conversation",d).get("state")
    if state not in {"starting","running","stopping"}:
        print(json.dumps({"state":state,"messages":[{"state":x.get("state"),"response":x.get("response"),"error_code":x.get("error_code")} for x in d.get("messages",[])],"native_actions":d.get("native_actions",[])},ensure_ascii=True),flush=True)
        break
    time.sleep(2)
else: raise RuntimeError("acceptance deadline exceeded; no automatic retry")
