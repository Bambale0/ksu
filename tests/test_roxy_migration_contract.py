from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_rox_denomination_migration_scales_all_persisted_spend_units() -> None:
    migration = (
        ROOT / "alembic" / "versions" / "0023_roxy_one_ruble_denomination.py"
    ).read_text(encoding="utf-8")
    for token in (
        "UPDATE wallets SET balance = balance *",
        "UPDATE wallet_transactions SET amount = amount *",
        "UPDATE promo_codes SET reward_amount = reward_amount *",
        "UPDATE generations SET cost_rox = cost_rox *",
        "UPDATE payments SET rox_amount = rox_amount *",
        "UPDATE payment_reversals SET credits = credits *",
        "UPDATE prompt_tool_tasks SET cost_credits = cost_credits *",
        "UPDATE batch_generation_jobs SET initial_cost_rox = initial_cost_rox *",
        "prompt_costs",
    ):
        assert token in migration


def test_rox_denomination_does_not_scale_withdrawable_ruble_accounting() -> None:
    migration = (
        ROOT / "alembic" / "versions" / "0023_roxy_one_ruble_denomination.py"
    ).read_text(encoding="utf-8")
    assert "UPDATE referral_rewards SET amount" not in migration
    assert "UPDATE partner_withdrawals SET amount" not in migration
    assert "UPDATE referral_reward_reversals SET amount" not in migration
