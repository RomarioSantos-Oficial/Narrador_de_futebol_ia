"""Optional browser regression tests. Use a fake speech service: no audible playback."""
import importlib.util
from pathlib import Path
import unittest

EDGE = Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
BROWSER_AVAILABLE = importlib.util.find_spec('playwright') is not None and EDGE.exists()


@unittest.skipUnless(BROWSER_AVAILABLE, 'Requires Playwright and Microsoft Edge for browser checks')
class NarrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(executable_path=str(EDGE), headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.page.clock.install()
        self.page.add_script_tag(path=str(Path(__file__).resolve().parents[1] / 'static' / 'radio-commentary.js'))
        self.page.add_script_tag(path=str(Path(__file__).resolve().parents[1] / 'static' / 'narration.js'))
        self.page.evaluate("""() => {
            window.spoken=[]; window.canceled=0;
            window.fake={speak:u=>spoken.push(u),cancel:()=>canceled++};
            window.finish=()=>{const current=narrator.utterance;if(current)current.onend();};
            window.drain=()=>{for(let i=0;i<20&&narrator.utterance;i++)finish();};
            window.narrator=new MatchNarrator({synth:fake,Utterance:class {constructor(text){this.text=text;}}});
            narrator.configure({voice:{name:'Teste',lang:'pt-BR',localService:true},rate:1,volume:0});
            window.state={competition:'Liga',home:{name:'Casa',score:0},away:{name:'Fora',score:0},
                kickoff:'2026-09-12T14:00Z',phase:'in',status:'AO VIVO',events:[]};
        }""")

    def tearDown(self):
        self.page.close()

    def test_manual_lineups_after_match_ends_read_both_teams(self):
        result = self.page.evaluate("""() => {
            const players=team=>Array.from({length:11},(_,i)=>({name:team+' '+(i+1),number:String(i+1),position:i?'CD-L':'G'}));
            state.lineups={home:{starters:players('Casa')},away:{starters:players('Fora')}};
            state.phase='post';narrator.start(state);drain();
            const start=spoken.length;narrator.readLineups(state);drain();
            return spoken.slice(start).map(u=>u.text);
        }""")
        self.assertEqual(len(result), 8)
        self.assertTrue(any('Casa 11' in text for text in result))
        self.assertTrue(any('Fora 11' in text for text in result))
        self.assertTrue(any('zagueiro pela esquerda' in text for text in result))

    def test_manual_lineups_survive_settings_updates_with_auto_disabled(self):
        result = self.page.evaluate("""() => {
            const config={voice:{lang:'pt-BR',localService:true},style:'events',announceLineups:false};
            narrator.configure(config);narrator.start(state);drain();
            state.lineups={home:{starters:Array.from({length:11},(_,i)=>({name:'Titular '+(i+1),position:'G'}))}};
            const start=spoken.length;narrator.readLineups(state);
            for(let i=0;i<10;i++){narrator.configure(config);narrator.update(state);finish();}
            return spoken.slice(start).map(u=>u.text);
        }""")
        self.assertEqual(len(result), 4)
        self.assertTrue(any('Titular 11' in text for text in result))

    def test_manual_lineups_work_after_automatic_final_announcement_stops_voice(self):
        result = self.page.evaluate("""() => {
            state.lineups={home:{starters:[{name:'Goleiro Casa',position:'G'}]},away:{starters:[{name:'Goleiro Fora',position:'G'}]}};
            narrator.start(state);drain();state.phase='post';narrator.update(state);drain();
            const stopped=!narrator.enabled;
            narrator.readLineups(state);drain();
            return {stopped,texts:spoken.map(u=>u.text),enabled:narrator.enabled};
        }""")
        self.assertTrue(result['stopped'])
        self.assertTrue(any('Goleiro Fora' in text for text in result['texts']))
        self.assertFalse(result['enabled'])

    def test_ge_events_ignore_timer_history_duplicates_and_other_provider(self):
        result = self.page.evaluate("""() => {
            narrator.configure({voice:{lang:'pt-BR',localService:true},style:'radio',commentaryInterval:0});
            narrator.start(state);drain();
            state.ge={ready:true,session:'match1',events:[{id:'old',revision:'1',text:'Histórico antigo',editorial:true}]};
            narrator.update(state);drain();
            state.ge.events.unshift({id:'new',revision:'1',minute:'22',text:'Novo lance do GE',editorial:true,speak:true});
            state.events=[{id:'primary',text:'Lance duplicado da outra fonte'}];
            narrator.update(state);drain();narrator.update(state);drain();
            state.ge.events[0]={...state.ge.events[0],revision:'2',text:'Lance corrigido',corrected:true};
            narrator.update(state);drain();
            return spoken.map(x=>x.text);
        }""")
        self.assertEqual(sum('Novo lance do GE' in x for x in result), 1)
        self.assertFalse(any('Histórico antigo' in x or 'outra fonte' in x for x in result))
        self.assertTrue(any('Atualização do lance' in x for x in result))

    def test_ge_editorial_events_have_queue_priority_over_regular_events(self):
        result = self.page.evaluate("""() => {
            narrator.configure({voice:{lang:'pt-BR',localService:true},style:'radio',commentaryInterval:0});
            const normal = narrator.queuePriority({kind:'event',eventKey:'regular',text:'Lance normal'});
            const ge = narrator.queuePriority({kind:'event',editorial:true,eventKey:'ge',source:{name:'ge · tempo real'},text:'Lens chega bem pela direita'});
            return {normal,ge,prioritized:ge>normal};
        }""")
        self.assertTrue(result['prioritized'])
        self.assertGreater(result['ge'], result['normal'])

    def test_ge_kickoff_arriving_before_primary_phase_change_is_read_once(self):
        result = self.page.evaluate("""() => {
            state.phase='pre';state.minute=0;
            narrator.start(state);drain();
            state.ge={ready:true,session:'kickoff',events:[{
                id:'ge:kickoff',revision:'1',minute:'0',period:'1T',
                text:'Bola rolando. Começa o jogo!',editorial:true,speak:true,
                created_at:new Date(Date.now()-180000).toISOString()
            }]};
            narrator.update(state);drain();
            const beforePrimaryUpdate=spoken.filter(u=>u.text.includes('Bola rolando. Começa o jogo!')).length;
            narrator.update(state);drain();
            state.phase='in';narrator.update(state);drain();
            state.ge.ready=false;narrator.update(state);drain();
            state.ge.ready=true;narrator.update(state);drain();
            return {beforePrimaryUpdate,texts:spoken.map(u=>u.text)};
        }""")
        self.assertEqual(result['beforePrimaryUpdate'], 1)
        self.assertEqual(sum('Bola rolando. Começa o jogo!' in text for text in result['texts']), 1)

    def test_ge_event_waiting_over_45_seconds_is_not_lost(self):
        self.page.evaluate("""() => {
            narrator.start(state);drain();
            state.ge={ready:true,session:'match',events:[]};narrator.update(state);
            narrator.enqueue('Fala atual');
            state.ge.events=[{id:'ge:queued',revision:'1',minute:'0',
                text:'Bola rolando. Começa o jogo!',editorial:true,speak:true}];
            narrator.update(state);
        }""")
        self.page.clock.run_for(60000)
        result = self.page.evaluate("""() => {
            drain();narrator.update(state);drain();return spoken.map(u=>u.text);
        }""")
        self.assertEqual(sum('Bola rolando. Começa o jogo!' in text for text in result), 1)

    def test_live_ge_event_without_current_clock_is_not_marked_as_history(self):
        result = self.page.evaluate("""() => {
            narrator.configure({voice:{lang:'pt-BR',localService:true},style:'events',commentaryInterval:0});
            const event={id:'ge-1',minute:'27',text:'GE: passe em profundidade',editorial:true,speak:true};
            const liveState={phase:'in',status:'AO VIVO',events:[],ge:{ready:true,session:'match-1',events:[event]}};
            return {
                recent: narrator.recentInPlayEvent(event, liveState, 8),
                liveHistory: narrator.events(liveState).filter(e => !narrator.recentInPlayEvent(e, liveState, 8)).length,
                queueable: narrator.eventSpeech(event)
            };
        }""")
        self.assertTrue(result['recent'])
        self.assertEqual(result['liveHistory'], 0)
        self.assertIn('GE: passe em profundidade', result['queueable'])

    def test_same_live_event_is_not_spoken_twice_when_source_refreshes_id(self):
        result = self.page.evaluate("""() => {
            narrator.configure({voice:{lang:'pt-BR',localService:true},style:'events',commentaryInterval:0});
            narrator.start(state);drain();
            state.events=[{id:101,minute:'26',icon:'⚽',text:'Gol. Raphinha'}];
            narrator.update(state);drain();
            state.events=[{id:102,minute:'26',icon:'⚽',text:'Gol. Raphinha'}];
            narrator.update(state);drain();
            state.events=[{id:103,minute:'29',icon:'⚽',text:'Gol. João'}];
            narrator.update(state);drain();
            return spoken.map(x=>x.text);
        }""")
        self.assertEqual(sum('Gol. Raphinha' in x for x in result), 1)
        self.assertEqual(sum('Gol. João' in x for x in result), 1)

    def test_skip_lineups_and_optional_engagement_yield_to_events(self):
        self.page.evaluate("""() => {
            narrator.configure({voice:{lang:'pt-BR',localService:true},style:'radio',commentaryInterval:0,engagement:true,engagementInterval:300});
            narrator.start(state);drain();
            state.lineups={home:{starters:[{name:'Jogador Um',position:'Goleiro'}]}};
            narrator.readLineups(state);narrator.skipLineups();
            narrator.lastEngagementAt=Date.now()-301000;narrator.lastCommentAt=Date.now()-20000;
            narrator.tick(state);
        }""")
        self.assertEqual(self.page.evaluate('narrator.lineupQueue.length'), 0)
        self.assertIn('like', self.page.evaluate('narrator.utterance.text'))
        self.page.evaluate("""() => {state.events=[{id:'goal',icon:'⚽',text:'Gol. Jogador Dois'}];narrator.update(state);}""")
        self.assertEqual(self.page.evaluate('narrator.utteranceKind'), 'goal')

    def test_start_ignores_history_and_repeated_updates(self):
        result = self.page.evaluate("""() => {
            state.events=[{minute:'10',icon:'card',text:'Cartão amarelo. Jogador antigo'}];
            narrator.start(state);drain();
            narrator.update(state);narrator.update(state);
            state.events.unshift({minute:'15',icon:'card',text:'Cartão vermelho. João'});
            narrator.update(state);drain();narrator.update(state);
            return spoken.map(u=>u.text);
        }""")
        self.assertEqual(len(result), 2)
        self.assertNotIn('antigo', ' '.join(result))
        self.assertIn('João', result[-1])

    def test_start_replays_recent_in_play_events(self):
        result = self.page.evaluate("""() => {
            state.phase='in';state.minute='45';
            state.events=[{minute:'44',icon:'⚽',text:'Gol. Bruno'}];
            narrator.start(state);drain();
            return spoken.map(u=>u.text);
        }""")
        self.assertTrue(any('Gol. Bruno' in x for x in result))
        self.assertTrue(any('Bruno' in x for x in result))

    def test_stop_cancels_queue_and_pending_score(self):
        self.page.evaluate("""() => {
            narrator.start(state);drain();state.home.score=1;
            state.events=[{minute:20,text:'Gol. Jogador'}];
            narrator.update(state);narrator.stop();
            window.countAtStop=spoken.length;
        }""")
        self.page.clock.run_for(2000)
        self.assertEqual(self.page.evaluate('spoken.length'), self.page.evaluate('countAtStop'))
        self.assertFalse(self.page.evaluate('narrator.enabled'))
        self.assertGreater(self.page.evaluate('canceled'), 0)
        self.assertEqual(self.page.evaluate('narrator.queue.length'), 0)

    def test_switch_match_and_reconnect_do_not_replay_old_events(self):
        result = self.page.evaluate("""() => {
            narrator.start(state);drain();
            state.away.name='Outro';state.events=[{minute:1,text:'Evento antigo da nova partida'}];
            narrator.update(state);drain();narrator.update(state);
            narrator.disconnect();state.events.unshift({minute:2,text:'Evento durante a desconexão'});
            narrator.update(state);drain();
            state.events.unshift({minute:3,text:'Novo lance após reconectar'});
            narrator.update(state);drain();
            return spoken.map(u=>u.text);
        }""")
        self.assertEqual(len(result), 3)
        self.assertIn('Outro', result[1])
        self.assertIn('Novo lance', result[2])
        self.assertNotIn('antigo', ' '.join(result))
        self.assertNotIn('durante', ' '.join(result))

    def test_goal_and_score_only_once_then_final_result(self):
        self.page.evaluate("""() => {
            narrator.start(state);drain();state.home.score=1;narrator.update(state);
            state.events=[{minute:'45+2',icon:'⚽',text:'Gol · Maria'}];
            narrator.update(state);drain();narrator.update(state);
        }""")
        self.page.clock.run_for(1100)
        self.page.evaluate('drain()')
        spoken = self.page.evaluate('spoken.map(u=>u.text)')
        self.assertEqual(len(spoken), 3)
        self.assertIn('mais 2 de acréscimo', spoken[1])
        self.assertIn('Gol. Maria', spoken[1])
        self.assertIn('Casa, 1. Fora, 0.', spoken[2])
        self.page.evaluate("state.phase='post';narrator.update(state);drain();narrator.update(state)")
        self.assertEqual(self.page.evaluate('spoken.length'), 4)
        self.assertIn('Placar final', self.page.evaluate('spoken.at(-1).text'))

    def test_speech_error_stops_and_remote_voice_is_rejected(self):
        self.page.evaluate("narrator.start(state);narrator.utterance.onerror({error:'not-allowed'})")
        self.assertFalse(self.page.evaluate('narrator.enabled'))
        self.assertIn('bloqueou', self.page.evaluate('narrator.status'))
        self.assertTrue(self.page.evaluate("""() => {
            narrator.configure({voice:{lang:'pt-BR',localService:false}});
            try{narrator.start(state);return false;}catch{return true;}
        }"""))

    def test_new_events_are_spoken_in_chronological_order(self):
        result = self.page.evaluate("""() => {
            narrator.start(state);drain();
            state.events=[{minute:25,text:'Lance B'},{minute:24,text:'Lance A'}];
            narrator.update(state);drain();return spoken.map(u=>u.text);
        }""")
        self.assertIn('Lance A', result[1])
        self.assertIn('Lance B', result[2])

    def radio_start(self):
        self.page.evaluate("""() => {
            narrator.configure({voice:{lang:'pt-BR',localService:true},style:'radio',commentaryInterval:60,volume:0});
            state.source='ESPN';state.updated_at=new Date().toISOString();state.minute=20;
            state.stats={shots:[2,1],shots_on:[1,0],possession:[60,40],corners:[null,null]};
            narrator.start(state);drain();
        }""")

    def test_radio_only_comments_on_new_stats_from_recent_live_snapshot(self):
        self.radio_start()
        self.page.clock.run_for(61000)
        self.page.evaluate("state.updated_at=new Date().toISOString();narrator.update(state);drain()")
        self.assertEqual(self.page.evaluate('spoken.length'), 1)
        self.page.evaluate("state.stats.shots=[3,1];narrator.update(state);drain()")
        self.assertEqual(self.page.evaluate('spoken.length'), 2)
        self.assertIn('Casa tem 3', self.page.evaluate('spoken.at(-1).text'))
        self.page.clock.run_for(100000)
        self.page.evaluate("state.stats.shots=[4,1];narrator.update(state);drain()")
        self.assertEqual(self.page.evaluate('spoken.length'), 2)
        self.page.evaluate("state.updated_at=new Date().toISOString();state.status='INTERVALO';narrator.lastStatus='INTERVALO';narrator.update(state);drain()")
        self.assertEqual(self.page.evaluate('spoken.length'), 2)

    def test_missing_or_inconsistent_stats_are_not_spoken_as_facts(self):
        result = self.page.evaluate("""() => {
            state.stats={shots:[2,1],shots_on:[3,0],possession:[80,40],corners:[null,0]};
            state.clock_display="45'+2'";
            return {text:narrator.radio.snapshot(state),clock:narrator.radio.clock(state)};
        }""")
        self.assertNotIn('Escanteios', result['text'])
        self.assertNotIn('No gol', result['text'])
        self.assertNotIn('posse', result['text'])
        self.assertIn('mais 2 de acréscimo', result['clock'])

    def test_radio_panorama_can_repeat_as_periodic_commentary(self):
        result = self.page.evaluate("""() => {
            narrator.configure({voice:{lang:'pt-BR',localService:true},style:'radio',commentaryInterval:60,volume:0});
            narrator.start(state);drain();
            state.updated_at=new Date().toISOString();
            state.minute='28';
            state.stats={};
            narrator.lastCommentAt=Date.now()-61000;
            narrator.analysisCycle=0;
            narrator.tick(state);
            return narrator.queue.at(-1)?.text || '';
        }""")
        self.assertTrue('acompanha' in result.lower() or 'última atualização' in result.lower())

    def test_goal_interrupts_panorama_and_late_audio_callback_cannot_advance_queue(self):
        self.radio_start()
        result = self.page.evaluate("""() => {
            narrator.panorama(state);const old=narrator.utterance;
            state.home.score=1;state.events=[{minute:"45'+2'",icon:'⚽',text:'Gol · Maria'}];
            narrator.update(state);old.onend();
            return {text:narrator.utterance.text,canceled};
        }""")
        self.assertGreater(result['canceled'], 0)
        self.assertIn('É gol! Maria', result['text'])
        self.assertIn('mais 2 de acréscimo', result['text'])

    def test_host_pause_skips_intervening_events_then_resumes_new_ones(self):
        self.radio_start()
        result = self.page.evaluate("""() => {
            narrator.panorama(state);narrator.toggleHost(state);
            state.home.score=1;state.events=[{minute:22,icon:'⚽',text:'Gol durante comentário'}];
            narrator.update(state);narrator.toggleHost(state);narrator.update(state);drain();
            state.events.unshift({minute:24,text:'Cartão amarelo · João'});narrator.update(state);drain();
            return {texts:spoken.map(u=>u.text),paused:narrator.paused};
        }""")
        self.assertFalse(result['paused'])
        self.assertNotIn('durante comentário', ' '.join(result['texts']))
        self.assertIn('Cartão amarelo para João', result['texts'][-1])

    def test_source_switch_does_not_replay_other_providers_event_history(self):
        self.radio_start()
        result = self.page.evaluate("""() => {
            state.source='API-Football';state.events=[{minute:19,text:'Lance já ocorrido'}];
            narrator.update(state);drain();narrator.update(state);drain();
            return spoken.map(u=>u.text);
        }""")
        self.assertEqual(len(result), 2)
        self.assertNotIn('Lance já ocorrido', ' '.join(result))

    def test_canceled_local_request_never_plays_delayed_audio(self):
        self.page.add_script_tag(path=str(Path(__file__).resolve().parents[1] / 'static' / 'speech-output.js'))
        result = self.page.evaluate("""async () => {
            let respond,started=0,ended=0;
            const output=new SpeechOutput({native:null,fetcher:()=>new Promise(resolve=>respond=resolve)});
            output.context={state:'running',decodeAudioData:async()=>({}),createBufferSource:()=>({connect(){},start(){started++}})};
            const utterance={text:'Gol',voice:{engine:'piper'},rate:1,volume:0,onend:()=>ended++};
            output.speak(utterance);output.cancel();
            respond({ok:true,status:200,arrayBuffer:async()=>new ArrayBuffer(0)});
            await new Promise(resolve=>window.setTimeout(resolve,0));
            return {started,ended,current:output.current};
        }""")
        self.assertEqual(result, {'started': 0, 'ended': 0, 'current': None})

    def test_dynamic_delivery_varies_pace_without_cheering_canceled_goals(self):
        self.radio_start()
        result = self.page.evaluate("""() => {
            narrator.configure({voice:{lang:'pt-BR',localService:true},style:'radio',delivery:'dynamic',rate:1,volume:0});
            narrator.panorama(state);drain();const analysis=spoken.at(-1).rate;
            state.events=[{minute:25,icon:'⚽',text:'Gol · Maria'}];
            narrator.update(state);const goal={text:narrator.utterance.text,rate:narrator.utterance.rate,kind:narrator.utterance.kind};drain();
            state.events.unshift({minute:27,icon:'⚽',text:'Gol anulado pelo VAR'});
            narrator.update(state);const canceledGoal={text:narrator.utterance.text,rate:narrator.utterance.rate,kind:narrator.utterance.kind};
            return {analysis,goal,canceledGoal};
        }""")
        self.assertLess(result['analysis'], result['goal']['rate'])
        self.assertTrue(result['goal']['text'].startswith('É gol!'))
        self.assertEqual(result['goal']['kind'], 'goal')
        self.assertEqual(result['canceledGoal']['kind'], 'event')
        self.assertIn('anulado', result['canceledGoal']['text'])
        self.assertNotIn('É gol!', result['canceledGoal']['text'])

    def test_dynamic_preview_is_explicitly_a_test_and_does_not_enable_live_narration(self):
        result = self.page.evaluate("""() => {
            narrator.configure({voice:{lang:'pt-BR',localService:true},delivery:'dynamic',volume:0});
            narrator.preview();drain();return {texts:spoken.map(u=>u.text),enabled:narrator.enabled,previewing:narrator.previewing};
        }""")
        self.assertFalse(result['enabled'])
        self.assertFalse(result['previewing'])
        self.assertIn('teste', result['texts'][0])
        self.assertIn('exemplo', result['texts'][1])

    def test_voice_catalogue_supports_legacy_and_multiple_local_models(self):
        self.page.add_script_tag(path=str(Path(__file__).resolve().parents[1] / 'static' / 'speech-output.js'))
        result = self.page.evaluate("""async () => {
            const native={getVoices:()=>[]};
            const legacy=new SpeechOutput({native,fetcher:async()=>({ok:true,json:async()=>({available:true,engine:'piper',lang:'pt-BR',voiceURI:'piper:pt_BR-faber-medium'})})});
            await legacy.load();
            const modern=new SpeechOutput({native,fetcher:async()=>({ok:true,json:async()=>({voices:[{engine:'kokoro',lang:'pt-BR',voiceURI:'kokoro:pm_alex',apiVersion:2},{engine:'piper',voiceURI:'piper:pt_BR-faber-medium',apiVersion:2}]})})});
            await modern.load();return {legacy:legacy.getVoices().length,modern:modern.getVoices().length,kokoro:modern.isLocalAI(modern.getVoices()[0])};
        }""")
        self.assertEqual(result, {'legacy': 1, 'modern': 2, 'kokoro': True})

    def test_legacy_busy_retry_backs_off_and_cancel_stops_new_requests(self):
        self.page.add_script_tag(path=str(Path(__file__).resolve().parents[1] / 'static' / 'speech-output.js'))
        self.page.evaluate("""() => {
            window.requests=0;window.failed=0;
            window.output=new SpeechOutput({native:null,fetcher:async()=>{requests++;return {status:409,ok:false};}});
            output.context={state:'running'};
            output.speak({text:'Gol',voice:{engine:'piper'},rate:1,volume:0,onerror:()=>failed++});
        }""")
        self.page.clock.run_for(500)
        self.assertEqual(self.page.evaluate('requests'), 1)
        self.page.clock.run_for(300)
        self.assertEqual(self.page.evaluate('requests'), 2)
        self.page.evaluate('output.cancel()')
        self.page.clock.run_for(5000)
        self.assertEqual(self.page.evaluate('requests'), 2)
        self.assertEqual(self.page.evaluate('failed'), 0)

    def test_retry_respects_server_delay_and_clears_current_on_failure(self):
        self.page.add_script_tag(path=str(Path(__file__).resolve().parents[1] / 'static' / 'speech-output.js'))
        self.page.evaluate("""() => {
            window.requests=0;window.failed=0;
            window.output=new SpeechOutput({native:null,fetcher:async()=>{
                requests++;return {status:429,ok:false,headers:{get:()=> '2'},json:async()=>({detail:'Voice busy'})};
            }});
            output.context={state:'running'};
            output.speak({text:'Gol',voice:{engine:'piper'},rate:1,volume:0,onerror:()=>failed++});
        }""")
        self.page.clock.run_for(1800)
        self.assertEqual(self.page.evaluate('requests'), 1)
        self.page.clock.run_for(15000)
        self.assertEqual(self.page.evaluate('requests'), 6)
        self.assertEqual(self.page.evaluate('failed'), 1)
        self.assertIsNone(self.page.evaluate('output.current'))

    def test_separate_narrator_and_commentator_voices(self):
        result = self.page.evaluate("""() => {
            const a={lang:'pt-BR',localService:true,name:'Alex'},b={lang:'pt-BR',localService:true,name:'Dora'};
            narrator.configure({voice:a,commentaryVoice:b,style:'radio'});
            narrator.start(state);drain();
            state.events=[{id:'card',text:'Cartão amarelo. João'}];narrator.update(state);drain();
            narrator.preview({commentary:true});drain();
            return spoken.map(u=>u.voice.name);
        }""")
        self.assertEqual(result, ['Dora', 'Alex', 'Dora'])

    def test_late_brain_plan_after_stop_or_match_switch_never_speaks(self):
        self.page.evaluate("""() => {
            window.pending=[];narrator.compose=()=>new Promise(resolve=>pending.push(resolve));
            narrator.start(state);
        }""")
        self.page.evaluate('narrator.stop();pending[0]("Old plan");')
        self.assertEqual(self.page.evaluate('spoken.length'), 0)
        self.page.evaluate('narrator.start(state)')
        self.page.evaluate('state.away.name="Other";narrator.update(state)')
        self.page.evaluate('pending[1]("Old match");pending[2]("Current match");')
        self.assertEqual(self.page.evaluate('spoken.map(u=>u.text)'), ['Current match'])

    def test_goal_interrupts_pending_brain_panorama_and_final_drains(self):
        self.page.evaluate("""() => {
            window.pending=[];narrator.compose=()=>new Promise(resolve=>pending.push(resolve));
            narrator.configure({voice:{lang:'pt-BR',localService:true},style:'radio'});
            narrator.start(state);
        }""")
        self.page.evaluate('state.events=[{id:1,text:"Gol. João",icon:"⚽"}];narrator.update(state)')
        self.page.evaluate('pending[0]("Old panorama");pending[1]("Gol. João");')
        self.assertEqual(self.page.evaluate('spoken.map(u=>u.text)'), ['Gol. João'])
        self.page.evaluate('finish();state.phase="post";narrator.update(state);')
        self.page.evaluate('pending[2]("Partida encerrada.");')
        self.page.evaluate('drain()')
        self.assertFalse(self.page.evaluate('narrator.enabled'))
        self.assertEqual(self.page.evaluate('narrator.queue.length'), 0)
        self.assertIsNone(self.page.evaluate('narrator.composing'))

    def test_club_facts_repeat_only_after_ten_minutes_and_stop_at_full_time(self):
        self.page.evaluate("""() => {
            narrator.configure({voice:{lang:'pt-BR',localService:true},style:'radio',curiosities:true,commentaryInterval:30});
            narrator.start(state);drain();
            narrator.setContext(state,[{id:'founding',text:'Clube fundado em 1892.',source:{name:'TheSportsDB'}}]);
        }""")
        self.page.clock.run_for(31000)
        self.page.evaluate('narrator.tick();drain()')
        self.assertEqual(self.page.evaluate('spoken.length'), 2)
        self.page.clock.run_for(31000)
        self.page.evaluate('narrator.tick();drain()')
        self.assertEqual(self.page.evaluate('spoken.length'), 2)
        self.page.clock.run_for(600000)
        self.page.evaluate('narrator.tick();drain()')
        self.assertEqual(self.page.evaluate('spoken.length'), 3)
        self.page.evaluate('state.phase="post";narrator.update(state);drain()')
        self.page.clock.run_for(600000)
        self.page.evaluate('narrator.tick();drain()')
        self.assertEqual(self.page.evaluate('spoken.length'), 4)

    def test_lineups_read_eleven_per_side_once_and_resume_after_goal(self):
        self.page.evaluate("""() => {
            const players=prefix=>Array.from({length:11},(_,i)=>({id:prefix+i,name:prefix+' Player '+i,number:i+1,position:i===0?'GK':'CB'}));
            state.lineups={home:{starters:players('Home')},away:{starters:players('Away')}};
            narrator.configure({voice:{lang:'pt-BR',localService:true},announceLineups:true});
            narrator.start(state);finish();
            state.events=[{id:'goal',text:'Gol. Home Player 3',icon:'⚽'}];narrator.update(state);
        }""")
        self.assertIn('Gol.', self.page.evaluate('narrator.utterance.text'))
        self.page.clock.run_for(1100)
        self.page.evaluate('drain();narrator.update(state);drain()')
        texts = self.page.evaluate('spoken.map(u=>u.text)')
        for side in ['Home', 'Away']:
            for index in range(11):
                self.assertIn(f'{side} Player {index}, camisa', ' '.join(texts))
        self.assertIn('goleiro', ' '.join(texts))
        self.assertIn('zagueiro', ' '.join(texts))
        count = len(texts)
        self.page.evaluate('narrator.update(state);drain()')
        self.assertEqual(self.page.evaluate('spoken.length'), count)

    def test_goal_kept_when_event_queue_is_full(self):
        result = self.page.evaluate("""() => {
            narrator.start(state);
            for(let i=0;i<10;i++)narrator.enqueue('Other '+i);
            narrator.enqueue('Goal priority','goal');
            return narrator.queue.map(item=>item.text);
        }""")
        self.assertEqual(len(result), 8)
        self.assertEqual(result[0], 'Goal priority')
