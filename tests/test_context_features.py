import os
import unittest
from unittest.mock import patch

from backend.news_context import NewsContext
from backend.youtube_live import YouTubeLiveChat


class ContextFeatureTests(unittest.TestCase):
    def setUp(self):
        self.state = {
            "home": {"name": "Mandante", "score": 0},
            "away": {"name": "Visitante", "score": 0},
            "lineups": {"home": {"starters": [{"name": "Pedro"}], "bench": []}, "away": {"starters": [{"name": "João"}], "bench": []}},
        }

    @patch("backend.youtube_live.time.time", side_effect=[1, 1, 4, 7, 10, 10, 10])
    def test_top_three_mentions_are_sorted(self, _clock):
        chat = YouTubeLiveChat(self.state, lambda: None)
        for message in ("Pedro foi bem", "João também", "Pedro", "Pedro", "João", "Outro"):
            chat.track_mentions(message)
        ranking = chat.top_players()
        self.assertEqual([item["name"] for item in ranking], ["Pedro", "João"])
        self.assertEqual(ranking[0]["count"], 3)

    def test_news_is_optional_without_key(self):
        context = NewsContext(self.state)
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(context.configured())

    def test_news_trust_uses_official_or_recognized_domains(self):
        self.assertEqual(NewsContext.trust_label("https://ge.globo.com/futebol/noticia"), "alta")
        self.assertEqual(NewsContext.trust_label("https://example.invalid/story"), "não verificada")


if __name__ == "__main__":
    unittest.main()
