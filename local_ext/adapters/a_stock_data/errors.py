from __future__ import annotations


class AStockDataError(Exception):
    """Base error for the bounded supplemental provider boundary."""


class AStockHTTPError(AStockDataError):
    def __init__(self, status: int) -> None:
        super().__init__(f"http_{status}")
        self.status = status


class AStockStaleData(AStockDataError):
    def __init__(self, payload: dict[str, object], age_seconds: float, cause: Exception) -> None:
        super().__init__(f"stale_data:{type(cause).__name__}")
        self.payload = payload
        self.age_seconds = age_seconds


class AStockSchemaError(AStockDataError):
    pass
