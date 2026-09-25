import unittest
from pathlib import Path

from tests.test_narration_browser import BROWSER_AVAILABLE


@unittest.skipUnless(BROWSER_AVAILABLE, 'Requires Edge and Playwright')
class CurrentLineupTests(unittest.TestCase):
    def test_formation_replacement_chain_and_unavailable_positions(self):
        from playwright.sync_api import sync_playwright
        base = Path(__file__).resolve().parents[1]
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page()
            page.add_script_tag(path=str(base / 'static/shared.js'))
            page.add_script_tag(path=str(base / 'static/formation.js'))
            result = page.evaluate('''() => {
                const starters=Array.from({length:11},(_,i)=>({id:String(i),name:'Starter '+i,
                    position:i===0?'G':i<5?'CB':i<8?'CM':'F',formation_place:i+1}));
                const l={formation:'4-3-3',starters,bench:[]};
                const before=formationSlots(l);
                starters[10].subbed_out=true;starters[10].replacement_id='12';
                l.bench.push({id:'12',name:'Pedro',subbed_in:true});
                const after=formationSlots(l);
                l.bench[0].subbed_out=true;l.bench[0].replacement_id='13';
                l.bench.push({id:'13',name:'Next',subbed_in:true});
                const second=formationSlots(l);
                starters[2].red=1;
                const red=formationSlots(l);
                l.bench.push({id:'14',name:'Unused'}, {id:'15',name:'Dismissed',red:1});
                return {before:before.slots.length,after:after.slots.length,
                    old:before.slots.find(p=>p.player.id==='10'),
                    replacement:after.slots.find(p=>p.player.id==='12'),
                    second:second.slots.some(p=>p.player.id==='13'),red:red.slots.length,
                    missing:formationSlots({...l,formation:''}).unplaced.length,
                    photo:formationPhoto('javascript:alert(1)'),
                    bench:benchPlayers(l).map(p=>p.name),emptyBench:benchPlayers({})};
            }''')
            browser.close()
        self.assertEqual(result['before'], 11)
        self.assertEqual(result['after'], 11)
        self.assertEqual(result['old']['x'], result['replacement']['x'])
        self.assertEqual(result['old']['y'], result['replacement']['y'])
        self.assertTrue(result['second'])
        self.assertEqual(result['red'], 10)
        self.assertEqual(result['missing'], 10)
        self.assertEqual(result['photo'], '')
        self.assertEqual(result['bench'], ['Unused'])
        self.assertEqual(result['emptyBench'], [])

    def test_substitutions_dismissals_and_original_lineup(self):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page()
            page.add_script_tag(path=str(Path(__file__).resolve().parents[1] / 'static/shared.js'))
            result = page.evaluate('''() => {
                const lineup = {starters: [{name:'Estevao'}, {name:'Hugo'}],
                    bench:[{name:'Pedro'}, {name:'Unused'}, {name:'Replacement'}]};
                const names = () => currentPlayers(lineup).map(p => p.name);
                const before = names();
                lineup.starters[0].subbed_out = true;
                lineup.bench[0].subbed_in = true;
                const after = names();
                const state = {home:{name:'Brazil'}, away:{name:'Australia'},
                    lineups:{home:lineup}};
                const html = lineupHTML(state, 'field');
                lineup.bench[0].subbed_out = true;
                lineup.bench[2].subbed_in = true;
                const second = names();
                lineup.starters[1].red = 1;
                return {before, after, second, dismissed:names(), html,
                    original:lineup.starters.map(p=>p.name), empty:currentPlayers({})};
            }''')
            browser.close()
            self.assertEqual(result['before'], ['Estevao', 'Hugo'])
            self.assertEqual(result['after'], ['Hugo', 'Pedro'])
            self.assertEqual(result['second'], ['Hugo', 'Replacement'])
            self.assertEqual(result['dismissed'], ['Replacement'])
            self.assertEqual(result['original'], ['Estevao', 'Hugo'])
            self.assertEqual(result['empty'], [])
            self.assertIn('Pedro', result['html'])
            self.assertNotIn('Estevao', result['html'])
            self.assertNotIn('Unused', result['html'])
