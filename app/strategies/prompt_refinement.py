"""One-shot, capability-grounded refinement of fuzzy text strategies."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .rules import DEFAULT_FEATURE_REGISTRY, FeatureRegistry
from .rules.schema import canonical_json, sha256_text


JsonRequester = Callable[[list[dict[str, str]]], str | Mapping[str, Any]]


@dataclass(frozen=True)
class PromptRefinement:
    refined_spec: dict[str, Any]
    refinement_prompt_sha256: str


def build_refinement_messages(
    raw_prompt: str,
    *,
    registry: FeatureRegistry = DEFAULT_FEATURE_REGISTRY,
) -> list[dict[str, str]]:
    capability_json = canonical_json(registry.capability_catalog())
    system = """你是 NiuOne 文字策略编译助手。你的任务只发生在策略创建阶段：把用户的模糊描述细化为一个可由本地规则引擎执行的 JSON 对象。激活后规则会冻结，运行期不得改写。

严格规则：
1. 只返回 JSON，不返回 Markdown、注释或解释；根对象必须是 strategy_spec。
2. 只能使用 capability_catalog 中的 feature_id、field、参数与 timeframe；禁止生成代码、公式字符串、SQL 或 eval。
3. 必须同时给出 selection、entry、exit 三阶段。若用户只给出买入条件，selection 默认复用买入条件；若卖出条件缺失，必须在 ambiguities 说明且采用保守、明确、可审计的退出条件。
4. 运行期不再调用模型。模糊语义必须在本次细化中转成 compare/all/any/not/crosses_above/crosses_below/for_bars 等确定规则，并把采用的解释写入 assumptions；无法安全量化的内容写入 ambiguities，不能生成 model_judgment 或让模型直接输出买卖动作。
5. KDJ 若用户只说“kdj 数值”，默认解释为 J 值，并把该假设写入 assumptions。
6. A 股固定股数必须是 100 的整数倍；默认 position 为 equity_pct=10、allow_add=false。
7. 默认使用已收盘日线：data_contract={timeframe:"1d",bar_status:"closed",freshness_seconds:129600}；默认缺数据时 hold、冲突时 exit_first、execution_mode 为 simulation。
8. candidate_limit 是完成 selection 过滤后保留的最大候选数，默认 60；max_new_buys_per_cycle 默认 2、最大 5。仓位规则仍受系统单票、总仓位和最低现金硬上限约束。
9. fact 节点仅允许以下运行时事实：account.cash、position.quantity、position.available_shares、position.avg_cost、position.pnl_pct、position.hold_days；它们只能用于 entry/exit，selection 只能使用行情特征。

strategy_spec 必须包含：schema_version=1、strategy_id、name、description、data_contract、rules、position、exit_quantity="all_available"、candidate_limit、max_new_buys_per_cycle、missing_data_policy="hold"、conflict_policy="exit_first"、execution_mode、assumptions、ambiguities。

feature 节点格式：{"type":"feature","feature_id":"technical.kdj","field":"j","parameters":{"n":9,"m1":3,"m2":3},"timeframe":"1d"}
compare 节点格式：{"type":"compare","rule_id":"唯一ID","left":<feature或fact或arithmetic>,"operator":"lt|lte|gt|gte|eq|neq|between","right":数值或 between 的两元素数组}
fact 节点格式：{"type":"fact","field":"position.pnl_pct"}
"""
    user = (
        "capability_catalog="
        + capability_json
        + "\n\n用户原始文字策略：\n"
        + str(raw_prompt or "").strip()
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def parse_refinement_json(value: str | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(value, Mapping):
        payload: Any = dict(value)
    else:
        text = str(value or "").strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        decoder = json.JSONDecoder()
        try:
            payload, _ = decoder.raw_decode(text)
        except json.JSONDecodeError:
            match = re.search(r"\{", text)
            if match is None:
                raise ValueError("模型未返回文字策略 JSON 对象")
            try:
                payload, _ = decoder.raw_decode(text[match.start():])
            except json.JSONDecodeError as exc:
                raise ValueError("模型返回的文字策略 JSON 无法解析") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("模型返回的文字策略必须是 JSON 对象")
    wrapped = payload.get("strategy_spec")
    spec = wrapped if isinstance(wrapped, Mapping) else payload
    if not isinstance(spec, Mapping):
        raise ValueError("模型返回缺少 strategy_spec")
    return dict(spec)


def refine_prompt_once(
    raw_prompt: str,
    requester: JsonRequester,
    *,
    registry: FeatureRegistry = DEFAULT_FEATURE_REGISTRY,
) -> PromptRefinement:
    normalized = str(raw_prompt or "").strip()
    if not normalized:
        raise ValueError("文字策略Prompt不能为空")
    messages = build_refinement_messages(normalized, registry=registry)
    response = requester(messages)
    return PromptRefinement(
        refined_spec=parse_refinement_json(response),
        refinement_prompt_sha256=sha256_text(canonical_json(messages)),
    )
