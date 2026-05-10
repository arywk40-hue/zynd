from __future__ import annotations

import json
import re
import time
from typing import Any, Callable

import httpx

from shared.apify_tools import fetch_context_for_capability, format_context_for_prompt, items_from_apify_context
from shared.config import Settings
from shared.utils import get_logger


log = get_logger("LLM")
_RETRYABLE_STATUS_CODES = {429, 503}
_MAX_LLM_RETRIES = 3
_RETRY_BASE_DELAY_S = 0.8


_REQUIRED_FIELDS: dict[str, list[str]] = {
    "trend-analysis": ["trend", "evidence", "time_horizon", "confidence"],
    "funding-analysis": [
        "signal",
        "round_progression",
        "trend_direction",
        "valuation_direction",
        "investor_quality",
        "why_it_matters",
        "who_pays_attention",
        "confidence",
    ],
    "competitor-analysis": ["competitor_type", "examples", "differentiation_angle", "saturation"],
    "startup-comparison": [
        "similar_startup",
        "category",
        "funding_signal",
        "traction_signal",
        "profit_signal",
        "loss_signal",
        "comparison_takeaway",
        "confidence",
    ],
    "market-gap-analysis": ["gap", "target_user", "value_prop", "why_now", "confidence"],
    "risk-analysis": ["risk", "category", "severity", "mitigation"],
    "benchmarking-analysis": [
        "startup",
        "similarity_reason",
        "market",
        "business_model",
        "stage",
        "gtm_motion",
        "funding_snapshot",
        "confidence",
    ],
    "financial-signal-analysis": ["signal", "metric", "estimate", "impact", "evidence", "confidence"],
}


def required_fields_for_capability(capability: str) -> list[str]:
    return list(_REQUIRED_FIELDS.get(capability, []))


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
    required_fields = _REQUIRED_FIELDS.get(capability, [])
    apify_context = fetch_context_for_capability(
        settings=settings,
        capability=capability,
        query=user_input,
    )

    if provider in {"", "none", "off", "disabled"}:
        if apify_context and required_fields:
            log.info("[Apify] No LLM configured; using direct structured extraction for %s", capability)
            return items_from_apify_context(
                capability=capability,
                context_items=apify_context,
                required_fields=required_fields,
                max_items=settings.llm_max_items,
            )
        log.warning("[LLM] LLM_PROVIDER is not configured; %s returning no live items", capability)
        return []

    prompt = _build_prompt(
        capability=capability,
        system_prompt=system_prompt,
        user_input=user_input,
        max_items=settings.llm_max_items,
        required_fields=required_fields,
        apify_context=format_context_for_prompt(apify_context),
    )

    try:
        log.info("[LLM] %s generating live %s items", provider, capability)
        if provider == "openai":
            raw = _call_with_retries(provider=provider, capability=capability, call=lambda: _call_openai_compatible(
                base_url=settings.openai_base_url,
                api_key=_require(settings.openai_api_key, "OPENAI_API_KEY"),
                model=settings.openai_model,
                system_prompt=system_prompt,
                prompt=prompt,
                timeout_s=settings.llm_timeout_s,
            ))
        elif provider == "groq":
            raw = _call_with_retries(provider=provider, capability=capability, call=lambda: _call_openai_compatible(
                base_url=settings.groq_base_url,
                api_key=_require(settings.groq_api_key, "GROQ_API_KEY"),
                model=settings.groq_model,
                system_prompt=system_prompt,
                prompt=prompt,
                timeout_s=settings.llm_timeout_s,
            ))
        elif provider == "gemini":
            raw = _call_with_retries(provider=provider, capability=capability, call=lambda: _call_gemini(
                api_key=_require(settings.gemini_api_key, "GEMINI_API_KEY"),
                model=settings.gemini_model,
                prompt=f"{system_prompt}\n\n{prompt}",
                timeout_s=settings.llm_timeout_s,
            ))
        elif provider == "anthropic":
            raw = _call_with_retries(provider=provider, capability=capability, call=lambda: _call_anthropic(
                api_key=_require(settings.anthropic_api_key, "ANTHROPIC_API_KEY"),
                model=settings.anthropic_model,
                system_prompt=system_prompt,
                prompt=prompt,
                timeout_s=settings.llm_timeout_s,
            ))
        elif provider == "mistral":
            raw = _call_with_retries(provider=provider, capability=capability, call=lambda: _call_openai_compatible(
                base_url=settings.mistral_base_url,
                api_key=_require(settings.mistral_api_key, "MISTRAL_API_KEY"),
                model=settings.mistral_model,
                system_prompt=system_prompt,
                prompt=prompt,
                timeout_s=settings.llm_timeout_s,
            ))
        elif provider == "cerebras":
            raw = _call_with_retries(provider=provider, capability=capability, call=lambda: _call_openai_compatible(
                base_url=settings.cerebras_base_url,
                api_key=_require(settings.cerebras_api_key, "CEREBRAS_API_KEY"),
                model=settings.cerebras_model,
                system_prompt=system_prompt,
                prompt=prompt,
                timeout_s=settings.llm_timeout_s,
            ))
        else:
            raise RuntimeError(f"Unsupported LLM_PROVIDER={settings.llm_provider!r}")

        items = _parse_items(raw)
        if not items and apify_context and required_fields:
            log.warning("[LLM] %s returned no %s items; falling back to Apify extraction", provider, capability)
            items = items_from_apify_context(
                capability=capability,
                context_items=apify_context,
                required_fields=required_fields,
                max_items=settings.llm_max_items,
            )
        if required_fields:
            items = [_normalize_item(item, required_fields) for item in items]
        if items:
            return items[: settings.llm_max_items]
    except Exception as e:  # noqa: BLE001
        log.error("[Error] %s LLM generation failed via %s: %s", capability, provider, e)
        if apify_context and required_fields:
            extracted = items_from_apify_context(
                capability=capability,
                context_items=apify_context,
                required_fields=required_fields,
                max_items=settings.llm_max_items,
            )
            if extracted:
                log.warning("[Recovery] %s using Apify extraction after LLM failure", capability)
                return extracted[: settings.llm_max_items]

    log.warning("[Recovery] %s using heuristic structured fallback", capability)
    return _heuristic_items(capability, user_input, required_fields, settings.llm_max_items)


