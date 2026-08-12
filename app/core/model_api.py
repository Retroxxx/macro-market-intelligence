"""OpenAI-compatible Chat Completions and Responses API helpers.

The project supports multiple gateways whose API shapes are close to, but not
always identical to, OpenAI's APIs.  Keep request construction and response
parsing here so model-using domains do not each grow a slightly different
compatibility implementation.
"""

from __future__ import annotations

import io
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Iterator

from .model_reasoning import (
    chat_reasoning_request_settings,
    normalize_reasoning_effort,
    reasoning_effort_capability,
    resolve_model_reasoning_effort,
)


UrlOpen = Callable[..., Any]


class ModelResponseParseError(ValueError):
    """The model response could not be decoded as supported JSON or SSE."""


@dataclass(frozen=True)
class ModelRequest:
    """A fully constructed model request before authentication is attached."""

    endpoint: str
    payload: dict[str, Any]
    api_mode: str


@dataclass(frozen=True)
class ParsedModelResponse:
    """Visible model text plus compact, non-sensitive response metadata."""

    content: str
    detail: str
    data: dict[str, Any] | None = None


def normalize_api_mode(mode: str | None) -> str:
    normalized = str(mode or "auto").strip().lower().replace("-", "_")
    if normalized in {"responses", "response"}:
        return "responses"
    if normalized in {"chat", "chat_completions", "chat_completion"}:
        return "chat"
    return "auto"


def uses_responses_api(
    mode: str | None,
    model: str,
    *,
    web_search: bool = False,
) -> bool:
    """Choose an API without changing legacy models in zero-config installs."""

    normalized = normalize_api_mode(mode)
    if normalized == "responses":
        return True
    if normalized == "chat":
        return False

    model_name = str(model or "").strip().lower()
    capability = reasoning_effort_capability(model_name)
    if (
        model_name.startswith(("grok-4.3", "grok-4.5"))
        or model_name == "grok-latest"
        or model_name in {"mimo-v2.5", "mimo-v2.5-pro"}
        or (capability is not None and capability.key in {"qwen-3.8-max", "qwen-responses"})
    ):
        return True
    # OpenAI-compatible GPT-5 search tools are exposed through Responses.  Do
    # not switch unknown legacy aliases automatically because some gateways
    # implement their own search-capable Chat endpoint.
    return web_search and model_name.startswith("gpt-5")


def _supports_responses_output_limit(model: str) -> bool:
    """Return whether the known upstream accepts ``max_output_tokens``.

    Some GPT-5.6 gateway aliases reject the otherwise standard Responses
    parameter.  Unknown providers still receive it first and have a guarded
    400 fallback in :func:`request_model`.
    """

    return not str(model or "").strip().lower().startswith("gpt-5.6")


def _uses_chat_completion_output_limit(model: str) -> bool:
    """Return whether Chat uses ``max_completion_tokens`` for this model."""

    model_name = str(model or "").strip().lower()
    return (
        model_name in {"mimo-v2.5", "mimo-v2.5-pro"}
        or re.fullmatch(r"minimax-m(?:3|2(?:\.(?:1|5|7)(?:-highspeed)?)?)", model_name)
        is not None
    )


