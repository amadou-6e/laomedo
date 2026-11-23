export function nativeStatus(text: string) {
  const fields = new Map<string, string>();
  const limits: { name: string; value: string; remaining: number | null }[] = [];
  for (const line of text.split(/\r?\n/)) {
    const match = line.trim().match(/^\*\*([^*]+):\*\*\s*(.*?)\s*$/);
    if (!match) continue;
    const name = match[1];
    const value = match[2].replace(/`/g, "");
    fields.set(name.toLowerCase(), value);
    if (/limit$/i.test(name)) {
      const percent = value.match(/^(\d+(?:\.\d+)?)% left\b/);
      const number = percent ? Number(percent[1]) : null;
      limits.push({ name: name.replace(/^codex\s+/i, ""), value,
        remaining: number !== null && number >= 0 && number <= 100 ? number : null });
    }
  }
  return { fields, limits };
}
