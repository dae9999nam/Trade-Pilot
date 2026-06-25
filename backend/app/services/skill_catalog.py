from functools import lru_cache
from importlib import resources

SKILL_ORDER = [
    "index.md",
    "system_status_and_config.md",
    "market_snapshot.md",
    "ai_trade_decision.md",
    "risk_guardrails.md",
    "order_management.md",
    "portfolio_positions.md",
    "account_reconciliation.md",
    "decision_history.md",
    "admin_dashboard.md",
    "auth_admin_session.md",
    "broker_adapters.md",
    "creon_gateway.md",
]


@lru_cache(maxsize=1)
def load_skill_catalog() -> str:
    skill_dir = resources.files("app.skills")
    ordered_names = [name for name in SKILL_ORDER if (skill_dir / name).is_file()]
    remaining_names = sorted(
        item.name
        for item in skill_dir.iterdir()
        if item.name.endswith(".md") and item.name not in ordered_names
    )

    skill_cards: list[str] = []
    for name in [*ordered_names, *remaining_names]:
        text = (skill_dir / name).read_text(encoding="utf-8").strip()
        skill_cards.append(f'<skill_card name="{name}">\n{text}\n</skill_card>')

    return "\n\n".join(skill_cards)
