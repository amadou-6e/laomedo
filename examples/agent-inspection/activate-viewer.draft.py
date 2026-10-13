import hashlib, json, subprocess, time, urllib.request, gzip
from pathlib import Path
ROOT = Path(r"C:/CodeWorkspace/agentviz")
OLD="laomedo-langflow-view139"
CANDIDATE="laomedo-langflow-agent-inspection-candidate"
ROLLBACK="laomedo-langflow-view139-rollback-agent-inspection"
BASE="http://127.0.0.1:7864"
RECORD=ROOT/"claude-review.local/agent-inspection-activation.json"

def docker(*args):
    result=subprocess.run(["docker",*args],capture_output=True,text=True,encoding="utf-8")
    if result.returncode: raise RuntimeError("docker_operation_failed:"+args[0])
    return result.stdout

def inspect(name): return json.loads(docker("inspect",name))[0]
def digest(value): return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def login():
    return json.load(urllib.request.urlopen(BASE+"/api/v1/auto_login",timeout=15))["access_token"]
def api(path, token):
    try:
        response=urllib.request.urlopen(urllib.request.Request(BASE+path,headers={"Authorization":"Bearer "+token}),timeout=60)
    except urllib.error.HTTPError as exc:
        raise RuntimeError("api_check_failed:"+path+":"+str(exc.code)) from None
    data=response.read()
    return json.loads(gzip.decompress(data) if response.headers.get("Content-Encoding")=="gzip" else data)
def snapshot():
    token=login(); user=api("/api/v1/users/whoami",token)
    listing=api("/api/v1/flows/",token)
    if isinstance(listing,dict): listing=listing.get("flows",listing.get("items"))
    if not isinstance(listing,list): raise RuntimeError("flow_listing_shape_unknown")
    flows={}; skill=None
    for entry in listing:
        if entry.get("user_id")!=user["id"]: continue
        fid=entry["id"]; flow=entry
        if entry.get("user_id")==user["id"]:
            flow=api("/api/v1/flows/"+fid,token)
            if api("/api/v2/workflows/pending?flow_id="+fid,token): raise RuntimeError("pending_workflow_refuses_replacement")
        flows[fid]=digest({k:flow.get(k) for k in ("id","name","description","folder_id","data")})
        for node in (flow.get("data") or {}).get("nodes",[]):
            data=node.get("data",{})
            if data.get("type")=="LaomedoSkill":
                template=data["node"]["template"]
                sid=template.get("resolved_skill_id",{}).get("value") or template["skill_id"].get("value"); rev=template.get("resolved_revision_id",{}).get("value") or template["revision_id"].get("value")
                if sid and rev: skill=(sid,rev)
    catalog=api("/api/v1/all",token)
    catalog_names={k:sorted(v) for k,v in catalog.items() if isinstance(v,dict)}
    db_code="""import sqlite3,json,hashlib
c=sqlite3.connect('file:/app/langflow/langflow.db?mode=ro',uri=True)
d=lambda r:hashlib.sha256(json.dumps(r,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def flatten(v,path='',out=None):
    if out is None:out={}
    if isinstance(v,dict):
        for k,x in v.items():flatten(x,path+'/'+str(k),out)
    elif isinstance(v,list):
        for i,x in enumerate(v):flatten(x,path+'/'+str(i),out)
    else:out[path]=d(v)
    return out
rows=list(c.execute('select name,description,data from flow where user_id is null'))
print(json.dumps({'owned':{r[0]:d(r) for r in c.execute('select id,user_id,name,description,folder_id,data from flow where user_id is not null')},'templates':{r[0]:d([r[0],r[1],json.loads(r[2])]) for r in rows},'template_fields':{r[0]:flatten({'name':r[0],'description':r[1],'graph':json.loads(r[2])}) for r in rows if r[0]=='Hybrid Search RAG'}}))"""
    database=json.loads(docker("exec",OLD,"/app/.venv/bin/python","-c",db_code))
    return {"user_id":user["id"],"flow_hashes":flows,"database_flows":database,"catalog_names":catalog_names},skill,token

