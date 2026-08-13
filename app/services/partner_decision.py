from __future__ import annotations

ALLOWED = {
    "pending": {"approved", "rejected"},
    "approved": {"suspended"},
    "suspended": {"approved", "rejected"},
    "rejected": set(),
}


class PartnerDecisionService:
    @staticmethod
    def validate(current: str, target: str) -> None:
        if target not in ALLOWED.get(current, set()):
            raise ValueError(f"Invalid partner transition: {current} -> {target}")
