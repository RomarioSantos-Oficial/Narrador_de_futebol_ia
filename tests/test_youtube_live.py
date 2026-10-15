import os
import unittest
from unittest.mock import AsyncMock, patch

from backend.youtube_live import YouTubeLiveChat


class YouTubeLiveChatTests(unittest.TestCase):
    def setUp(self):
        self.state = {
            "home": {"name": "Mandante", "score": 1},
            "away": {"name": "Visitante", "score": 0},
            "status": "AO VIVO", "minute": 42, "events": [],
            "lineups": {"home": {"starters": [{"name": "Pedro"}], "bench": [{"name": "Lucas"}]}, "away": {"starters": [], "bench": []}},
        }
        self.chat = YouTubeLiveChat(self.state, lambda: None)

    def test_commands_are_factual_and_do_not_change_score(self):
        response = self.chat.response_for("!placar", "Ana")
        self.assertIn("Mandante 1, Visitante 0", response)
        self.assertEqual(self.state["home"]["score"], 1)

    def test_user_is_rate_limited(self):
        self.assertIsNotNone(self.chat.response_for("!narrar", "Ana"))
        self.assertIsNone(self.chat.response_for("!narrar", "Ana"))

    def test_unknown_text_is_ignored(self):
        self.assertIsNone(self.chat.response_for("olá", "Ana"))

    def test_configuration_is_optional(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(self.chat.configured())

    def test_accepts_studio_link_and_extracts_video_id(self):
        link = "https://studio.youtube.com/live_chat?is_popout=1&v=ded3jykYQfA"
        self.assertEqual(self.chat.extract_video_id(link), "ded3jykYQfA")
        self.assertEqual(self.chat.extract_video_id("ded3jykYQfA"), "ded3jykYQfA")
        self.assertNotEqual(self.chat.extract_video_id(link), "liveChatId")

    def test_accepts_channel_handle_only(self):
        self.assertEqual(self.chat.extract_channel_handle("@PosJogoBR"), "PosJogoBR")
        self.assertEqual(self.chat.extract_channel_handle("https://www.youtube.com/@PosJogoBR"), "PosJogoBR")
        self.assertEqual(self.chat.extract_channel_handle("9b1r-t3y9-2mbw-gk3k-5dag"), "")

    def test_vote_accepts_only_roster_and_returns_percentage(self):
        self.assertIn("Pedro", self.chat.response_for("!vota Pedro", "Ana"))
        self.assertIsNotNone(self.chat.response_for("!vota jogador-inexistente", "Bia"))
        self.assertEqual(self.chat.status()["votes"][0]["percentage"], 100.0)

    def test_same_user_can_change_player_vote(self):
        self.chat.response_for("!vota Pedro", "Ana")
        self.chat.response_for("!vota Lucas", "Ana")
        self.assertEqual(self.chat.status()["votes"], [{"name": "Lucas", "votes": 1, "percentage": 100.0}])

    def test_saved_studio_link_is_resolved_before_chat_request(self):
        self.chat.saved_settings[self.chat.match_key()] = {
            "api_key": "test-api-key", "live_chat_id": "https://studio.youtube.com/live_chat?is_popout=1&v=ded3jykYQfA"
        }
        with patch.object(self.chat, "resolve_live_chat_id", new=AsyncMock(return_value=("resolved-chat-id", "ded3jykYQfA"))):
            with patch("backend.youtube_live.httpx.AsyncClient") as client_cls:
                response = client_cls.return_value.__aenter__.return_value.get
                response.return_value = AsyncMock()
                response.return_value.json.return_value = {"items": [], "nextPageToken": "next"}
                import asyncio
                asyncio.run(self.chat.fetch_chat_messages())
        self.assertEqual(self.chat.config()["live_chat_id"], "resolved-chat-id")


if __name__ == "__main__":
    unittest.main()
