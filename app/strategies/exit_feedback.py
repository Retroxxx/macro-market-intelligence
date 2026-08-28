"""Bounded, deterministic tuning from durable post-exit observations.

The tuner deliberately excludes structural stops, account risk budgets, and
position caps.  It can only move the ordinary soft-exit, replacement, and
post-exit re-entry thresholds by one pre-declared step per evaluation.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any


EXIT_FEEDBACK_ALGORITHM_VERSION = "niuone-exit-feedback-v1"
EXIT_FEEDBACK_DEFAULT_MIN_SAMPLES = 30
EXIT_FEEDBACK_DEFAULT_MIN_MONTHS = 3
EXIT_FEEDBACK_DEFAULT_COOLDOWN_SAMPLES = 10
EXIT_FEEDBACK_ROLLBACK_MIN_SAMPLES = 10

EXIT_FEEDBACK_DEFAULT_PARAMETERS: dict[str, int | float] = {
    "soft_exit_confirmations": 2,
    "soft_exit_reduce_ratio": 0.5,
    "replacement_priority_margin": 3.0,
    "reentry_volume_ratio": 1.0,
    "reentry_amount_percentile": 60.0,
}

EXIT_FEEDBACK_PARAMETER_BOUNDS: dict[str, tuple[int | float, ...]] = {
    "soft_exit_confirmations": (2, 3),
    "soft_exit_reduce_ratio": (0.25, 0.5),
    "replacement_priority_margin": (3.0, 4.0, 5.0),
    "reentry_volume_ratio": (0.9, 1.0, 1.1),
    "reentry_amount_percentile": (55.0, 60.0, 65.0),
}

SOFT_EXIT_RULES = frozenset({
    "no_progress",
    "profit_protection",
    "sector_retreat",
    "sell_score",
    "position_adjust",
})


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _bounded_value(name: str, value: Any) -> int | float:
    allowed = EXIT_FEEDBACK_PARAMETER_BOUNDS[name]
    numeric = _number(value, float(EXIT_FEEDBACK_DEFAULT_PARAMETERS[name]))
    selected = min(allowed, key=lambda item: abs(float(item) - numeric))
    if isinstance(EXIT_FEEDBACK_DEFAULT_PARAMETERS[name], int):
        return int(selected)
    return float(selected)


def normalize_exit_feedback_parameters(
    value: Mapping[str, Any] | None,
) -> dict[str, int | float]:
    """Return a complete parameter set restricted to the audited grid."""
    source = value if isinstance(value, Mapping) else {}
    return {
        name: _bounded_value(name, source.get(name, default))
        for name, default in EXIT_FEEDBACK_DEFAULT_PARAMETERS.items()
    }


def effective_exit_feedback_parameters(
    policy: Mapping[str, Any] | None,
) -> dict[str, int | float]:
    """Resolve runtime parameters, failing closed to legacy defaults."""
    if not isinstance(policy, Mapping) or not bool(policy.get("enabled")):
        return dict(EXIT_FEEDBACK_DEFAULT_PARAMETERS)
    return normalize_exit_feedback_parameters(
        policy.get("parameters")
        if isinstance(policy.get("parameters"), Mapping)
        else None
    )


def _rate(rows: Sequence[Mapping[str, Any]], field: str) -> float | None:
    values = [int(bool(row.get(field))) for row in rows if row.get(field) is not None]
    return sum(values) / len(values) if values else None


def _average(rows: Sequence[Mapping[str, Any]], field: str) -> float | None:
    values = [
        value
        for row in rows
        if (value := _optional_number(row.get(field))) is not None
    ]
    return sum(values) / len(values) if values else None


def observation_metrics(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Aggregate only fields needed by the deterministic tuning policy."""
    completed = [row for row in rows if int(_number(row.get("completed"), 0)) == 1]
    soft = [
        row for row in completed
        if str(row.get("exit_rule") or "") in SOFT_EXIT_RULES
        and not str(row.get("replacement_target_code") or "").strip()
        and str(row.get("exit_signal") or "") != "niu_priority_replacement"
    ]
    replacements = [
        row for row in completed
        if row.get("replacement_regret") is not None
    ]
    sell_fly_rate = _rate(soft, "sell_fly")
    avoided_loss_rate = _rate(soft, "avoided_loss")
    replacement_regret_rate = _rate(replacements, "replacement_regret")
    regret_score = (
        (sell_fly_rate or 0.0)
        + (replacement_regret_rate or 0.0)
        - (avoided_loss_rate or 0.0)
    )
    return {
        "completed_count": len(completed),
        "soft_exit_count": len(soft),
        "replacement_count": len(replacements),
        "sell_fly_rate": round(sell_fly_rate, 6) if sell_fly_rate is not None else None,
        "avoided_loss_rate": round(avoided_loss_rate, 6) if avoided_loss_rate is not None else None,
        "replacement_regret_rate": (
            round(replacement_regret_rate, 6)
            if replacement_regret_rate is not None else None
        ),
        "avg_close_return_pct": (
            round(value, 6)
            if (value := _average(soft, "close_return_pct")) is not None else None
        ),
        "avg_mae_pct": (
            round(value, 6)
            if (value := _average(soft, "mae_pct")) is not None else None
        ),
        "avg_replacement_regret_pct": (
            round(value, 6)
            if (value := _average(replacements, "replacement_regret_pct")) is not None
            else None
        ),
        "objective_regret_score": round(regret_score, 6),
    }


