import sys
import types
import unittest
from unittest import mock

from shared import apify_tools
from shared.config import Settings


NEWS_PAGE = {
    "search_parameters": {"q": "ai contract review", "gl": "us", "hl": "en", "max_pages": 1},
    "search_metadata": {"total_results": 2, "news_count": 2, "pages_processed": 1},
    "page_number": 1,
    "news_results": [
        {
            "position": 1,
            "title": "Contract review startup raises Series A",
            "link": "https://example.com/contract-review-series-a",
            "source": "Example News",
            "snippet": "The round was led by an existing seed investor.",
            "date": "2 days ago",
        },
        {
            "position": 2,
            "title": "Investors keep backing legal AI tools",
            "link": "https://example.com/legal-ai-funding",
            "source": "Example Wire",
            "snippet": "Funding for legal software rose again this quarter.",
            "date": "1 week ago",
        },
    ],
}


class _FakeApifyClient:
    def __init__(self, token: str) -> None:
        self.actor_ids: list[str] = []
        self.calls: list[dict] = []
        _FakeApifyClient.last = self

    def actor(self, actor_id: str) -> "_FakeApifyClient":
        self.actor_ids.append(actor_id)
        return self

    def call(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        return {"defaultDatasetId": "dataset-1"}

    def dataset(self, dataset_id: str) -> "_FakeApifyClient":
        return self

    def iterate_items(self):
        return iter([NEWS_PAGE])


class GoogleNewsActorTests(unittest.TestCase):
    def setUp(self) -> None:
        apify_tools._CACHE.clear()

    def test_default_news_actor(self) -> None:
        self.assertEqual(Settings.model_fields["apify_google_news_actor"].default, "johnvc/GoogleNewsAPI")

    def test_news_context_maps_input_and_articles(self) -> None:
        settings = Settings(
            apify_enabled=True,
            apify_api_token="test-token",
            apify_max_items=5,
            apify_timeout_s=20,
            apify_cache_ttl_s=0,
            apify_google_news_actor="johnvc/GoogleNewsAPI",
        )
        fake_module = types.ModuleType("apify_client")
        fake_module.ApifyClient = _FakeApifyClient

        with mock.patch.dict(sys.modules, {"apify_client": fake_module}):
            items = apify_tools.fetch_context_for_capability(
                settings=settings,
                capability="funding-analysis",
                query="ai contract review",
            )

        client = _FakeApifyClient.last
        self.assertEqual(client.actor_ids, ["johnvc/GoogleNewsAPI"])
        run_input = client.calls[0]["run_input"]
        self.assertTrue(run_input["q"].startswith("ai contract review "))
        self.assertEqual(run_input["hl"], "en")
        self.assertEqual(run_input["max_pages"], 1)
        self.assertGreaterEqual(client.calls[0]["timeout_secs"], 60)

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["title"], "Contract review startup raises Series A")
        self.assertEqual(items[0]["text"], "The round was led by an existing seed investor.")
        self.assertEqual(items[0]["url"], "https://example.com/contract-review-series-a")
        self.assertEqual(items[0]["source"], "Example News")
        self.assertEqual(items[0]["published_at"], "2 days ago")

    def test_news_context_respects_max_items(self) -> None:
        settings = Settings(
            apify_enabled=True,
            apify_api_token="test-token",
            apify_max_items=1,
            apify_cache_ttl_s=0,
            apify_google_news_actor="johnvc/GoogleNewsAPI",
        )
        fake_module = types.ModuleType("apify_client")
        fake_module.ApifyClient = _FakeApifyClient

        with mock.patch.dict(sys.modules, {"apify_client": fake_module}):
            items = apify_tools.fetch_context_for_capability(
                settings=settings,
                capability="risk-analysis",
                query="ai contract review",
            )

        self.assertEqual([item["title"] for item in items], ["Contract review startup raises Series A"])


if __name__ == "__main__":
    unittest.main()
