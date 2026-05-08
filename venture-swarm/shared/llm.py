from __future__ import annotations

import json
import re
from typing import Any

import httpx

from shared.config import Settings
from shared.utils import get_logger


log = get_logger("LLM")


_REQUIRED_FIELDS: dict[str, list[str]] = {
    "trend-analysis": ["trend", "evidence", "time_horizon", "confidence"],
    "funding-analysis": ["signal", "why_it_matters", "who_pays_attention", "confidence"],
    "competitor-analysis": ["competitor_type", "examples", "differentiation_angle", "saturation"],
    "market-gap-analysis": ["gap", "target_user", "value_prop", "why_now", "confidence"],
    "risk-analysis": ["risk", "category", "severity", "mitigation"],
}


def build_llm_data_factory(
    *,
    settings: Settings,
    capability: str,
    system_prompt: str,
) -> Any:
    def _build_data(user_input: str) -> list[dict]:
        return generate_structured_items(
            settings=settings,
            capability=capability,
            system_prompt=system_prompt,
            user_input=user_input,
        )

    return _build_data


def generate_structured_items(
    *,
    settings: Settings,
    capability: str,
    system_prompt: str,
    user_input: str,
) -> list[dict]:
    provider = settings.llm_provider.strip().lower()
    if provider in {"", "none", "off", "disabled"}:
        log.warning("[LLM] LLM_PROVIDER is not configured; %s returning no live items", capability)
        return []

    required_fields = _REQUIRED_FIELDS.get(capability, [])
    prompt = _build_prompt(
        capability=capability,
        system_prompt=system_prompt,
        user_input=user_input,
        max_items=settings.llm_max_items,
        required_fields=required_fields,
    )

    log.info("[LLM] %s generating live %s items", provider, capability)
    if provider == "openai":
        raw = _call_openai_compatible(
            base_url=settings.openai_base_url,
            api_key=_require(settings.openai_api_key, "OPENAI_API_KEY"),
            model=settings.openai_model,
            system_prompt=system_prompt,
            prompt=prompt,
            timeout_s=settings.llm_timeout_s,
        )
    elif provider == "groq":
        raw = _call_openai_compatible(
            base_url=settings.groq_base_url,
            api_key=_require(settings.groq_api_key, "GROQ_API_KEY"),
            model=settings.groq_model,
            system_prompt=system_prompt,
            prompt=prompt,
            timeout_s=settings.llm_timeout_s,
        )
    elif provider == "gemini":
        raw = _call_gemini(
            api_key=_require(settings.gemini_api_key, "GEMINI_API_KEY"),
            model=settings.gemini_model,
            prompt=f"{system_prompt}\n\n{prompt}",
            timeout_s=settings.llm_timeout_s,
        )
    elif provider == "anthropic":
        raw = _call_anthropic(
            api_key=_require(settings.anthropic_api_key, "ANTHROPIC_API_KEY"),
            model=settings.anthropic_model,
            system_prompt=system_prompt,
            prompt=prompt,
            timeout_s=settings.llm_timeout_s,
        )
    elif provider == "mistral":
        raw = _call_openai_compatible(
            base_url=settings.mistral_base_url,
            api_key=_require(settings.mistral_api_key, "MISTRAL_API_KEY"),
            model=settings.mistral_model,
            system_prompt=system_prompt,
            prompt=prompt,
            timeout_s=settings.llm_timeout_s,
        )
    elif provider == "cerebras":
        raw = _call_openai_compatible(
            base_url=settings.cerebras_base_url,
            api_key=_require(settings.cerebras_api_key, "CEREBRAS_API_KEY"),
            model=settings.cerebras_model,
            system_prompt=system_prompt,
            prompt=prompt,
            timeout_s=settings.llm_timeout_s,
        )
    else:
        raise RuntimeError(f"Unsupported LLM_PROVIDER={settings.llm_provider!r}")

    items = _parse_items(raw)
    if required_fields:
        items = [_normalize_item(item, required_fields) for item in items]
    return items[: settings.llm_max_items]


def _build_prompt(
    *,
    capability: str,
    system_prompt: str,
    user_input: str,
    max_items: int,
    required_fields: list[str],
) -> str:
    return "\n".join(
        [
            system_prompt,
            "",
            f"Capability: {capability}",
            f"Return {max_items} or fewer concise, decision-grade items.",
            f"Each item must include these fields: {', '.join(required_fields)}.",
            'Return strict JSON only in this shape: {"items":[{...}]}',
            "Do not include markdown, explanations, citations blocks, or extra keys outside items.",
            "",
            "Startup intelligence task:",
            user_input,
        ]
    )


def _require(value: str | None, env_name: str) -> str:
    if not value:
        raise RuntimeError(f"{env_name} is required when selected as LLM_PROVIDER")
    return value


def _call_openai_compatible(
    *,
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    prompt: str,
    timeout_s: float,
) -> str:
    payload = {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
    }
    with httpx.Client(timeout=httpx.Timeout(timeout_s)) as client:
        response = client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
    response.raise_for_status()
    return str(response.json()["choices"][0]["message"]["content"])


def _call_gemini(*, api_key: str, model: str, prompt: str, timeout_s: float) -> str:
    payload = {
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
        "contents": [{"parts": [{"text": prompt}]}],
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    with httpx.Client(timeout=httpx.Timeout(timeout_s)) as client:
        response = client.post(url, params={"key": api_key}, json=payload)
    response.raise_for_status()
    return str(response.json()["candidates"][0]["content"]["parts"][0]["text"])


def _call_anthropic(
    *,
    api_key: str,
    model: str,
    system_prompt: str,
    prompt: str,
    timeout_s: float,
) -> str:
    payload = {
        "model": model,
        "max_tokens": 1200,
        "temperature": 0.2,
        "system": system_prompt,
        "messages": [{"role": "user", "content": prompt}],
    }
    with httpx.Client(timeout=httpx.Timeout(timeout_s)) as client:
        response = client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json=payload,
        )
    response.raise_for_status()
    parts = response.json().get("content", [])
    return "\n".join(str(part.get("text", "")) for part in parts if part.get("type") == "text")


def _parse_items(raw: str) -> list[dict]:
    data = json.loads(_strip_code_fence(raw))
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("items") or data.get("results") or []
    else:
        items = []

    return [item for item in items if isinstance(item, dict)]


def _strip_code_fence(raw: str) -> str:
    text = raw.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    return match.group(1).strip() if match else text


def _normalize_item(item: dict[str, Any], required_fields: list[str]) -> dict[str, Any]:
    return {field: item.get(field, _empty_value(field)) for field in required_fields}


def _empty_value(field: str) -> Any:
    if field == "confidence":
        return 0.0
    if field == "examples":
        return []
    return ""
