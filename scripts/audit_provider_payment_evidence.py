"""Opt-in, bounded, READ ONLY provider invoice evidence audit.

Usage (no provider network call):
  python -m scripts.audit_provider_payment_evidence --provider tbank --limit 3

Usage (status inquiries ONLY; no create/credit/settle/refund):
  python -m scripts.audit_provider_payment_evidence --provider tbank --limit 3 --probe

The output contains aggregated status *observations*, never invoice IDs,
buyer identifiers, amounts, request URLs, or raw provider errors. Reports are
not evidence permitting automatic settlement. Human review is still required.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter

from sqlalchemy import text

from app.db.session import SessionFactory, engine
from app.services.payment_provider_evidence import ProviderEvidenceProbe


def args_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider", required=True,
        choices=sorted(ProviderEvidenceProbe.SUPPORTED_PROVIDERS),
    )
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--older-than-days", type=int, default=7)
    parser.add_argument(
        "--probe", action="store_true",
        help="Explicitly allow bounded provider status inquiries (never mutations)",
    )
    return parser


async def main() -> None:
    args = args_parser().parse_args()
    if not 1 <= args.limit <= ProviderEvidenceProbe.MAX_LOOKUPS:
        raise SystemExit("limit must be between 1 and 5")
    if not 1 <= args.older_than_days <= 3650:
        raise SystemExit("older-than-days must be between 1 and 3650")

    try:
        # Read local evidence in a transaction that rejects writes even if a
        # future refactor accidentally introduces a mutating SQL statement.
        async with SessionFactory() as session:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            candidates = await ProviderEvidenceProbe.candidates(
                session,
                provider=args.provider,
                limit=args.limit,
                older_than_days=args.older_than_days,
            )
            await session.rollback()

        outcomes: Counter[str] = Counter()
        if args.probe:
            for candidate in candidates:
                outcomes[await ProviderEvidenceProbe.probe(candidate)] += 1

        print(json.dumps({
            "provider": args.provider,
            "mode": "provider_status_inquiry" if args.probe else "local_read_only",
            "older_than_days": args.older_than_days,
            "max_items": args.limit,
            "selected": len(candidates),
            "outcome_counts": dict(sorted(outcomes.items())),
            "evidence_required": True,
            "automatic_settlement_allowed": False,
            "changes_to_payments_or_wallets": False,
            "missing_provider_id_records_excluded": True,
        }, sort_keys=True))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
