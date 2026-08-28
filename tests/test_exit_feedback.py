#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
COMPAT = APP / "compat"
sys.path.insert(0, str(APP))
sys.path.insert(0, str(COMPAT))

from strategies.exit_feedback import (  # noqa: E402
    EXIT_FEEDBACK_DEFAULT_PARAMETERS,
    effective_exit_feedback_parameters,
    propose_exit_feedback_policy,
)


def feedback_rows(
    count: int,
    *,
    sell_fly: int = 0,
    avoided_loss: int = 0,
    close_return_pct: float = 0.0,
    exit_rule: str = "no_progress",
    replacement_regret: int | None = None,
    replacement_regret_pct: float | None = None,
    policy_version: int = 0,
):
    rows = []
    for index in range(count):
        month = 1 + index % 3
        day = 1 + index // 3
        rows.append({
            "trade_key": f"trade-{index}",
            "sell_time": f"2026-{month:02d}-{day:02d} 14:45:00",
            "exit_rule": exit_rule,
            "close_return_pct": close_return_pct,
            "mae_pct": -5.0 if avoided_loss else -1.0,
            "sell_fly": sell_fly,
            "avoided_loss": avoided_loss,
            "replacement_regret": replacement_regret,
            "replacement_regret_pct": replacement_regret_pct,
            "feedback_policy_version": policy_version,
            "completed": 1,
        })
    return rows


class ExitFeedbackPolicyTests(unittest.TestCase):
    def test_defaults_fail_closed_when_policy_is_disabled(self):
        parameters = effective_exit_feedback_parameters({
            "enabled": False,
            "parameters": {
                "soft_exit_confirmations": 3,
                "replacement_priority_margin": 5,
            },
        })

        self.assertEqual(parameters, EXIT_FEEDBACK_DEFAULT_PARAMETERS)

    def test_cross_month_sample_gate_blocks_early_tuning(self):
        proposal = propose_exit_feedback_policy(
            feedback_rows(19, sell_fly=1, close_return_pct=5.0),
            None,
            min_samples=20,
            min_months=3,
        )

        self.assertFalse(proposal["persist"])
        self.assertEqual(proposal["status"], "learning")
        self.assertEqual(
            proposal["parameters"]["soft_exit_confirmations"],
            2,
        )

    def test_high_sell_fly_rate_moves_only_one_patience_step(self):
        proposal = propose_exit_feedback_policy(
            feedback_rows(30, sell_fly=1, close_return_pct=5.0),
            None,
            min_samples=30,
            min_months=3,
        )

        self.assertTrue(proposal["persist"])
        self.assertEqual(
            proposal["parameters"]["soft_exit_confirmations"],
            3,
        )
        self.assertEqual(proposal["parameters"]["soft_exit_reduce_ratio"], 0.5)
        self.assertEqual(proposal["action"], "reduce_sell_fly:soft_exit_confirmations")

    def test_replacement_regret_raises_margin_after_component_gate(self):
        proposal = propose_exit_feedback_policy(
            feedback_rows(
                30,
                exit_rule="other_exit",
                replacement_regret=1,
                replacement_regret_pct=3.0,
            ),
            None,
            min_samples=30,
            min_months=3,
        )

        self.assertEqual(proposal["action"], "raise_replacement_margin")
        self.assertEqual(
            proposal["parameters"]["replacement_priority_margin"],
            4.0,
        )

    def test_cooldown_requires_new_completed_observations(self):
        current = {
            "version": 1,
            "observation_count": 30,
            "parameters": EXIT_FEEDBACK_DEFAULT_PARAMETERS,
        }
        proposal = propose_exit_feedback_policy(
            feedback_rows(34, sell_fly=1, close_return_pct=5.0),
            current,
            min_samples=30,
            min_months=3,
            cooldown_samples=5,
        )

        self.assertFalse(proposal["persist"])
        self.assertEqual(proposal["status"], "cooldown")

    def test_materially_worse_version_rolls_back_previous_parameters(self):
        prior = dict(EXIT_FEEDBACK_DEFAULT_PARAMETERS)
        current_parameters = {**prior, "soft_exit_confirmations": 3}
        old_rows = feedback_rows(20)
        new_rows = feedback_rows(
            10,
            sell_fly=1,
            close_return_pct=5.0,
            policy_version=2,
        )
        for index, row in enumerate(new_rows, start=20):
            row["trade_key"] = f"trade-{index}"
        current = {
            "version": 2,
            "observation_count": 20,
            "parameters": current_parameters,
            "previous_parameters": prior,
            "baseline_metrics": {
                "objective_regret_score": 0.0,
                "avg_close_return_pct": 0.0,
            },
        }

        proposal = propose_exit_feedback_policy(
            [*old_rows, *new_rows],
            current,
            min_samples=30,
            min_months=3,
            cooldown_samples=10,
        )

        self.assertEqual(proposal["action"], "automatic_rollback")
        self.assertEqual(proposal["rollback_of"], 2)
        self.assertEqual(proposal["parameters"], prior)


if __name__ == "__main__":
    unittest.main()
