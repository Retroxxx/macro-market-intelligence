from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from local_ext.core.models import ProviderResult


@dataclass(frozen=True)
class AStockSnapshot:
    results: dict[str, ProviderResult] = field(default_factory=dict)

    @property
    def errors(self) -> dict[str, str]:
        return {
            name: result.error or result.status
            for name, result in self.results.items()
            if result.status not in {"VALID", "VALID_EMPTY", "DISABLED"}
        }

    def as_dict(self) -> dict[str, Any]:
        return {name: result.as_dict() for name, result in self.results.items()}