def build_model_request(
    base_url: str,
    model: str,
    messages: list[dict[str, Any]],
    *,
    max_tokens: int | None = None,
    api_mode: str | None = "auto",
    tools: Iterable[dict[str, Any]] | None = None,
    reasoning: dict[str, Any] | None = None,
    reasoning_effort: str | None = None,
    stream: bool = False,
    extra_payload: dict[str, Any] | None = None,
) -> ModelRequest:
    """Build a Chat or Responses request with mode-appropriate parameters."""

    tool_list = [dict(tool) for tool in (tools or [])]
    has_web_search = any(
        str(tool.get("type") or "").strip().lower() == "web_search"
        for tool in tool_list
    )
    use_responses = uses_responses_api(
        api_mode,
        model,
        web_search=has_web_search,
    )
    payload = dict(extra_payload or {})
    payload["model"] = model

    if use_responses:
        for legacy_key in ("messages", "max_tokens", "max_completion_tokens"):
            payload.pop(legacy_key, None)
        payload["input"] = messages
        if tool_list:
            payload["tools"] = tool_list
        else:
            payload.pop("tools", None)
        payload.pop("reasoning_effort", None)
        reasoning_payload = (
            dict(payload.get("reasoning"))
            if isinstance(payload.get("reasoning"), dict)
            else {}
        )
        if reasoning:
            reasoning_payload.update(reasoning)
        if reasoning_effort is not None:
            normalized_effort = resolve_model_reasoning_effort(
                model,
                reasoning_effort,
            ).configured_effort
            if normalized_effort:
                reasoning_payload["effort"] = normalized_effort
            else:
                reasoning_payload.pop("effort", None)
        elif "effort" in reasoning_payload:
            reasoning_payload["effort"] = resolve_model_reasoning_effort(
                model,
                reasoning_payload["effort"],
            ).configured_effort
        if reasoning_payload:
            payload["reasoning"] = reasoning_payload
        else:
            payload.pop("reasoning", None)
        if max_tokens and max_tokens > 0 and _supports_responses_output_limit(model):
            payload["max_output_tokens"] = int(max_tokens)
        else:
            payload.pop("max_output_tokens", None)
        payload["stream"] = bool(stream)
        return ModelRequest(
            endpoint=base_url.rstrip("/") + "/responses",
            payload=payload,
            api_mode="responses",
        )

    raw_reasoning_effort = (
        reasoning_effort
        if reasoning_effort is not None
        else payload.get("reasoning_effort")
    )
    effort_resolution = resolve_model_reasoning_effort(
        model,
        raw_reasoning_effort,
    )
    normalized_effort = effort_resolution.configured_effort
    for responses_key in ("input", "max_output_tokens", "reasoning"):
        payload.pop(responses_key, None)
    payload["messages"] = messages
    if max_tokens and max_tokens > 0:
        if _uses_chat_completion_output_limit(model):
            payload.pop("max_tokens", None)
            payload["max_completion_tokens"] = int(max_tokens)
        else:
            payload["max_tokens"] = int(max_tokens)
            payload.pop("max_completion_tokens", None)
    else:
        payload.pop("max_tokens", None)
        payload.pop("max_completion_tokens", None)
    payload.pop("reasoning_effort", None)
    if normalized_effort:
        payload.update(chat_reasoning_request_settings(model, normalized_effort))
    capability = reasoning_effort_capability(model)
    if capability is not None and capability.key in {"minimax-m3", "minimax-m2"}:
        # MiniMax Chat otherwise embeds <think> content in the visible answer.
        # This flag only separates output fields; it does not alter reasoning.
        payload.setdefault("reasoning_split", True)
    if stream or "stream" in payload:
        payload["stream"] = bool(stream)
    return ModelRequest(
        endpoint=base_url.rstrip("/") + "/chat/completions",
        payload=payload,
        api_mode="chat",
    )


def responses_output_text(data: dict[str, Any]) -> str:
    direct = _content_text(data.get("output_text"))
    if direct.strip():
        return direct.strip()
    parts: list[str] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            if content.get("type") in {"output_text", "text"}:
                text = _content_text(content.get("text"))
                if text:
                    parts.append(text)
    return "\n".join(parts).strip()


def _content_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, dict):
                    text = text.get("value") or text.get("text")
                if text:
                    parts.append(str(text))
        return "".join(parts)
    if isinstance(value, dict):
        nested = value.get("value") or value.get("text")
        return str(nested or "")
    return ""


def _parse_json_response(data: dict[str, Any]) -> ParsedModelResponse:
    if "choices" in data:
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = _content_text(message.get("content"))
        detail: list[str] = []
        if choice.get("finish_reason"):
            detail.append(f"finish_reason={choice.get('finish_reason')}")
        if data.get("usage"):
            detail.append(f"usage={data.get('usage')}")
        return ParsedModelResponse(content, ", ".join(detail), data)

    content = responses_output_text(data)
    detail = []
    if data.get("status"):
        detail.append(f"status={data.get('status')}")
    if data.get("usage"):
        detail.append(f"usage={data.get('usage')}")
    return ParsedModelResponse(content, ", ".join(detail), data)


