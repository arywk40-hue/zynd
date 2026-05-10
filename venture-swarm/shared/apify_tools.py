from __future__ import annotations

from typing import Any

from shared.config import Settings
from shared.utils import get_logger


log = get_logger("Apify")

_MAX_TEXT_LEN = 420
_DEFAULT_MAX_ITEMS = 5

_CAPABILITY_ACTORS = {
    "trend-analysis": "google_search",
    "funding-analysis": "google_news",
    "competitor-analysis": "google_search",
    "market-gap-analysis": "reddit",
    "startup-comparison": "google_search",
    "financial-signal-analysis": "google_news",
    "risk-analysis": "google_news",
    "benchmarking-analysis": "google_search",
}

_QUERY_HINTS = {
    "trend-analysis": "market trends growth adoption recent reports",
    "funding-analysis": "startup funding venture capital investment round valuation investors",
    "competitor-analysis": "companies alternatives competitors market saturation",
    "market-gap-analysis": "problem pain frustration underserved users need alternative",
    "startup-comparison": "similar startups funding traction acquisition failed",
    "financial-signal-analysis": "revenue ARR MRR burn runway margin unit economics profitability",
    "risk-analysis": "regulation compliance lawsuit legal technical risk privacy security",
    "benchmarking-analysis": "market size TAM SAM SOM industry benchmark business model stage",
}


def fetch_context_for_capability(
    *,
    settings: Settings,
    capability: str,
    query: str,
) -> list[dict[str, Any]]:
    if not settings.apify_enabled:
        return []
    if not settings.apify_api_token:
        log.warning("[Apify] APIFY_ENABLED=true but APIFY_API_TOKEN is missing")
        return []

    actor_key = _CAPABILITY_ACTORS.get(capability)
    if not actor_key:
        log.warning("[Apify] No actor mapping for capability=%s", capability)
        return []

    max_items = max(1, min(settings.apify_max_items or _DEFAULT_MAX_ITEMS, 10))
    actor_id = _actor_id(settings, actor_key)
    run_input = _actor_input(actor_key, _capability_query(capability, query), max_items)

    try:
        from apify_client import ApifyClient
    except ImportError:
        log.warning("[Apify] apify-client is not installed; skipping real web context")
        return []

    try:
        log.info("[Apify] Running %s for %s", actor_id, capability)
        client = ApifyClient(settings.apify_api_token)
        run = client.actor(actor_id).call(run_input=run_input)
        dataset_id = run.get("defaultDatasetId")
        if not dataset_id:
            log.warning("[Apify] %s finished without a dataset", actor_id)
            return []

        items: list[dict[str, Any]] = []
        for raw_item in client.dataset(dataset_id).iterate_items():
            for normalized in _normalize_items(raw_item):
                if normalized["title"] or normalized["text"]:
                    items.append(normalized)
                if len(items) >= max_items:
                    break
            if len(items) >= max_items:
                break

        log.info("[Apify] %s returned %d grounding item(s)", capability, len(items))
        return items
    except Exception as e:  # noqa: BLE001
        log.warning("[Apify] Context fetch failed for %s via %s: %s", capability, actor_id, e)
        return []


