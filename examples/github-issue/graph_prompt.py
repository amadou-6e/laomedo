"""Native Prompt Template text plus its host-side frozen-task rendering."""
import json

def issue_text(issue):
    return (f"Issue: {issue['url']}\nTitle: {issue['title']}\nState: {issue['state']}\n"
            f"Labels: {', '.join(issue['labels'])}\n\n{issue['body']}")

def prompt_template(config):
    instructions = ("Read the offered skill. This is an issue-operation proposal, not the skill's report-file task. "
        "Do not modify files or GitHub or use git/gh. Propose JSON only with task_outcome success and "
        "operations exactly as supplied. The host will check and apply it after the graph validates it. "
        "Use the output precheck tool before submitting.\nApproved operations:\n" + json.dumps(config['approved']))
    return (instructions.replace('{','{{').replace('}','}}') +
        "\n\nUpdate target:\n{update_issue}\n\nClose target:\n{close_issue}")

def render_task(config):
    return prompt_template(config).format(
        update_issue=issue_text(config['issues'][str(config['approved']['modify']['number'])]),
        close_issue=issue_text(config['issues'][str(config['approved']['close']['number'])]))
