import copy
import base64
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import uvicorn

from backend.appearance import Appearance
from tests.test_narration_browser import BROWSER_AVAILABLE


@unittest.skipUnless(BROWSER_AVAILABLE, 'Requires Edge and Playwright')
class VisualBrowserTests(unittest.TestCase):
    def test_saved_colors_reach_preview_and_open_overlay(self):
        import main
        from playwright.sync_api import sync_playwright

        original = copy.deepcopy(main.state)
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(main.appearance_store, 'path', Path(folder) / 'appearance.json'), \
                patch.object(main.appearance_store, 'base', Path(folder)), \
                patch.object(main.player_photos, 'path', Path(folder) / 'player_photos.json'), \
                patch.object(main.player_photos, 'base', Path(folder)), \
                patch.object(main.player_photos, 'photos', {}), \
                patch.object(main.ge_feed, 'observe'):
            (Path(folder) / 'static').mkdir()
            main.state.update(appearance=Appearance().model_dump(),
                              events=[{'minute': '50', 'text': 'Teste', 'icon': ''}],
                              ge={'ready': False},
                              lineups={'home': {'formation': '4-3-3', 'starters': [
                                  {'id': '1', 'number': '10', 'name': 'Jogador', 'position': 'F'}]}})
            sock = socket.socket()
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
            sock.close()
            server = uvicorn.Server(uvicorn.Config(main.app, host='127.0.0.1', port=port,
                                                  log_level='error', lifespan='off'))
            thread = threading.Thread(target=server.run, daemon=True)
            thread.start()
            try:
                for _ in range(100):
                    if server.started:
                        break
                    time.sleep(.05)
                with sync_playwright() as p:
                    browser = p.chromium.launch(channel='msedge', headless=True)
                    try:
                        overlay = browser.new_page()
                        overlay.goto(f'http://127.0.0.1:{port}/overlay')
                        overlay.wait_for_selector('.event-minute')
                        self.assertEqual(overlay.locator('#clock').evaluate('(e)=>getComputedStyle(e).color'), 'rgb(255, 255, 255)')
                        control = browser.new_page()
                        control.goto(f'http://127.0.0.1:{port}/control')
                        control.locator('[data-tab="visual"]').click()
                        control.wait_for_function('visualDraft !== null')
                        control.locator('#accent').evaluate('e=>{e.value="#ffff00";e.dispatchEvent(new Event("input",{bubbles:true}))}')
                        control.locator('#background_color').evaluate('e=>{e.value="#123456";e.dispatchEvent(new Event("input",{bubbles:true}))}')
                        control.locator('#background').select_option('solid')
                        for field, color in {'home_photo_color': '#ff0000', 'home_photo_secondary': '#0000ff',
                                             'formation_home_background': '#123456', 'formation_away_background': '#654321'}.items():
                            control.locator('#' + field).evaluate('(e,c)=>{e.value=c;e.dispatchEvent(new Event("input",{bubbles:true}))}', color)
                        self.assertTrue(control.locator('#home_custom_colors').is_checked())
                        self.assertFalse(control.locator('#away_custom_colors').is_checked())
                        control.locator('#saveVisual').click()
                        predicate = 'getComputedStyle(document.querySelector("#clock")).color === "rgb(255, 255, 0)"'
                        overlay.wait_for_function(predicate)
                        preview = control.locator('#preview').content_frame
                        # Both pages receive the same broadcast, without a reload.
                        preview.locator('#clock').wait_for()
                        control.wait_for_function('getComputedStyle(document.querySelector("#preview").contentDocument.querySelector("#clock")).color === "rgb(255, 255, 0)"')
                        for selector in ('#clock', '.event-minute', '.eyebrow', '#matchStatus'):
                            self.assertEqual(overlay.locator(selector).first.evaluate('(e)=>getComputedStyle(e).color'), 'rgb(255, 255, 0)')
                        self.assertEqual(overlay.locator('#backdrop').evaluate('(e)=>getComputedStyle(e).backgroundColor'), 'rgb(18, 52, 86)')
                        self.assertEqual(main.appearance_store.load()['accent'], '#ffff00')
                        control.locator('#background').select_option('transparent')
                        control.locator('#saveVisual').click()
                        overlay.wait_for_function('getComputedStyle(document.querySelector("#backdrop")).backgroundColor === "rgba(0, 0, 0, 0)"')
                        response = control.request.get(f'http://127.0.0.1:{port}/static/overlay.css')
                        self.assertEqual(response.headers.get('cache-control'), 'no-cache')
                        # Simulate an outdated iframe that cannot render the new scene.
                        control.locator('#preview').evaluate('e=>e.contentDocument.querySelector("#formationPanel").remove()')
                        control.locator('.scene-controls [data-scene="formation"]').click()
                        control.frame_locator('#preview').locator('#formationPanel').wait_for(state='visible')
                        self.assertIn('preview=', control.locator('#preview').get_attribute('src'))
                        self.assertEqual(main.state['appearance']['scene'], 'formation')
                        formation = control.frame_locator('#preview')
                        self.assertEqual(formation.locator('.formation-avatar').first.evaluate('(e)=>e.style.getPropertyValue("--team-primary")'), '#ff0000')
                        self.assertEqual(formation.locator('.formation-avatar').first.evaluate('(e)=>e.style.getPropertyValue("--team-secondary")'), '#0000ff')
                        self.assertEqual(formation.locator('#formationPanel .formation-half.home').evaluate('(e)=>getComputedStyle(e).backgroundColor'), 'rgb(18, 52, 86)')
                        self.assertEqual(formation.locator('#formationPanel .formation-half.away').evaluate('(e)=>getComputedStyle(e).backgroundColor'), 'rgb(101, 67, 33)')
                        self.assertEqual(main.appearance_store.load()['home_photo_color'], '#ff0000')
                        self.assertFalse(main.appearance_store.load()['away_custom_colors'])
                        control.locator('.scene-controls [data-scene="match"]').click()
                        control.frame_locator('#preview').locator('#matchPanels').wait_for(state='visible')
                        self.assertEqual(main.state['appearance']['scene'], 'match')
                        control.frame_locator('#preview').locator('#matchLineupRows .formation-board').wait_for(state='visible')
                        self.assertEqual(control.frame_locator('#preview').locator('#matchLineupRows .formation-half').count(), 2)
                        home_half = control.frame_locator('#preview').locator('#matchLineupRows .formation-half.home').bounding_box()
                        away_half = control.frame_locator('#preview').locator('#matchLineupRows .formation-half.away').bounding_box()
                        self.assertAlmostEqual(home_half['y'], away_half['y'], places=1)
                        self.assertLess(home_half['x'], away_half['x'])
                        # Upload a real decodable PNG through the player chooser.
                        control.locator('[data-tab="players"]').click()
                        png = base64.b64decode(control.evaluate('''() => {
                            const c=document.createElement('canvas');c.width=4;c.height=4;
                            c.getContext('2d').fillRect(0,0,4,4);return c.toDataURL('image/png').split(',')[1];
                        }'''))
                        control.context.route('**/static/uploads/*', lambda route: route.fulfill(content_type='image/png', body=png))
                        control.locator('#playerPhotoUpload').set_input_files({'name': 'portrait.png', 'mimeType': 'image/png', 'buffer': png})
                        control.wait_for_function('document.querySelector("#playerPhotoStatus").textContent.includes("enviada por")')
                        self.assertTrue((Path(folder) / 'player_photos.json').is_file())
                        control.locator('#controlStarters .formation-avatar img').wait_for()
                        control.locator('#controlStarters .formation-player').first.click()
                        control.locator('#playerInfoDialog').wait_for(state='visible')
                        control.locator('#playerInfoDialog button').click()
                        control.locator('.scene-controls [data-scene="lineups"]').click()
                        control.frame_locator('#preview').locator('#overlayLineups .formation-avatar img').wait_for(state='visible')
                        control.locator('#resetPlayerPhoto').click()
                        control.wait_for_function('!document.querySelector("#controlStarters .formation-avatar img")')
                        self.assertEqual(main.player_photos.photos, {})
                    finally:
                        browser.close()
            finally:
                server.should_exit = True
                thread.join(timeout=10)
                main.state.clear()
                main.state.update(original)