def _parse_sse_response(raw: str) -> ParsedModelResponse:
    chat_parts: list[str] = []
    response_parts: list[str] = []
    response_done_text = ""
    finish_reasons: list[str] = []
    usage: Any = None
    completed_response: dict[str, Any] | None = None
    last_data: dict[str, Any] | None = None
    chunks = 0
    search_events = 0

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped.startswith("data:"):
            continue
        chunk = stripped[5:].strip()
        if not chunk or chunk == "[DONE]":
            continue
        try:
            obj = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        chunks += 1
        last_data = obj
        if obj.get("usage"):
            usage = obj.get("usage")

        choice = (obj.get("choices") or [{}])[0]
        if isinstance(choice, dict):
            if choice.get("finish_reason"):
                finish_reasons.append(str(choice.get("finish_reason")))
            delta = choice.get("delta") or {}
            message = choice.get("message") or {}
            piece = _content_text(delta.get("content")) or _content_text(message.get("content"))
            if piece:
                chat_parts.append(piece)

        event_type = str(obj.get("type") or "")
        if ".web_search_call." in event_type or ".x_search_call." in event_type:
            search_events += 1
        if event_type == "response.output_text.delta":
            piece = _content_text(obj.get("delta"))
            if piece:
                response_parts.append(piece)
        elif event_type == "response.output_text.done":
            response_done_text = _content_text(obj.get("text"))
        elif event_type == "response.completed" and isinstance(obj.get("response"), dict):
            completed_response = obj["response"]
            if completed_response.get("usage"):
                usage = completed_response.get("usage")

    content = "".join(response_parts) or response_done_text or "".join(chat_parts)
    if not content and completed_response:
        content = responses_output_text(completed_response)

    detail = [f"sse_chunks={chunks}"]
    if finish_reasons:
        detail.append(f"finish_reason={finish_reasons[-1]}")
    if search_events:
        detail.append(f"search_events={search_events}")
    if usage:
        detail.append(f"usage={usage}")
    return ParsedModelResponse(content, ", ".join(detail), completed_response or last_data)


