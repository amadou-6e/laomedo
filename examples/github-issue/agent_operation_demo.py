"""Bounded real Codex proposals, then exact host-mediated issue effects.

No stage GitHub credential or native gh edit support is implied by this example.
Run only after approving the concrete campaign configuration.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
from uuid import uuid4
from laomedo.agents.agents.codex.runner import CodexRunner as LocalRunner; from laomedo.agents.agents.base.utils import _private
from experiments.turn_harness import VerificationLocalRunner as LocalRunner
from laomedo.github.issues.gateway import GitHubIssueGateway
from laomedo.github.issues.contract import issue_digest
from laomedo.host.mediation.store import MediationStore; from laomedo.host.mediation.errors import KnownRejected
from laomedo.github.transport.rest.transport import GitHubRestTransport
from laomedo.host.credentials.token.connection import HostTokenConnection

REPOSITORY="ga84jog/laomedo-exp104-disposable-20261007"
SOURCE=Path(__file__).resolve().parent / "demo-workspace"
REGISTRY=Path("C:/Users/amado/AppData/Local/Temp/laomedo-standing-demo-20261012/skill-store")
SKILL={"skill_id":"live-report","revision_id":"sha256:3f6d9c52b1d4ad5777651fc600e1e9a86f8fae7b842438a045bc730c37f46349","tree_hash":"sha256:3f6d9c52b1d4ad5777651fc600e1e9a86f8fae7b842438a045bc730c37f46349"}

def save(path,value):
    pending=path.with_suffix(".pending");pending.write_text(json.dumps(value,indent=2),encoding="utf-8");pending.replace(path)

def connection():
    return HostTokenConnection(connection_id="issue-ops-demo",generation=1,repository=REPOSITORY,
        token_file=Path("C:/CodeWorkspace/agentviz/.env"),key="GH_LAOMEDO",forbidden_mount=SOURCE)

def transport(provider):
    return GitHubRestTransport(REPOSITORY,lambda connection_id=None,connection_generation=None:provider.token("issue-ops-demo",1))

def prepare(root):
    root=_private(root);root.mkdir(exist_ok=True)
    if (root/"config.json").exists():raise ValueError("campaign_already_prepared_no_reset")
    rest=transport(connection())
    issues={str(n):rest(REPOSITORY,"issue_read",{"number":n}) for n in (15,12)}
    if any(i["state"]!="open" for i in issues.values()):raise ValueError("approved_issue_not_open")
    approved={"modify":{"number":15,"changes":{"title":"Filter demo: agent updated",
        "body":issues["15"]["body"]+"\n\n## Agent operation verified\n\nUpdated by the bounded Codex demonstration.\n",
        "labels":sorted(set(issues["15"]["labels"]+["question"]))}},"close":{"number":12}}
    config={"campaign_id":uuid4().hex,"repository":REPOSITORY,"turn_cap":4,"issues":issues,"approved":approved,"skill":SKILL}
    save(root/"config.json",config)
    print(json.dumps({"prepared":True,"turns_used":0,"turn_cap":4,"targets":[15,12],"write_capability_issued":False}))

def accepted_plan(config,record):
    if (record.get("status")!="completed" or record.get("evidence_complete") is not True or
            record.get("completion_basis")!="native_trace_closure" or record.get("snapshot_ready") is not True):
        raise ValueError("native_evidence_not_complete")
    plan=json.loads(record["answer"])
    if plan!={"task_outcome":"success","operations":config["approved"]}:raise ValueError("agent_plan_not_exactly_approved")
    return plan

def propose(root):
    if (root/"binding.json").exists():raise ValueError("campaign_already_entered_publication")
    config=json.loads((root/"config.json").read_text(encoding="utf-8"))
    engine=LocalRunner(root/"runner",REGISTRY,SOURCE,max_model_turns=4,
        lease_service=root/"lease",supervise_containers=True)
    task=("Read the offered live-report skill. This is a proposal-only task, not its report-file success task. "
          "Do not write files, run git/gh or make remote changes. Return JSON only with task_outcome success "
          "and operations exactly as provided. The trusted host will validate and execute them after native "
          "evidence closes. Do not claim you already modified GitHub.\nApproved operations:\n"+json.dumps(config["approved"]))
    record=engine.start({"request_id":str(uuid4()),"task":task,"model":"gpt-6-luna","effort":"low",
                         "skill_ref":config["skill"],"output_retries":0})
    save(root/"agent-result.json",record)
    accepted_plan(config,record)
    print(json.dumps({"agent_proposal_verified":True,"run_id":record["run_id"],"thread_id":record.get("thread_id"),
                      "completion_basis":record["completion_basis"],"github_mutations":0}))

def apply(root):
    config=json.loads((root/"config.json").read_text(encoding="utf-8"));record=json.loads((root/"agent-result.json").read_text(encoding="utf-8"))
    accepted_plan(config,record)
    provider=connection();rest=transport(provider)
    store=MediationStore(root/"issues.sqlite",connection_is_current=provider.current)
    binding_path=root/"binding.json"
    if binding_path.exists():binding=json.loads(binding_path.read_text(encoding="utf-8"))
    else:
        # Both issues must still have their original content before granting.
        for n,issue in config["issues"].items():
            if issue_digest(rest(REPOSITORY,"issue_read",{"number":int(n)}))!=issue_digest(issue):
                raise ValueError("issue_changed_since_campaign_preparation")
        _,token=store.issue(run_id=record["run_id"],invocation_id=config["campaign_id"],repository=REPOSITORY,
            operations={"issue_update"},target_issues={12,15},ttl_seconds=60,
            connection_id="issue-ops-demo",connection_generation=1)
        binding={"token":token,"run_id":record["run_id"],"repository":REPOSITORY};save(binding_path,binding)
    if binding["run_id"]!=record["run_id"]:raise ValueError("campaign_run_rebinding_denied")
    class ExactTransport:
        def __call__(self,repository,operation,payload,**kwargs):
            if operation=="issue_update":
                n=payload["number"];approved=config["approved"]["modify"]["changes"] if n==15 else {"state":"closed"}
                if n not in (12,15) or payload["changes"]!=approved or payload["expected"]!=issue_digest(config["issues"][str(n)]):
                    raise KnownRejected("campaign_effect_not_approved")
            return rest(repository,operation,payload,**kwargs)
    gateway=GitHubIssueGateway({REPOSITORY:ExactTransport()},store,lambda _:binding)
    results={}
    try:
        for action,n in (("modify",15),("close",12)):
            op={"action":action,"request_id":config["campaign_id"]+"-"+str(n),"grant_ref":"campaign"}
            if action=="modify":op["changes"]=config["approved"]["modify"]["changes"]
            result=gateway.execute("https://github.com/"+REPOSITORY,[],"all",n,op);results[str(n)]=result
            save(root/"operation-results.json",results)
            if result["operation"]["status"]!="succeeded":raise ValueError("operation_not_confirmed_stop_without_retry")
    finally:
        store.revoke_run(record["run_id"])
    print(json.dumps({"confirmed":[{"number":int(n),"status":r["operation"]["status"],"state":r["issue"]["state"]} for n,r in results.items()],"capability_revoked":True}))

def main():
    p=argparse.ArgumentParser();p.add_argument("phase",choices=["prepare","propose","apply"]);p.add_argument("--state",type=Path,required=True);args=p.parse_args()
    root=_private(args.state);root.mkdir(exist_ok=True)
    lock=root/"operator.lock"
    lock.touch(exist_ok=False)
    try:{"prepare":prepare,"propose":propose,"apply":apply}[args.phase](root)
    finally:lock.unlink()
if __name__=="__main__":
    try:main()
    except Exception as exc:
        print(json.dumps({"failed":True,"category":str(exc) if type(exc) is ValueError and str(exc).replace('_','').isalnum() else type(exc).__name__}));raise SystemExit(1)
