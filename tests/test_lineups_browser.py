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
        self.assertEqual(result['bench'], ['Pedro', 'Unused', 'Dismissed', 'Starter 2', 'Starter 10'])
        self.assertEqual(result['emptyBench'], [])

    def test_bench_name_icons_and_coach(self):
        from playwright.sync_api import sync_playwright
        base = Path(__file__).resolve().parents[1]
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page()
            for name in ('shared.js', 'formation.js'):
                page.add_script_tag(path=str(base / 'static' / name))
            result = page.evaluate('''() => {
                const player={id:'1',name:'Scorer',subbed_out:true,yellow:1,
                    match_stats:{totalGoals:2,goalAssists:1}};
                const s={home:{name:'Home',color:'#ffcc00',alternate_color:'#006633'},away:{name:'Away'},
                    lineups:{home:{starters:[player],bench:[]}},
                    ge:{ready:true,coaches:{home:{name:'Coach <test>',source:'GE'}}}};
                document.body.innerHTML=formationBenchHTML(s);
                const result={name:document.querySelector('.formation-name').textContent,
                    goals:document.querySelector('.formation-goals').textContent,
                    yellow:document.querySelectorAll('.formation-avatar .formation-yellow').length,
                    status:document.querySelector('.formation-player-status').textContent,
                    coach:document.querySelector('.formation-coach strong').textContent,
                    injected:document.querySelectorAll('test').length,
                    primary:document.querySelector('.formation-avatar').style.getPropertyValue('--team-primary'),
                    secondary:document.querySelector('.formation-avatar').style.getPropertyValue('--team-secondary'),
                    fallback:formationTeamColors({color:'red;display:none'}),
                    awayIndependent:formationTeamColors({color:'#992242',alternate_color:'#ffffff'},
                        {home_custom_colors:true,home_photo_color:'#ffffff',home_photo_secondary:'#ff0000'},'away')};
                player.red=1;
                document.body.innerHTML=formationBenchHTML(s);
                result.red=document.querySelectorAll('.formation-avatar .formation-red').length;
                result.dismissed=document.querySelector('.formation-player-status').textContent;
                player.injured=true;
                document.body.innerHTML=formationBenchHTML(s);
                result.injury=document.querySelectorAll('.formation-avatar .formation-injury').length;
                result.out=document.querySelectorAll('.formation-avatar .formation-sub-out').length;
                player.subbed_out=false;player.subbed_in=true;player.red=0;player.injured=false;
                document.body.innerHTML=formationPlayer(s,player,'home');
                result.entered=document.querySelectorAll('.formation-avatar .formation-sub-in').length;
                result.noInjury=document.querySelectorAll('.formation-injury').length;
                return result;
            }''')
            browser.close()
        self.assertEqual(result['goals'], '⚽⚽')
        self.assertEqual(result['yellow'], 1)
        self.assertEqual(result['red'], 1)
        self.assertEqual(result['status'], 'Saiu')
        self.assertEqual(result['dismissed'], 'Expulso')
        self.assertEqual(result['coach'], 'Coach <test>')
        self.assertEqual(result['injected'], 0)
        self.assertEqual(result['primary'], '#ffcc00')
        self.assertEqual(result['secondary'], '#006633')
        self.assertEqual(result['fallback'], '--team-primary:#d9e6df;--team-secondary:#d9e6df')
        self.assertEqual(result['awayIndependent'], '--team-primary:#992242;--team-secondary:#ffffff')
        self.assertEqual(result['injury'], 1)
        self.assertEqual(result['out'], 1)
        self.assertEqual(result['entered'], 1)
        self.assertEqual(result['noInjury'], 0)

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
