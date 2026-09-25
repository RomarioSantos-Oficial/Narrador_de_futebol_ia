import asyncio
import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.ge_feed import GEFeed, agenda_games, matches, event_from_play
from backend.narration_channel import NarrationChannel, LeaseRequest
from tools.inspect_ge import parse_page


def play(text="O time avança pelo lado esquerdo.", **overrides):
    return {"id": "one", "createdAt": "2026-09-16T00:20:00Z", "moment": "18:01",
            "playType": {"id": "NORMAL"}, "period": {"abbreviation": "1T"},
            "body": {"blocks": [{"type": "unstyled", "text": text}]}, **overrides}


class GEParsingTests(unittest.TestCase):
    def setUp(self):
        self.primary = {"home": {"name": "CRB"}, "away": {"name": "Sport Recife"}, "kickoff": "2026-09-16T00:00:00Z"}
        self.match = {"id": 123, "homeTeam": {"popularName": "CRB"}, "awayTeam": {"popularName": "Sport"},
                      "startDate": "2026-09-15", "startHour": "21:00:00"}

    def test_identity_requires_both_sides_orientation_and_time(self):
        self.assertTrue(matches(self.primary, self.match))
        wrong = copy.deepcopy(self.primary)
        wrong["home"]["name"] = "Sport"
        self.assertFalse(matches(wrong, self.match))
        wrong = {**self.primary, "kickoff": "2026-09-17T00:00:00Z"}
        self.assertFalse(matches(wrong, self.match))

    def test_brazil_friendly_matches_page_and_agenda_without_relaxing_identity(self):
        primary = {"home": {"name": "Australia"}, "away": {"name": "Brazil"},
                   "kickoff": "2026-09-25T10:00:00Z"}
        match = {"homeTeam": {"popularName": "Austrália"},
                 "awayTeam": {"popularName": "Brasil"},
                 "startDate": "2026-09-25", "startHour": "07:00:00"}
        agenda = {**match, "firstContestant": match["homeTeam"],
                  "secondContestant": match["awayTeam"]}
        self.assertTrue(matches(primary, match))
        self.assertTrue(matches(primary, agenda, agenda=True))
        for wrong in (
            {**primary, "away": {"name": "Brazil U20"}},
            {**primary, "home": primary["away"], "away": primary["home"]},
            {**primary, "kickoff": "2026-09-26T10:00:00Z"},
        ):
            self.assertFalse(matches(wrong, match))
            self.assertFalse(matches(wrong, agenda, agenda=True))

    def test_pregame_text_is_visible_and_new_updates_are_eligible_for_voice(self):
        feed = GEFeed({}, None)
        now = datetime.now(timezone.utc)
        old = play("Bem-vindos!", id="welcome", moment=None,
                   period={"abbreviation": "Pré-jogo"},
                   createdAt=(now-timedelta(minutes=10)).isoformat())
        previous = feed.snapshot_events([old], 'url', {}, True)
        self.assertFalse(previous['ge:welcome']['speak'])
        new = play("Titulares confirmados.", id="lineup", title="BRASIL ESCALADO!",
                   moment=None, period={"abbreviation": "Pré-jogo"},
                   createdAt=now.isoformat())
        events = feed.snapshot_events([new, old], 'url', previous, False)
        self.assertEqual(len(feed.sorted_events(events)), 2)
        self.assertEqual(events['ge:lineup']['period'], 'Pré-jogo')
        self.assertIn('BRASIL ESCALADO!', events['ge:lineup']['text'])
        self.assertTrue(events['ge:lineup']['speak'])
        self.assertFalse(events['ge:welcome']['speak'])

    def test_agenda_extracts_only_public_match_urls(self):
        match = {**self.match, "firstContestant": self.match["homeTeam"], "secondContestant": self.match["awayTeam"],
                 "transmission": {"url": "https://ge.globo.com/futebol/jogo/15-09-2026/crb-sport.ghtml"}}
        value = {"2026-09-15": {"championshipsAgenda": [{"now": [{"match": match}]}]}}
        rows = agenda_games("window.dataSportsSchedule = { sport: " + json.dumps(value) + "};")
        self.assertEqual(len(rows), 1)
        self.assertTrue(matches(self.primary, rows[0]["match"], agenda=True))
        match["transmission"]["url"] = "http://127.0.0.1/private"
        self.assertEqual(agenda_games("window.dataSportsSchedule = { sport: " + json.dumps(value) + "};"), [])

    def test_summary_embeds_and_cancelled_goal_are_not_new_goals(self):
        self.assertIsNone(event_from_play(play(playType={"id": "SUMMARY_AUTOMATIC"}), "url"))
        self.assertIsNone(event_from_play(play(body={"blocks": [{"type": "atomic", "text": "embedded"}]}), "url"))
        event = event_from_play(play("Gol anulado após revisão.", playType={"id": "GOAL"}), "url")
        self.assertEqual(event["kind"], "event")

    def test_page_duplicates_edits_deletions_and_stale_replay(self):
        feed = GEFeed({}, None)
        feed.started_at = datetime.now(timezone.utc)-timedelta(seconds=5)
        current = play(createdAt=datetime.now(timezone.utc).isoformat())
        events = feed.snapshot_events([current], 'url', {}, False)
        first = events["ge:one"]["revision"]
        self.assertTrue(events["ge:one"]["speak"])
        events = feed.snapshot_events([current], 'url', events, False)
        self.assertTrue(events['ge:one']['speak'])
        edited = {**current, 'body': play('A jogada foi corrigida.')['body']}
        events = feed.snapshot_events([edited], 'url', events, False)
        self.assertNotEqual(first, events["ge:one"]["revision"])
        self.assertTrue(events["ge:one"]["corrected"])
        stale = play(id='two', createdAt=(datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat())
        events = feed.snapshot_events([edited, stale], 'url', events, False)
        self.assertFalse(events["ge:two"]["speak"])
        events = feed.snapshot_events([stale], 'url', events, False)
        self.assertNotIn("ge:one", events)
        initial = feed.snapshot_events([current], 'url', {}, True)
        self.assertTrue(initial['ge:one']['speak'])
        stale_initial = feed.snapshot_events([stale], 'url', {}, True)
        self.assertFalse(stale_initial['ge:two']['speak'])

    def test_parse_page_accepts_null_optional_sections(self):
        html = '''
        <script>
        window.trv2 = {
          transmission: {"match":{"id":123,"homeTeam":{"popularName":"CRB"},"awayTeam":{"popularName":"Sport"}}},
          statistics: null,
          plays: [{"id": "play-1", "createdAt": "2026-09-16T00:20:00Z", "moment": "18:01", "playType": {"id": "NORMAL"}, "period": {"abbreviation": "1T"}, "body": {"blocks": [{"type": "unstyled", "text": "Gol do CRB"}]}}],
          matchHistory: null,
          theSportsField: {"url": "https://field.example/track"}
        };
        </script>
        '''
        snapshot = parse_page(html)
        self.assertEqual(snapshot['transmission']['match']['id'], 123)
        self.assertIsNone(snapshot['statistics'])
        self.assertIsNone(snapshot['matchHistory'])
        self.assertEqual(snapshot['events'][0]['text'], 'Gol do CRB')

    def test_delayed_new_kickoff_is_eligible_but_older_history_is_not(self):
        feed = GEFeed({}, None)
        now = datetime.now(timezone.utc)
        pregame = play(id='pregame', createdAt=(now-timedelta(minutes=7)).isoformat())
        previous = feed.snapshot_events([pregame], 'url', {}, True)
        kickoff = play('Começa o jogo!', id='kickoff', moment='00:00',
                       createdAt=(now-timedelta(minutes=3)).isoformat())
        history = play(id='history', createdAt=(now-timedelta(minutes=20)).isoformat())
        events = feed.snapshot_events([kickoff, pregame, history], 'url', previous, False)
        self.assertTrue(events['ge:kickoff']['speak'])
        self.assertFalse(events['ge:history']['speak'])
        refreshed = feed.snapshot_events([kickoff, pregame, history], 'url', events, False)
        self.assertTrue(refreshed['ge:kickoff']['speak'])
        self.assertEqual(refreshed['ge:kickoff']['revision'], events['ge:kickoff']['revision'])

    def test_correction_remains_available_after_next_poll(self):
        feed = GEFeed({}, None)
        original = play(createdAt=datetime.now(timezone.utc).isoformat())
        previous = feed.snapshot_events([original], 'url', {}, True)
        corrected = {**original, 'body': play('Correção do lance.')['body']}
        events = feed.snapshot_events([corrected], 'url', previous, False)
        refreshed = feed.snapshot_events([corrected], 'url', events, False)
        self.assertTrue(refreshed['ge:one']['speak'])
        self.assertTrue(refreshed['ge:one']['corrected'])

    def test_publish_updates_root_timestamp_for_radio_commentary(self):
        async def run():
            state = {'home': {'name': 'CRB'}, 'away': {'name': 'Sport Recife'}}
            async def broadcast():
                pass
            feed = GEFeed(state, broadcast)
            feed.generation = 1
            await feed.publish(1, ready=True, events=[], status='OK')
            self.assertIn('updated_at', state)
            self.assertIn('updated_at', state['ge'])
        asyncio.run(run())

    def test_recent_or_updated_events_are_spoken_even_if_session_started_later(self):
        feed = GEFeed({}, None)
        feed.started_at = datetime.now(timezone.utc)
        current = play(createdAt=(datetime.now(timezone.utc) - timedelta(seconds=20)).isoformat())
        events = feed.snapshot_events([current], 'url', {}, False)
        self.assertTrue(events['ge:one']['speak'])

    def test_live_textual_event_without_created_at_is_still_speaking(self):
        feed = GEFeed({}, None)
        current = play(createdAt=None, moment='24:00', text='AH! Zakaria desperdiça bom ataque do Monaco, ao demorar demais para tocar a bola.')
        events = feed.snapshot_events([current], 'url', {}, False)
        self.assertTrue(events['ge:one']['speak'])
        self.assertEqual(events['ge:one']['minute'], '24')


class NarrationChannelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        async def broadcast():
            pass
        self.channel = NarrationChannel(Path(self.temp.name), {}, broadcast)
        app = FastAPI()
        self.channel.install(app)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def test_settings_persist_and_interval_can_be_disabled(self):
        r = self.client.post('/api/narration/settings', json={"output": "obs", "enabled": True, "commentaryInterval": 0, "engagement": True})
        self.assertEqual(r.status_code, 200)
        new = NarrationChannel(Path(self.temp.name), {}, None)
        self.assertEqual(new.settings.output, "obs")
        self.assertEqual(new.settings.commentaryInterval, 0)
        self.assertFalse(new.settings.announceLineups)
        self.assertEqual(self.client.post('/api/narration/settings', json={"commentaryInterval": -1}).status_code, 422)

    def test_only_one_player_and_failover_after_expiry(self):
        a = LeaseRequest(client='a'*32, output='control')
        b = LeaseRequest(client='b'*32, output='control')
        with patch('backend.narration_channel.time.monotonic', return_value=100):
            self.assertTrue(self.channel.acquire(a)['granted'])
            self.assertFalse(self.channel.acquire(b)['granted'])
        with patch('backend.narration_channel.time.monotonic', return_value=107):
            self.assertTrue(self.channel.acquire(b)['granted'])
            self.assertFalse(self.channel.acquire(a)['granted'])

    def test_switch_output_waits_for_previous_owner_or_release(self):
        a = LeaseRequest(client='a'*32, output='control')
        b = LeaseRequest(client='b'*32, output='obs')
        self.assertTrue(self.channel.acquire(a)['granted'])
        self.client.post('/api/narration/settings', json={"output": "obs"})
        self.assertFalse(self.channel.acquire(a)['granted'])
        self.assertFalse(self.channel.acquire(b)['granted'])
        self.client.post('/api/narration/release', json=a.model_dump())
        self.assertTrue(self.channel.acquire(b)['granted'])


if __name__ == '__main__':
    unittest.main()
