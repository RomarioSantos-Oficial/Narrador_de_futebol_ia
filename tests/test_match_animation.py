import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright


class AnimationTests(unittest.TestCase):
    def test_new_goals_substitutions_restore_and_no_replay(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page()
            page.clock.install()
            page.set_content('<section id="matchLineups"><div id="matchLineupRows">FIELD</div></section>')
            for name in ('shared.js', 'formation.js', 'match-events.js', 'match-animation.js'):
                page.add_script_tag(path=str(Path('static', name).resolve()))
            page.evaluate('''() => {
                window.s={source:'ESPN',kickoff:'2026-09-27',phase:'in',minute:50,competition:'League',
                    appearance:{scene:'match'},home:{name:'Home',score:0},away:{name:'Away',score:0},
                    lineups:{home:{starters:[{id:'1',name:'Scorer',photo:'https://example.com/p.png'},
                        {id:'2',name:'Leaving'}],bench:[{id:'3',name:'Entering'}]}},
                    events:[{id:'old',kind:'goal',minute:'10',player:'Scorer',text:'Old goal'}]};
                matchAnimation.update(s);
            }''')
            self.assertEqual(page.locator('#matchAnimation').count(), 0)
            page.evaluate('''() => {s.home.score=1;s.events.unshift({id:'new',kind:'goal',minute:'50',player:'Scorer',text:'Goal <script>bad</script>'});matchAnimation.update(s)}''')
            self.assertEqual(page.locator('.moment-person strong').inner_text(), 'Scorer')
            self.assertEqual(page.locator('.moment-photo img').count(), 1)
            self.assertEqual(page.locator('#matchAnimation script').count(), 0)
            page.evaluate('matchAnimation.update(s)')
            self.assertEqual(page.locator('#matchAnimation').count(), 1)
            page.clock.fast_forward(9100)
            self.assertEqual(page.locator('#matchAnimation').count(), 0)
            self.assertEqual(page.locator('#matchLineupRows').inner_text(), 'FIELD')
            page.evaluate('''() => {
                s.lineups.home.starters[1].subbed_out=true;s.lineups.home.bench[0].subbed_in=true;
                s.events.unshift({id:'sub',kind:'substitution',minute:'50',side:'home',text:'Substitution',
                    players:[{id:'3',name:'Entering'},{id:'2',name:'Leaving'}]});matchAnimation.update(s);
            }''')
            self.assertEqual(page.locator('.out strong').inner_text(), 'Leaving')
            self.assertEqual(page.locator('.in strong').inner_text(), 'Entering')
            page.clock.fast_forward(7100)
            page.evaluate('matchAnimation.baseline=true;matchAnimation.update(s)')
            self.assertEqual(page.locator('#matchAnimation').count(), 0)
            page.evaluate('''() => {s.appearance.scene='bench';s.events.unshift({id:'hidden',kind:'goal',minute:'50'});matchAnimation.update(s);s.appearance.scene='match';matchAnimation.update(s)}''')
            self.assertEqual(page.locator('#matchAnimation').count(), 0)
            page.evaluate('''() => {s.events.unshift({id:'cancel-me',kind:'goal',minute:'50'});matchAnimation.update(s);s.home.score=0;matchAnimation.update(s)}''')
            self.assertEqual(page.locator('#matchAnimation').count(), 0)
            browser.close()
