#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
sys.path.insert(0, str(APP))

from strategies.prompt_refinement import (  # noqa: E402
    build_refinement_messages,
    parse_refinement_json,
    refine_prompt_once,
)

from test_prompt_rule_engine import kdj_spec  # noqa: E402


class PromptRefinementTests(unittest.TestCase):
    def test_messages_ground_model_in_registered_capabilities(self):
        messages = build_refinement_messages("kdj<0买入，kdj>15卖出")

        self.assertEqual([item["role"] for item in messages], ["system", "user"])
        self.assertIn('"feature_id":"technical.kdj"', messages[1]["content"])
        self.assertIn("激活后规则会冻结", messages[0]["content"])
        self.assertIn("禁止生成代码", messages[0]["content"])

    def test_refinement_accepts_wrapped_json_and_is_called_once(self):
        calls = []

        def requester(messages):
            calls.append(messages)
            return {"strategy_spec": kdj_spec()}

        result = refine_prompt_once("kdj<0买入，kdj>15卖出", requester)

        self.assertEqual(len(calls), 1)
        self.assertEqual(result.refined_spec["strategy_id"], "kdj-rebound")
        self.assertEqual(len(result.refinement_prompt_sha256), 64)

    def test_parser_accepts_fenced_json_but_rejects_non_object(self):
        parsed = parse_refinement_json(
            "```json\n" + '{"strategy_spec":{"schema_version":1}}' + "\n```"
        )
        self.assertEqual(parsed, {"schema_version": 1})
        with self.assertRaisesRegex(ValueError, "JSON 对象"):
            parse_refinement_json("[1, 2, 3]")


if __name__ == "__main__":
    unittest.main()