def parse_model_response(raw: str, content_type: str = "") -> ParsedModelResponse:
    """Parse Chat/Responses JSON or SSE, including gateways that force SSE."""

    if not (raw or "").strip():
        raise ModelResponseParseError("empty model response")
    looks_like_sse = "text/event-stream" in str(content_type or "").lower() or any(
        line.lstrip().startswith("data:") for line in raw.splitlines()
    )
    if looks_like_sse:
        return _parse_sse_response(raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ModelResponseParseError("model returned neither JSON nor SSE") from exc
    if not isinstance(data, dict):
        raise ModelResponseParseError("model returned a non-object JSON response")
    return _parse_json_response(data)


def _response_content_type(response: Any) -> str:
    headers = getattr(response, "headers", None)
    if headers is None:
        return ""
    try:
        return str(headers.get("Content-Type") or "")
    except Exception:
        return ""


def _request_once(
    request: ModelRequest,
    api_key: str,
    *,
    timeout: float,
    opener: UrlOpen,
    ssl_context: Any = None,
) -> ParsedModelResponse:
    req = urllib.request.Request(
        request.endpoint,
        data=json.dumps(request.payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "NiuOne/1.0",
        },
    )
    kwargs: dict[str, Any] = {"timeout": timeout}
    if ssl_context is not None:
        kwargs["context"] = ssl_context
    with opener(req, **kwargs) as response:
        content_type = _response_content_type(response)
        raw = response.read().decode("utf-8", "ignore")
    return parse_model_response(raw, content_type)


def _stream_response_text(response: Any) -> Iterator[str]:
    """Yield visible text from an upstream JSON or SSE model response."""

    content_type = _response_content_type(response)
    if "text/event-stream" not in content_type.lower():
        raw = response.read().decode("utf-8", "ignore")
        parsed = parse_model_response(raw, content_type)
        if parsed.content:
            yield parsed.content
        return

    emitted = False
    while True:
        raw_line = response.readline()
        if not raw_line:
            break
        if isinstance(raw_line, bytes):
            line = raw_line.decode("utf-8", "ignore")
        else:
            line = str(raw_line)
        stripped = line.strip()
        if not stripped.startswith("data:"):
            continue
        payload = stripped[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue

        piece = ""
        choice = (obj.get("choices") or [{}])[0]
        if isinstance(choice, dict):
            delta = choice.get("delta") or {}
            message = choice.get("message") or {}
            if isinstance(delta, dict):
                piece = _content_text(delta.get("content"))
            if not piece and isinstance(message, dict):
                piece = _content_text(message.get("content"))

        event_type = str(obj.get("type") or "")
        if event_type == "response.output_text.delta":
            piece = _content_text(obj.get("delta"))
        elif event_type == "response.output_text.done" and not emitted:
            piece = _content_text(obj.get("text"))
        elif (
            event_type == "response.completed"
            and not emitted
            and isinstance(obj.get("response"), dict)
        ):
            piece = responses_output_text(obj["response"])

        if piece:
            emitted = True
            yield piece


def _stream_once(
    request: ModelRequest,
    api_key: str,
    *,
    timeout: float,
    opener: UrlOpen,
    ssl_context: Any = None,
) -> Iterator[str]:
    req = urllib.request.Request(
        request.endpoint,
        data=json.dumps(request.payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
            "Accept": "text/event-stream, application/json",
            "User-Agent": "NiuOne/1.0",
        },
    )
    kwargs: dict[str, Any] = {"timeout": timeout}
    if ssl_context is not None:
        kwargs["context"] = ssl_context
    with opener(req, **kwargs) as response:
        yield from _stream_response_text(response)


def _unsupported_output_limit(error_body: str) -> bool:
    text = str(error_body or "").lower()
    if "max_output_tokens" not in text:
        return False
    unsupported_patterns = (
        r"unsupported\s+(?:request\s+)?(?:parameter|argument|field)",
        r"(?:unknown|unrecognized)\s+(?:request\s+)?(?:parameter|argument|field)",
        r"(?:parameter|argument|field)[^\n]{0,120}\bnot\s+supported\b",
        r"max_output_tokens[^\n]{0,120}\bnot\s+supported\b",
        r"max_output_tokens(?:[\"'`]|[\s:,-]){0,8}(?:is\s+)?unsupported\b",
        (
            r"\b(?:does|do)\s+not\s+support\s+"
            r"(?:the\s+)?(?:parameter\s+)?[\"'`]?max_output_tokens\b"
        ),
    )
    return any(re.search(pattern, text) for pattern in unsupported_patterns)


def request_model(
    request: ModelRequest,
    api_key: str,
    *,
    timeout: float,
    opener: UrlOpen = urllib.request.urlopen,
    ssl_context: Any = None,
) -> ParsedModelResponse:
    """Send one request with a narrow Responses token-parameter fallback."""

    try:
        return _request_once(
            request,
            api_key,
            timeout=timeout,
            opener=opener,
            ssl_context=ssl_context,
        )
    except urllib.error.HTTPError as exc:
        if exc.code != 400 or "max_output_tokens" not in request.payload:
            raise
        try:
            error_body = exc.read().decode("utf-8", "ignore")
        except Exception:
            error_body = ""
        if not _unsupported_output_limit(error_body):
            # Preserve the response body for module-specific diagnostics after
            # inspecting it for the narrow compatibility fallback.
            exc.close()
            raise urllib.error.HTTPError(
                exc.url,
                exc.code,
                exc.msg,
                exc.hdrs,
                io.BytesIO(error_body.encode("utf-8")),
            ) from exc
        exc.close()
        fallback_payload = dict(request.payload)
        fallback_payload.pop("max_output_tokens", None)
        fallback = ModelRequest(request.endpoint, fallback_payload, request.api_mode)
        return _request_once(
            fallback,
            api_key,
            timeout=timeout,
            opener=opener,
            ssl_context=ssl_context,
        )


def stream_model_response(
    request: ModelRequest,
    api_key: str,
    *,
    timeout: float,
    opener: UrlOpen = urllib.request.urlopen,
    ssl_context: Any = None,
) -> Iterator[str]:
    """Stream visible model text with the same narrow compatibility fallback."""

    try:
        yield from _stream_once(
            request,
            api_key,
            timeout=timeout,
            opener=opener,
            ssl_context=ssl_context,
        )
    except urllib.error.HTTPError as exc:
        if exc.code != 400 or "max_output_tokens" not in request.payload:
            raise
        try:
            error_body = exc.read().decode("utf-8", "ignore")
        except Exception:
            error_body = ""
        if not _unsupported_output_limit(error_body):
            exc.close()
            raise urllib.error.HTTPError(
                exc.url,
                exc.code,
                exc.msg,
                exc.hdrs,
                io.BytesIO(error_body.encode("utf-8")),
            ) from exc
        exc.close()
        fallback_payload = dict(request.payload)
        fallback_payload.pop("max_output_tokens", None)
        fallback = ModelRequest(request.endpoint, fallback_payload, request.api_mode)
        yield from _stream_once(
            fallback,
            api_key,
            timeout=timeout,
            opener=opener,
            ssl_context=ssl_context,
        )
