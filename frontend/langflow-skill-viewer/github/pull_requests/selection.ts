import type { NodeTemplate as Template } from "../models";

export function nodeKind(type: string) { return type.match(/^ext:[^:]+:([^@]+)@.+$/)?.[1] ?? type; }

export function prSelection(template: Template) {
  const repository = typeof template?.repository_url?.value === "string" ? template.repository_url.value : "";
  const selected = typeof template?.pr_choice?.value === "string" ? template.pr_choice.value : "";
  const match = selected.match(/^#([1-9][0-9]*)(?: |$)/);
  const number = match ? Number(match[1]) : 0;
  const valid = /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/?$/.test(repository) && Number.isSafeInteger(number) && number > 0;
  return { repository_url: repository, pr_number: valid ? number : 0,
    account: typeof template?.github_connection?.value === "string" ? template.github_connection.value : "",
    labels: [],
    state: "all",
    url: valid ? repository.replace(/\/$/, "") + "/pull/" + number : "" };
}

export const safeLink = (href: string | undefined) => href && /^https?:\/\//i.test(href) ? href : undefined;
