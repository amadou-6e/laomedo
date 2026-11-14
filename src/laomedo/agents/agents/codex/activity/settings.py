"""Pinned historical Codex API-equivalent pricing evidence, not current invoices."""

CATALOG_DATE = "2026-10-15"
RATES = {
    "gpt-6-luna": ("0.1", "0.01", "0.5"),
    "gpt-6.1-sol": ("2", "0.1", "10"),
}
SOURCES = {
    model: {
        "url": f"https://developers.openai.com/api/docs/models/{model}",
        "fetched_at": "2026-10-15",
        "tier": "Standard",
        "currency": "USD",
    }
    for model in RATES
}
