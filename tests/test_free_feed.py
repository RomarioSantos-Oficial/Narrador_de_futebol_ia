import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.free_feed import FreeFeed, Selection, normalize


def fixture():
    return {
        "header": {"competitions": [{
            "competitors": [
                {"homeAway": "away", "team": {"id": "2", "displayName": "Visitante"}, "score": "1"},
                {"homeAway": "home", "team": {"id": "1", "displayName": "Mandante"}, "score": "2"},
            ],
            "status": {"displayClock": "45'+2'", "type": {"state": "in", "completed": False}},
        }]},
        "boxscore": {"teams": [
            {"team": {"id": "2"}, "statistics": [{"name": "possessionPct", "displayValue": "40"}]},
            {"team": {"id": "1"}, "statistics": [{"name": "possessionPct", "displayValue": "60"}]},
        ]},
    }


class FeedTests(unittest.IsolatedAsyncioTestCase):
    def test_lineups_logos_and_named_cards(self):
        data = fixture()
        data['header']['competitions'][0]['competitors'][1]['team']['logos'] = [{'href': 'https://example.com/crest.png'}]
        data['rosters'] = [{'team': {'id': '1'}, 'formation': '4-3-3', 'roster': [
            {'starter': True, 'jersey': '10', 'athlete': {'id': '11', 'displayName': 'Jogador A'}, 'stats': []},
            {'starter': False, 'jersey': '12', 'athlete': {'id': '12', 'displayName': 'Reserva B'}, 'stats': []},
        ]}]
        data['keyEvents'] = [{'type': {'type': 'red-card'}, 'clock': {'displayValue': "65'"},
                              'team': {'id': '1', 'displayName': 'Mandante'},
                              'participants': [{'athlete': {'id': '11', 'displayName': 'Jogador A'}}]}]
        result, _ = normalize(data, 'bra.1')
        self.assertEqual(result['home']['logo'], 'https://example.com/crest.png')
        self.assertEqual(result['lineups']['home']['starters'][0]['red'], 1)
        self.assertEqual(result['lineups']['home']['bench'][0]['name'], 'Reserva B')
        self.assertEqual(result['cards'][0]['player'], 'Jogador A')
        self.assertIn('Cartão vermelho', result['events'][0]['text'])
        self.assertEqual(result['lineups']['away']['starters'], [])

    def test_live_search_excludes_scheduled_and_finished(self):
        app = FastAPI()
        FreeFeed({}, AsyncMock()).install(app)
        events = [{"id": str(i), "name": phase, "date": "2026-09-12T19:00Z",
                   "status": {"type": {"state": phase}, "displayClock": "32'"}}
                  for i, phase in enumerate(("pre", "in", "post"))]
        with patch("backend.free_feed.request", new=AsyncMock(return_value={"events": events})) as request:
            with TestClient(app) as client:
                response = client.get("/api/free/games?league=bra.1&live=true")
        self.assertEqual([game["id"] for game in response.json()], ["1"])
        self.assertNotIn("dates", request.call_args.kwargs)

    def test_team_order_missing_stats_and_stoppage_time(self):
        state, completed = normalize(fixture(), "bra.1")
        self.assertEqual(state["home"]["score"], 2)
        self.assertEqual(state["stats"]["possession"], [60, 40])
        self.assertEqual(state["stats"]["shots"], [None, None])
        self.assertEqual(state["minute"], 47)
        self.assertEqual(state["clock_display"], "45'+2'")
        self.assertFalse(completed)

    def test_corners_zero_missing_and_team_order(self):
        data = fixture()
        data['boxscore']['teams'][0]['statistics'].append({'name': 'wonCorners', 'displayValue': '0'})
        result, _ = normalize(data, 'bra.1')
        self.assertEqual(result['stats']['corners'], [None, 0])
        data['boxscore']['teams'][1]['statistics'].extend([
            {'name': 'wonCorners', 'displayValue': '1'},
            {'name': 'totalPasses', 'displayValue': '100'},
            {'name': 'accuratePasses', 'displayValue': '83'},
        ])
        result, _ = normalize(data, 'bra.1')
        self.assertEqual(result['stats']['corners'], [1, 0])
        self.assertEqual(result['stats']['pass_accuracy'], [83, None])

    def test_pregame_does_not_use_season_stats(self):
        data = fixture()
        data["header"]["competitions"][0]["status"]["type"]["state"] = "pre"
        state, _ = normalize(data, "bra.1")
        self.assertEqual(state["stats"]["possession"], [None, None])

    async def test_update_failure_keeps_previous_state(self):
        state = {"home": {"name": "Anterior"}}
        feed = FreeFeed(state, AsyncMock())
        with patch("backend.free_feed.request", new=AsyncMock(side_effect=HTTPException(502, "Falha"))):
            with self.assertRaises(HTTPException):
                await feed.update(Selection(league="bra.1", event="1"))
        self.assertEqual(state, {"home": {"name": "Anterior"}})

    async def test_background_update_and_stop(self):
        feed = FreeFeed({}, AsyncMock())
        feed.info["active"] = True
        feed.update = AsyncMock(return_value=True)
        with patch("backend.free_feed.asyncio.sleep", new=AsyncMock()):
            await feed.loop(Selection(league="bra.1", event="1"))
        feed.update.assert_awaited_once()
        self.assertFalse(feed.info["active"])
        feed.task = asyncio.create_task(asyncio.sleep(100))
        await feed.stop()
        self.assertIsNone(feed.task)


if __name__ == "__main__":
    unittest.main()