def main():
    old=inspect(OLD)
    if not old["State"]["Running"]: raise RuntimeError("existing_viewer_not_running")
    before,skill,_=snapshot()
    if not skill: raise RuntimeError("saved_skill_selection_missing")
    manifest=json.loads((ROOT/"claude-review.local/agent-inspection-build-manifest.json").read_text(encoding="utf-8"))
    build=ROOT/"claude-review.local/agent-inspection-build"
    actual={f.relative_to(build).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in build.rglob("*") if f.is_file()}
    if actual!=manifest["assets"]: raise RuntimeError("build_manifest_mismatch")
    source=ROOT/"work-issue-graph.local"
    if subprocess.check_output(["git","-C",str(source),"rev-parse","HEAD"],text=True).strip()!=manifest["source_revision"]: raise RuntimeError("source_revision_mismatch")
    if subprocess.check_output(["git","-C",str(source),"status","--porcelain"]).strip(): raise RuntimeError("source_not_clean")
    store=Path(r"C:/Users/amado/AppData/Local/Temp/laomedo-standing-demo-20261012/skill-store")
    if not store.is_dir(): raise RuntimeError("standing_skill_registry_missing")
    env=dict(item.split("=",1) for item in old["Config"]["Env"])
    if env.get("LANGFLOW_DATABASE_URL") not in ("sqlite:////app/langflow/langflow.db","sqlite:///app/langflow/langflow.db"):
        raise RuntimeError("existing_database_location_unconfirmed")
    env.update({"PYTHONPATH":"/workspace","LANGFLOW_FRONTEND_PATH":"/skill-frontend"})
    env['LAOMEDO_AGENT_INSPECTION_URLS']='["http://host.docker.internal:8784"]'
    mounts=json.loads(json.dumps(old["HostConfig"]["Mounts"]))
    for mount in mounts:
        if mount["Target"]=="/workspace": mount["Source"]=str(source)
        if mount["Target"]=="/skill-frontend": mount["Source"]=str(build)
    args=["create","--name",CANDIDATE,"--pull=never","--network",old["HostConfig"]["NetworkMode"],"--cgroupns",old["HostConfig"]["CgroupnsMode"],"--ipc",old["HostConfig"]["IpcMode"],"--shm-size",str(old["HostConfig"]["ShmSize"]),"--restart","no","--log-driver","json-file","-p","127.0.0.1:7864:7860"]
    if old["Config"].get("User"): args += ["--user",old["Config"]["User"]]
    if old["Config"].get("WorkingDir"): args += ["--workdir",old["Config"]["WorkingDir"]]
    for k,v in (old["Config"].get("Labels") or {}).items(): args += ["--label",k+"="+v]
    for mount in mounts:
        value="type="+mount["Type"]+",source="+mount["Source"]+",target="+mount["Target"]
        if mount.get("ReadOnly"): value+=",readonly"
        args += ["--mount",value]
    for k,v in env.items(): args += ["-e",k+"="+v]
    args += ["--entrypoint","/app/.venv/bin/python",old["Config"]["Image"],"-m","uvicorn","laomedo.langflow_skill_viewer:create_app","--factory","--host","0.0.0.0","--port","7860"]
    docker(*args); candidate=inspect(CANDIDATE)
    expected=dict(old["HostConfig"]); expected["Mounts"]=mounts
    def normalize_mounts(items):
        values=json.loads(json.dumps(items))
        for value in values:
            path=value.get("Source", "").replace("\\", "/")
            if len(path)>2 and path[1:3]==":/":
                value["Source"]="/run/desktop/mnt/host/"+path[0].lower()+path[2:]
        return values
    comparison=dict(candidate["HostConfig"])
    expected["Mounts"]=normalize_mounts(expected["Mounts"])
    comparison["Mounts"]=normalize_mounts(comparison["Mounts"])
    mismatches=[k for k in expected if expected[k]!=comparison.get(k)]
    if mismatches:
        if mismatches==["Mounts"]: print("mount_comparison:"+json.dumps({"expected":expected["Mounts"],"actual":candidate["HostConfig"].get("Mounts")}))
        docker("rm",CANDIDATE); raise RuntimeError("candidate_protection_mismatch:"+",".join(mismatches))
    ce=dict(item.split("=",1) for item in candidate["Config"]["Env"])
    if ce!=env or candidate["Image"]!=old["Image"]: raise RuntimeError("candidate_configuration_mismatch")
    for mount in candidate["Mounts"]:
        if mount["Destination"] in ("/skills","/workspace","/skill-frontend") and mount["RW"]: raise RuntimeError("candidate_readonly_mount_mismatch")
    record={"source_revision":manifest["source_revision"],"build_manifest_hash":hashlib.sha256((ROOT/"claude-review.local/agent-inspection-build-manifest.json").read_bytes()).hexdigest(),"before":before,"candidate_protections_match":True,"model_turns":0,"publication_writes":0,"status":"prepared"}
    RECORD.write_text(json.dumps(record,indent=2),encoding="utf-8")
    # Recheck no suspended workflow appeared while preparing the candidate.
    current,_,_=snapshot()
    if current!=before: raise RuntimeError("baseline_changed_before_replacement")
    docker("stop","--time","30",OLD);docker("rename",OLD,ROLLBACK)
    try:
        docker("rename",CANDIDATE,OLD);docker("start",OLD)
        last=None
        for _ in range(60):
            try:
                after,_,token=snapshot();break
            except Exception as exc: last=exc;time.sleep(2)
        else: raise RuntimeError("new_viewer_startup_timeout") from last
        # Only the reviewed new catalog entry may be added. Owned flows and all
        # persisted database rows, settings and skill selection remain identical.
        expected_after=json.loads(json.dumps(before))
        if after!=expected_after:
            record["rejected_after"]=after
            if before["database_flows"]["owned"]==after["database_flows"]["owned"]:
                a=before["database_flows"]["template_fields"].get("Hybrid Search RAG",{})
                b=after["database_flows"]["template_fields"].get("Hybrid Search RAG",{})
                print("changed_starter_field_paths:"+json.dumps([k for k in a.keys()|b.keys() if a.get(k)!=b.get(k)]))
            record["changed_sections"]=[k for k in before if before[k]!=after[k]]
            raise RuntimeError("saved_flow_user_or_catalog_mismatch:"+",".join(record["changed_sections"]))
        sid,rev=skill
        from urllib.parse import quote
        bundle=api("/api/v1/laomedo/skills/"+quote(sid,safe="")+"/"+quote(rev,safe=""),token)
        if bundle["skill_id"]!=sid or bundle["revision_id"]!=rev or bundle["tree_hash"]!=rev: raise RuntimeError("selected_skill_identity_mismatch")
        settings=docker("exec",OLD,"/app/.venv/bin/python","-c","from langflow.services.deps import get_settings_service; import json; s=get_settings_service(); print(json.dumps({'workers':s.settings.workers,'worker_timeout':s.settings.worker_timeout,'components_path':s.settings.components_path,'config_dir':s.settings.config_dir,'auto_login':s.auth_settings.AUTO_LOGIN}))")
        settings=json.loads(settings.strip().splitlines()[-1])
        if settings!={"workers":1,"worker_timeout":300,"components_path":["/app/custom_components"],"config_dir":"/app/langflow","auto_login":True}: raise RuntimeError("startup_settings_mismatch")
        record.update(status="activated",after=after,settings=settings,skill_id=sid,skill_revision=rev,file_count=len(bundle["files"]),rollback_container=ROLLBACK)
        RECORD.write_text(json.dumps(record,indent=2),encoding="utf-8")
        print(json.dumps({"status":"activated","saved_flows":len(after["flow_hashes"]),"catalog_preserved_plus_github_issue":True,"auto_login_preserved":True,"skill_files":len(bundle["files"]),"model_turns":0,"rollback_container":ROLLBACK}))
    except Exception:
        try: docker("stop","--time","10",OLD)
        except RuntimeError: pass
        docker("rename",OLD,CANDIDATE);docker("rename",ROLLBACK,OLD);docker("start",OLD)
        record["status"]="rolled_back";RECORD.write_text(json.dumps(record,indent=2),encoding="utf-8")
        raise

if __name__=="__main__":
    try: main()
    except Exception as exc:
        import traceback
        print("failure_locations:"+json.dumps([(f.name,f.lineno) for f in traceback.extract_tb(exc.__traceback__)]))
        print("activation_refused:"+str(exc) if isinstance(exc,RuntimeError) else "activation_refused:"+type(exc).__name__)
        raise SystemExit(1)