def format_context_for_prompt(context_items: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for index, item in enumerate(context_items, start=1):
        title = item.get("title") or "Untitled source"
        source = item.get("source") or "unknown source"
        url = item.get("url") or ""
        text = _truncate(str(item.get("text") or ""))

        lines.append(f"[{index}] {title}")
        lines.append(f"source: {source}")
        if url:
            lines.append(f"url: {url}")
        if text:
            lines.append(f"text: {text}")
        lines.append("")

    return "\n".join(lines).strip()


def items_from_apify_context(
    *,
    capability: str,
    context_items: list[dict[str, Any]],
    required_fields: list[str],
    max_items: int,
) -> list[dict[str, Any]]:
    structured = [
        _structured_item(capability=capability, source=item, required_fields=required_fields)
        for item in context_items[:max_items]
    ]
    return [item for item in structured if item]


def _actor_id(settings: Settings, actor_key: str) -> str:
    if actor_key == "google_news":
        return settings.apify_google_news_actor
    if actor_key == "reddit":
        return settings.apify_reddit_actor
    return settings.apify_google_search_actor


def _capability_query(capability: str, query: str) -> str:
    hint = _QUERY_HINTS.get(capability, "startup intelligence")
    return f"{query} {hint}".strip()


def _actor_input(actor_key: str, query: str, max_items: int) -> dict[str, Any]:
    if actor_key == "google_news":
        return {
            "query": query,
            "queries": query,
            "maxItems": max_items,
            "maxItemsPerQuery": max_items,
            "language": "en",
            "proxyConfiguration": {"useApifyProxy": True},
        }
    if actor_key == "reddit":
        return {
            "startUrls": [{"url": f"https://www.reddit.com/search/?q={query.replace(' ', '+')}&sort=relevance&t=year"}],
            "searches": [query],
            "maxItems": max_items,
            "proxy": {"useApifyProxy": True},
        }
    return {
        "queries": query,
        "maxPagesPerQuery": 1,
        "resultsPerPage": max_items,
        "languageCode": "en",
        "countryCode": "us",
        "proxyConfiguration": {"useApifyProxy": True},
    }


def _normalize_items(item: dict[str, Any]) -> list[dict[str, Any]]:
    organic_results = item.get("organicResults")
    if isinstance(organic_results, list) and organic_results:
        return [_normalize_item(result) for result in organic_results if isinstance(result, dict)]
    return [_normalize_item(item)]


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    title = _first_text(item, "title", "name", "headline", "postTitle")
    text = _first_text(
        item,
        "description",
        "snippet",
        "text",
        "body",
        "selftext",
        "content",
        "summary",
    )
    url = _first_text(item, "url", "link", "organicUrl")
    source = _source_text(item)
    published_at = _first_text(item, "date", "publishedAt", "createdAt", "timestamp")

    return {
        "title": _truncate(title),
        "text": _truncate(text),
        "url": url,
        "source": source,
        "published_at": published_at,
    }


def _structured_item(
    *,
    capability: str,
    source: dict[str, Any],
    required_fields: list[str],
) -> dict[str, Any]:
    title = str(source.get("title") or "Web signal")
    text = str(source.get("text") or "")
    evidence = _evidence(source)

    values: dict[str, Any] = {
        "trend": title,
        "evidence": evidence,
        "time_horizon": "current market signal",
        "signal": title,
        "round_progression": "unknown",
        "trend_direction": "unknown",
        "valuation_direction": "unknown",
        "investor_quality": "unknown",
        "why_it_matters": text or evidence,
        "who_pays_attention": "founders, operators, and investors",
        "competitor_type": title,
        "examples": [title],
        "differentiation_angle": text or evidence,
        "saturation": "unknown",
        "similar_startup": title,
        "category": "startup intelligence",
        "funding_signal": evidence,
        "traction_signal": text or evidence,
        "profit_signal": "unknown",
        "loss_signal": "unknown",
        "comparison_takeaway": text or evidence,
        "gap": title,
        "target_user": "users described by the source context",
        "value_prop": text or evidence,
        "why_now": evidence,
        "risk": title,
        "severity": "unknown",
        "mitigation": "Validate with source material and expert review",
        "startup": title,
        "similarity_reason": text or evidence,
        "market": "unknown",
        "business_model": "unknown",
        "stage": "unknown",
        "gtm_motion": "unknown",
        "funding_snapshot": evidence,
        "metric": title,
        "estimate": "unknown",
        "impact": text or evidence,
        "confidence": 0.55,
    }

    if capability == "risk-analysis":
        values["category"] = "market/regulatory"
    elif capability == "startup-comparison":
        values["category"] = "comparable startup"

    structured = {field: values.get(field, "") for field in required_fields}
    for optional in ("source", "source_url", "published_at"):
        value = _optional_source_value(optional, source)
        if value:
            structured[optional] = value
    return structured


def _optional_source_value(key: str, source: dict[str, Any]) -> str:
    if key == "source_url":
        return str(source.get("url") or "")
    return str(source.get(key) or "")


def _evidence(source: dict[str, Any]) -> str:
    title = str(source.get("title") or "").strip()
    text = str(source.get("text") or "").strip()
    url = str(source.get("url") or "").strip()
    base = " - ".join(part for part in (title, text) if part)
    if url:
        return f"{base} ({url})" if base else url
    return base


def _source_text(item: dict[str, Any]) -> str:
    source = item.get("source")
    if isinstance(source, dict):
        return _first_text(source, "title", "name", "domain")
    if isinstance(source, str):
        return source
    return _first_text(item, "displayedUrl", "domain", "siteName", "subreddit", "communityName")


def _first_text(source: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = source.get(key)
        if value is None:
            continue
        if isinstance(value, (str, int, float)):
            text = str(value).strip()
            if text:
                return text
    return ""


def _truncate(text: str) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= _MAX_TEXT_LEN:
        return cleaned
    return f"{cleaned[: _MAX_TEXT_LEN - 3]}..."
