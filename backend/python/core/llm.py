from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

import httpx

from .config import settings

TRANSIENT_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class LLMError(RuntimeError):
    pass


class TransientLLMError(LLMError):
    pass


def provider_order() -> list[str]:
    order: list[str] = []
    if settings.groq_api_key:
        order.append("groq")
    if settings.gemini_api_key:
        order.append("gemini")
    if settings.fallback_provider == "ollama" or not order:
        order.append("ollama")
    order.append("echo")
    return order


async def _groq(messages: list[dict[str, str]], **_: Any) -> str:
    payload = {"model": settings.groq_model, "messages": messages, "temperature": 0.3}
    async with httpx.AsyncClient(timeout=settings.llm_timeout) as client:
        res = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            json=payload,
        )
    _raise_for_status(res, "groq")
    return res.json()["choices"][0]["message"]["content"].strip()


async def _gemini(messages: list[dict[str, str]], **_: Any) -> str:
    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    contents = [
        {"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]}
        for m in messages
        if m["role"] != "system"
    ]
    payload = {"contents": contents, "generationConfig": {"temperature": 0.3}}
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )
    async with httpx.AsyncClient(timeout=settings.llm_timeout) as client:
        res = await client.post(
            url,
            headers={"x-goog-api-key": settings.gemini_api_key},
            json=payload,
        )
    _raise_for_status(res, "gemini")
    data = res.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError) as exc:
        raise LLMError(f"gemini returned unexpected payload: {data}") from exc


async def _ollama(messages: list[dict[str, str]], **_: Any) -> str:
    model = await resolve_ollama_model()
    if model is None:
        raise LLMError("ollama has no usable models")
    payload = {"model": model, "messages": messages, "stream": False}
    async with httpx.AsyncClient(timeout=settings.ollama_timeout) as client:
        res = await client.post(f"{settings.ollama_url.rstrip('/')}/api/chat", json=payload)
    _raise_for_status(res, "ollama")
    return res.json().get("message", {}).get("content", "").strip()


async def _echo(messages: list[dict[str, str]], **_: Any) -> str:
    last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    return (
        "I am running without a configured LLM provider. "
        f"To activate full reasoning set GROQ_API_KEY or GEMINI_API_KEY. "
        f"Received: {last[:400]}"
    )


PROVIDERS = {"groq": _groq, "gemini": _gemini, "ollama": _ollama, "echo": _echo}


def _raise_for_status(res: httpx.Response, provider: str) -> None:
    if res.status_code < 400:
        return
    body = res.text[:300]
    if res.status_code in TRANSIENT_STATUS:
        raise TransientLLMError(f"{provider} {res.status_code}: {body}")
    raise LLMError(f"{provider} {res.status_code}: {body}")


_OLLAMA_MODEL: dict[str, str] = {}


async def resolve_ollama_model() -> str | None:
    cached = _OLLAMA_MODEL.get("name")
    if cached:
        return cached
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            res = await client.get(f"{settings.ollama_url.rstrip('/')}/api/tags")
        if res.status_code != 200:
            return None
        names = [m.get("name", "") for m in res.json().get("models", []) if m.get("name")]
    except (httpx.HTTPError, KeyError, ValueError):
        return None
    if not names:
        return None
    wanted = settings.ollama_model
    for name in names:
        if name == wanted or name.split(":")[0] == wanted.split(":")[0]:
            _OLLAMA_MODEL["name"] = name
            return name
    _OLLAMA_MODEL["name"] = names[0]
    return names[0]


async def probe_ollama() -> bool:
    return await resolve_ollama_model() is not None


async def chat(
    messages: list[dict[str, str]],
    providers: list[str] | None = None,
    retries: int | None = None,
) -> str:
    order = providers or provider_order()
    attempts = settings.llm_max_retries if retries is None else retries
    errors: list[str] = []

    for provider in order:
        handler = PROVIDERS.get(provider)
        if handler is None:
            continue
        for attempt in range(max(1, attempts)):
            try:
                result = await handler(messages)
                if result:
                    return result
                raise LLMError(f"{provider} returned an empty completion")
            except TransientLLMError as exc:
                errors.append(str(exc))
                await asyncio.sleep(min(2**attempt, 8))
            except LLMError as exc:
                errors.append(str(exc))
                break
            except httpx.HTTPError as exc:
                errors.append(f"{provider} transport error: {exc}")
                await asyncio.sleep(min(2**attempt, 8))
    raise LLMError(" | ".join(errors) or "no LLM provider available")


async def stream(
    messages: list[dict[str, str]],
    providers: list[str] | None = None,
) -> AsyncIterator[str]:
    order = providers or provider_order()
    primary = next((p for p in order if p in PROVIDERS), "echo")
    handler = PROVIDERS[primary]

    if primary in {"groq", "ollama"}:
        async for chunk in _stream_openai_style(primary, handler, messages):
            yield chunk
        return

    text = await chat(messages, providers=order)
    for line in text.splitlines() or [""]:
        yield line


async def _stream_openai_style(
    provider: str,
    handler: Any,
    messages: list[dict[str, str]],
) -> AsyncIterator[str]:
    if provider == "groq":
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {settings.groq_api_key}"}
        payload = {"model": settings.groq_model, "messages": messages, "stream": True}
        timeout = settings.llm_timeout
    else:
        url = f"{settings.ollama_url.rstrip('/')}/api/chat"
        headers = {}
        model = await resolve_ollama_model() or settings.ollama_model
        payload = {"model": model, "messages": messages, "stream": True}
        timeout = settings.ollama_timeout

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as res:
                if res.status_code >= 400:
                    await res.aread()
                    raise LLMError(f"{provider} {res.status_code}: {res.text[:200]}")
                async for line in res.aiter_lines():
                    token = _extract_token(provider, line)
                    if token:
                        yield token
    except (LLMError, httpx.HTTPError):
        text = await chat(messages, providers=[provider])
        yield text


def _extract_token(provider: str, line: str) -> str:
    line = line.strip()
    if not line or line == "[DONE]":
        return ""
    if line.startswith("data:"):
        line = line[5:].strip()
        if not line or line == "[DONE]":
            return ""
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return ""
    if provider == "groq":
        delta = data.get("choices", [{}])[0].get("delta", {})
        return delta.get("content") or ""
    return data.get("message", {}).get("content") or ""