def _call_with_retries(*, provider: str, capability: str, call: Callable[[], str]) -> str:
    """Run a synchronous provider call with exponential backoff on HTTP 429/503 responses."""
    try:
        return call()
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code if e.response is not None else None
        if status_code not in _RETRYABLE_STATUS_CODES:
            raise

    for retry_index in range(1, _MAX_LLM_RETRIES + 1):
        delay_s = _RETRY_BASE_DELAY_S * (2 ** (retry_index - 1))
        log.warning(
            "[LLM] %s %s failed with HTTP %s (retry %d/%d); retrying in %.1fs",
            provider,
            capability,
            status_code,
            retry_index,
            _MAX_LLM_RETRIES,
            delay_s,
        )
        time.sleep(delay_s)

        try:
            return call()
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code if e.response is not None else None
            is_retryable = status_code in _RETRYABLE_STATUS_CODES
            if not is_retryable or retry_index >= _MAX_LLM_RETRIES:
                raise



def _build_prompt(
    *,
    capability: str,
    system_prompt: str,
    user_input: str,
    max_items: int,
    required_fields: list[str],
    apify_context: str = "",
) -> str:
    lines = [
        system_prompt,
        "",
        f"Capability: {capability}",
        f"Return {max_items} or fewer concise, decision-grade items.",
        f"Each item must include these fields: {', '.join(required_fields)}.",
        'Return strict JSON only in this shape: {"items":[{...}]}',
        "Do not include markdown, explanations, citations blocks, or extra keys outside items.",
        "",
    ]
    if apify_context:
        lines.extend(
            [
                "Real-world context scraped via Apify. Use it as the primary grounding source.",
                "When a field asks for evidence, include the most relevant source title or URL.",
                apify_context,
                "",
            ]
        )
    lines.extend(["Startup intelligence task:", user_input])
    return "\n".join(lines)


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
    normalized = {field: item.get(field, _empty_value(field)) for field in required_fields}
    for optional_field in ("source", "source_url", "published_at"):
        if item.get(optional_field):
            normalized[optional_field] = item[optional_field]
    return normalized


