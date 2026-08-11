"""Realtime financial-news monitoring backed by NewsNow."""

from .newsnow import (
    DEFAULT_ENDPOINT,
    DEFAULT_SOURCE_IDS,
    NEWSNOW_SOURCE_REGISTRY_REVISION,
    NewsNowClient,
    NewsNowConfig,
    NewsNowConfigurationError,
    NewsNowError,
    NewsNowRequestError,
    NewsNowResponseError,
    NewsNowService,
    SUPPORTED_SOURCES,
    normalize_endpoint,
    parse_source_ids,
    source_options,
)

__all__ = [
    "DEFAULT_ENDPOINT",
    "DEFAULT_SOURCE_IDS",
    "NEWSNOW_SOURCE_REGISTRY_REVISION",
    "NewsNowClient",
    "NewsNowConfig",
    "NewsNowConfigurationError",
    "NewsNowError",
    "NewsNowRequestError",
    "NewsNowResponseError",
    "NewsNowService",
    "SUPPORTED_SOURCES",
    "normalize_endpoint",
    "parse_source_ids",
    "source_options",
]