def observation_span_months(rows: Sequence[Mapping[str, Any]]) -> int:
    dates: list[datetime] = []
    for row in rows:
        try:
            dates.append(datetime.strptime(str(row.get("sell_time") or "")[:10], "%Y-%m-%d"))
        except (TypeError, ValueError):
            continue
    if not dates:
        return 0
    earliest = min(dates)
    latest = max(dates)
    return (latest.year - earliest.year) * 12 + latest.month - earliest.month + 1


def observation_fingerprint(rows: Sequence[Mapping[str, Any]]) -> str:
    material = [
        {
            key: row.get(key)
            for key in (
                "trade_key", "sell_time", "exit_rule", "exit_signal",
                "replacement_target_code", "close_return_pct",
                "mae_pct", "sell_fly", "avoided_loss", "replacement_regret_pct",
                "replacement_regret", "feedback_policy_version",
            )
        }
        for row in rows
        if int(_number(row.get("completed"), 0)) == 1
    ]
    encoded = json.dumps(
        sorted(material, key=lambda item: (str(item.get("sell_time")), str(item.get("trade_key")))),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _move(
    parameters: dict[str, int | float],
    name: str,
    direction: int,
) -> bool:
    allowed = EXIT_FEEDBACK_PARAMETER_BOUNDS[name]
    current = _bounded_value(name, parameters[name])
    index = allowed.index(current)
    target_index = max(0, min(len(allowed) - 1, index + direction))
    if target_index == index:
        return False
    parameters[name] = allowed[target_index]
    return True


def _rollback_needed(
    current_policy: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> tuple[bool, dict[str, Any]]:
    version = int(_number(current_policy.get("version"), 0))
    if version <= 0 or not isinstance(current_policy.get("previous_parameters"), Mapping):
        return False, {}
    version_rows = [
        row for row in rows
        if int(_number(row.get("feedback_policy_version"), 0)) == version
    ]
    metrics = observation_metrics(version_rows)
    if metrics["completed_count"] < EXIT_FEEDBACK_ROLLBACK_MIN_SAMPLES:
        return False, metrics
    baseline = current_policy.get("baseline_metrics")
    if not isinstance(baseline, Mapping):
        return False, metrics
    current_score = _number(metrics.get("objective_regret_score"), 0.0)
    baseline_score = _number(baseline.get("objective_regret_score"), 0.0)
    current_close = _optional_number(metrics.get("avg_close_return_pct"))
    baseline_close = _optional_number(baseline.get("avg_close_return_pct"))
    materially_worse = current_score >= baseline_score + 0.25
    if current_close is not None and baseline_close is not None:
        materially_worse = materially_worse and current_close >= baseline_close + 2.0
    return materially_worse, metrics


def propose_exit_feedback_policy(
    rows: Sequence[Mapping[str, Any]],
    current_policy: Mapping[str, Any] | None,
    *,
    min_samples: int = EXIT_FEEDBACK_DEFAULT_MIN_SAMPLES,
    min_months: int = EXIT_FEEDBACK_DEFAULT_MIN_MONTHS,
    cooldown_samples: int = EXIT_FEEDBACK_DEFAULT_COOLDOWN_SAMPLES,
) -> dict[str, Any]:
    """Propose one auditable policy version or a non-mutating gate result."""
    completed = [row for row in rows if int(_number(row.get("completed"), 0)) == 1]
    metrics = observation_metrics(completed)
    span_months = observation_span_months(completed)
    current = current_policy if isinstance(current_policy, Mapping) else {}
    parameters = normalize_exit_feedback_parameters(
        current.get("parameters") if isinstance(current.get("parameters"), Mapping) else None
    )
    current_count = int(_number(current.get("observation_count"), 0))
    new_count = max(0, len(completed) - current_count)
    base = {
        "algorithm_version": EXIT_FEEDBACK_ALGORITHM_VERSION,
        "parameters": parameters,
        "metrics": metrics,
        "observation_count": len(completed),
        "new_observation_count": new_count,
        "observation_span_months": span_months,
        "source_fingerprint": observation_fingerprint(completed),
        "previous_parameters": dict(parameters),
        "rollback_of": None,
    }
    if len(completed) < max(1, int(min_samples)) or span_months < max(1, int(min_months)):
        return {
            **base,
            "persist": False,
            "status": "learning",
            "action": "sample_gate",
            "reason": (
                f"5日完整样本{len(completed)}/{max(1, int(min_samples))}，"
                f"覆盖月份{span_months}/{max(1, int(min_months))}"
            ),
        }
    if current and new_count < max(1, int(cooldown_samples)):
        return {
            **base,
            "persist": False,
            "status": "cooldown",
            "action": "cooldown",
            "reason": f"新增完整样本{new_count}/{max(1, int(cooldown_samples))}",
        }

    rollback, rollback_metrics = _rollback_needed(current, completed)
    if rollback:
        restored = normalize_exit_feedback_parameters(current.get("previous_parameters"))
        return {
            **base,
            "persist": True,
            "status": "active",
            "parameters": restored,
            "action": "automatic_rollback",
            "reason": "当前版本新增样本的综合后悔分与卖飞收益显著恶化，自动恢复上一参数版本",
            "rollback_of": int(_number(current.get("version"), 0)),
            "rollback_metrics": rollback_metrics,
        }

    component_min = max(10, max(1, int(min_samples)) // 3)
    next_parameters = dict(parameters)
    action = "hold"
    reason = "样本结果未越过调参滞回区间，保持当前参数"
    soft_count = int(metrics.get("soft_exit_count") or 0)
    sell_fly_rate = _optional_number(metrics.get("sell_fly_rate"))
    avoided_rate = _optional_number(metrics.get("avoided_loss_rate"))
    avg_close = _optional_number(metrics.get("avg_close_return_pct"))
    if soft_count >= component_min and sell_fly_rate is not None and avoided_rate is not None:
        if sell_fly_rate - avoided_rate >= 0.15 and (avg_close or 0.0) >= 2.0:
            for name, direction in (
                ("soft_exit_confirmations", 1),
                ("soft_exit_reduce_ratio", -1),
                ("reentry_volume_ratio", -1),
                ("reentry_amount_percentile", -1),
            ):
                if _move(next_parameters, name, direction):
                    action = f"reduce_sell_fly:{name}"
                    reason = "卖飞率显著高于避损率，按一档增加软退出耐心或降低再入确认门槛"
                    break
        elif avoided_rate - sell_fly_rate >= 0.20 and (avg_close or 0.0) <= -2.0:
            for name, direction in (
                ("reentry_amount_percentile", 1),
                ("reentry_volume_ratio", 1),
                ("soft_exit_reduce_ratio", 1),
                ("soft_exit_confirmations", -1),
            ):
                if _move(next_parameters, name, direction):
                    action = f"restore_defense:{name}"
                    reason = "避损贡献显著高于卖飞损失，按一档恢复更防守的退出或再入确认"
                    break

    replacement_count = int(metrics.get("replacement_count") or 0)
    regret_rate = _optional_number(metrics.get("replacement_regret_rate"))
    avg_regret = _optional_number(metrics.get("avg_replacement_regret_pct"))
    if action == "hold" and replacement_count >= component_min and regret_rate is not None:
        if regret_rate >= 0.35 or (avg_regret is not None and avg_regret >= 1.5):
            if _move(next_parameters, "replacement_priority_margin", 1):
                action = "raise_replacement_margin"
                reason = "换仓后悔率或原股相对收益过高，换仓优势门槛上调一档"
        elif regret_rate <= 0.10 and avg_regret is not None and avg_regret <= -1.0:
            if _move(next_parameters, "replacement_priority_margin", -1):
                action = "lower_replacement_margin"
                reason = "换仓持续有效且后悔率低，换仓优势门槛下调一档"

    return {
        **base,
        "persist": True,
        "status": "active",
        "parameters": next_parameters,
        "action": action,
        "reason": reason,
        "baseline_metrics": metrics,
    }


__all__ = [
    "EXIT_FEEDBACK_ALGORITHM_VERSION",
    "EXIT_FEEDBACK_DEFAULT_COOLDOWN_SAMPLES",
    "EXIT_FEEDBACK_DEFAULT_MIN_MONTHS",
    "EXIT_FEEDBACK_DEFAULT_MIN_SAMPLES",
    "EXIT_FEEDBACK_DEFAULT_PARAMETERS",
    "EXIT_FEEDBACK_PARAMETER_BOUNDS",
    "effective_exit_feedback_parameters",
    "normalize_exit_feedback_parameters",
    "observation_metrics",
    "propose_exit_feedback_policy",
]
