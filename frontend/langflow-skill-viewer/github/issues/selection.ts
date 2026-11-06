import type { NodeTemplate as Template } from "../models";

export function nodeKind(type: string) { return type.match(/^ext:[^:]+:([^@]+)@.+$/)?.[1] ?? type; }

export function issueSelection(template: Template) {
  const repository = typeof template?.repository_url?.value === "string" ? template.repository_url.value : "";
  const selected = typeof template?.issue_choice?.value === "string" ? template.issue_choice.value : "";
  const match = selected.match(/^#([1-9][0-9]*) /);
  const number = match ? Number(match[1]) : 0;
  const valid = /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/?$/.test(repository) && Number.isSafeInteger(number) && number > 0;
  return { repository_url: repository, issue_number: valid ? number : 0,
    labels: Array.isArray(template?.labels?.value) ? template.labels.value : [],
    state: typeof template?.state?.value === "string" ? template.state.value : "open",
    url: valid ? repository.replace(/\/$/, "") + "/issues/" + number : "" };
}

export const safeLink = (href: string | undefined) => href && /^https?:\/\//i.test(href) ? href : undefined;