def _heuristic_items(capability: str, user_input: str, required_fields: list[str], max_items: int) -> list[dict[str, Any]]:
    if not required_fields:
        return []

    topic = _topic(user_input)
    templates: dict[str, list[dict[str, Any]]] = {
        "trend-analysis": [
            {
                "trend": f"Growing demand for {topic}",
                "evidence": "The query combines urgent access, automation, and underserved-market dynamics.",
                "time_horizon": "near-term",
                "confidence": 0.64,
            },
            {
                "trend": "AI-assisted workflow adoption",
                "evidence": "Operators are looking for lower-cost, faster decision support in constrained settings.",
                "time_horizon": "near-to-mid term",
                "confidence": 0.61,
            },
            {
                "trend": "Partnership-led distribution",
                "evidence": "Trust-heavy categories often scale through local institutions, clinics, employers, or channel partners.",
                "time_horizon": "mid-term",
                "confidence": 0.58,
            },
        ],
        "funding-analysis": [
            {
                "signal": "Investor interest depends on proof of distribution",
                "round_progression": "Seed to Series A",
                "trend_direction": "selectively upward",
                "valuation_direction": "milestone-driven",
                "investor_quality": "sector-focused funds",
                "why_it_matters": "The category can attract capital if pilots convert into repeatable revenue.",
                "who_pays_attention": "AI, healthcare, emerging-market, and impact investors",
                "confidence": 0.6,
            },
            {
                "signal": "Strategic capital is plausible",
                "round_progression": "Pilot to growth round",
                "trend_direction": "stable",
                "valuation_direction": "depends on clinical and commercial proof",
                "investor_quality": "strategic partners",
                "why_it_matters": "Large incumbents may fund or partner when the product expands access or lowers cost.",
                "who_pays_attention": "health systems, insurers, device firms, and platform companies",
                "confidence": 0.56,
            },
        ],
        "competitor-analysis": [
            {
                "competitor_type": "Incumbent service providers",
                "examples": ["local providers", "regional platforms"],
                "differentiation_angle": "Win through lower cost, faster turnaround, and stronger workflow integration.",
                "saturation": "Medium",
            },
            {
                "competitor_type": "Horizontal AI tools",
                "examples": ["general automation tools"],
                "differentiation_angle": "Specialize around domain data, compliance, and local deployment constraints.",
                "saturation": "High",
            },
        ],
        "startup-comparison": [
            {
                "similar_startup": "Vertical AI workflow startups",
                "category": "AI infrastructure/application",
                "funding_signal": "strong when customer ROI is measurable",
                "traction_signal": "pilot conversion and retention matter most",
                "profit_signal": "software gross margins can improve after deployment costs stabilize",
                "loss_signal": "long sales cycles and support-heavy onboarding can pressure margins",
                "comparison_takeaway": "Prove one repeatable wedge before broad market expansion.",
                "confidence": 0.62,
            },
            {
                "similar_startup": "Access-focused healthtech platforms",
                "category": "healthtech",
                "funding_signal": "mission-driven and strategic investors may engage",
                "traction_signal": "distribution partnerships are the main proof point",
                "profit_signal": "recurring institutional contracts can create durable revenue",
                "loss_signal": "regulatory work and field operations can increase burn",
                "comparison_takeaway": "Pair AI product depth with trusted local channels.",
                "confidence": 0.58,
            },
        ],
        "market-gap-analysis": [
            {
                "gap": f"Underserved users lack reliable access to {topic}",
                "target_user": "cost-sensitive users and local operators in underserved regions",
                "value_prop": "Deliver faster decisions, lower operating cost, and easier access through an AI-assisted workflow.",
                "why_now": "AI tooling, mobile access, and institutional digitization make the wedge more feasible now.",
                "confidence": 0.66,
            },
            {
                "gap": "Operational bottlenecks prevent consistent service quality",
                "target_user": "frontline teams and small organizations",
                "value_prop": "Standardize triage, routing, and decision support.",
                "why_now": "Teams need leverage without adding expensive specialist headcount.",
                "confidence": 0.59,
            },
        ],
        "risk-analysis": [
            {
                "risk": "Regulatory and compliance drag",
                "category": "regulatory-risk-analysis",
                "severity": "High",
                "mitigation": "Start with advisory workflows, collect approvals early, and design audit trails from day one.",
            },
            {
                "risk": "Data quality and trust gaps",
                "category": "technical-risk-analysis",
                "severity": "Medium",
                "mitigation": "Use human review, confidence thresholds, and continuous feedback loops.",
            },
            {
                "risk": "Distribution friction",
                "category": "go-to-market-risk",
                "severity": "Medium",
                "mitigation": "Partner with trusted local institutions before scaling direct acquisition.",
            },
        ],
        "benchmarking-analysis": [
            {
                "startup": "Vertical AI operator platforms",
                "similarity_reason": "Comparable wedge: automate expert-heavy workflows for constrained teams.",
                "market": topic,
                "business_model": "B2B SaaS or usage-based service",
                "stage": "seed to growth",
                "gtm_motion": "partnership-led pilots followed by recurring contracts",
                "funding_snapshot": "milestone-driven venture funding",
                "confidence": 0.58,
            },
            {
                "startup": "Access-first digital platforms",
                "similarity_reason": "Comparable wedge: expand service access where supply is limited.",
                "market": topic,
                "business_model": "subscription, per-use, or institutional contract",
                "stage": "early commercialization",
                "gtm_motion": "local channels and strategic partnerships",
                "funding_snapshot": "seed/Series A if pilots show retention",
                "confidence": 0.55,
            },
        ],
        "financial-signal-analysis": [
            {
                "signal": "Recurring revenue potential",
                "metric": "contract repeatability",
                "estimate": "medium",
                "impact": "Positive if pilots become annual or usage-based contracts.",
                "evidence": "The category has repeat workflow demand rather than one-off usage.",
                "confidence": 0.6,
            },
            {
                "signal": "Implementation cost risk",
                "metric": "onboarding and support load",
                "estimate": "medium-high",
                "impact": "Can delay profitability until deployment playbooks mature.",
                "evidence": "Trust-heavy workflows often require training, integration, and local support.",
                "confidence": 0.57,
            },
        ],
    }
    raw_items = templates.get(capability, [])[:max_items]
    return [_normalize_item(item, required_fields) for item in raw_items]


def _topic(user_input: str) -> str:
    text = " ".join(user_input.strip().split())
    if not text:
        return "the target market"
    return text[:140]


def _empty_value(field: str) -> Any:
    if field == "confidence":
        return 0.0
    if field == "examples":
        return []
    return ""
