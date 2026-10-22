"""Study invariants and authenticated integration, isolated from personal notes/Discord."""
import datetime as dt
import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import server
import study

SID = 'a' * 32
OTHER = 'b' * 32
AT = dt.datetime(2026, 10, 21, 12, tzinfo=dt.timezone.utc)

class StudyModelTest(unittest.TestCase):
    def start(self, at=AT):
        return study.apply(study.load(''), {'action':'start','id':SID,'course':'STAT 252','topic':'Probability'}, at)

    def test_exact_time_and_idempotent_retries(self):
        data = self.start()
        retry = study.apply(data, {'action':'start','id':SID,'course':'STAT 252','topic':'Probability'}, AT+dt.timedelta(minutes=1))
        self.assertEqual(retry, data)
        data = study.apply(data, {'action':'stop','id':SID}, AT+dt.timedelta(seconds=90))
        self.assertEqual(study.view(data, AT)['sessions'][0]['duration_seconds'], 90)
        self.assertEqual(study.apply(data, {'action':'stop','id':SID}, AT+dt.timedelta(minutes=5)), data)

    def test_one_active_session_and_stale_stop_cannot_stop_another(self):
        data = self.start()
        with self.assertRaises(ValueError):
            study.apply(data, {'action':'start','id':OTHER,'course':'CISC','topic':'Trees'}, AT)
        data = study.apply(data, {'action':'stop','id':SID}, AT+dt.timedelta(seconds=60))
        data = study.apply(data, {'action':'start','id':OTHER,'course':'CISC','topic':'Trees'}, AT+dt.timedelta(seconds=61))
        retry = study.apply(data, {'action':'stop','id':SID}, AT+dt.timedelta(seconds=90))
        self.assertEqual(study.active(retry)['id'], OTHER)

    def test_restart_or_missing_checkins_require_explicit_recovery(self):
        data = self.start()
        with patch.object(study, 'RUN', 'new-process'):
            self.assertTrue(study.view(data, AT)['active']['interrupted'])
        later = AT+dt.timedelta(hours=3)
        view = study.view(data, later)
        self.assertTrue(view['active']['interrupted'])
        self.assertEqual(view['active']['duration_seconds'], 0)
        with self.assertRaises(ValueError):
            study.apply(data, {'action':'heartbeat','id':SID}, later)
        ended = study.apply(data, {'action':'stop','id':SID}, later)
        self.assertEqual(study.view(ended, later)['sessions'][0]['duration_seconds'], 0)
        confirmed = study.apply(data, {'action':'continue','id':SID}, later)
        self.assertFalse(study.view(confirmed, later)['active']['interrupted'])
        self.assertEqual(study.view(confirmed, later)['active']['duration_seconds'], 10800)

    def test_user_finish_time_and_timezone_offsets(self):
        data = self.start()
        body = {'action':'stop','id':SID,'ended_at':'2026-10-21T08:45:00-04:00'}
        data = study.apply(data, body, AT+dt.timedelta(hours=2))
        self.assertEqual(study.view(data)['sessions'][0]['duration_seconds'], 2700)
        with self.assertRaises(ValueError):
            study.apply(data, {'action':'correct_end','id':SID,'ended_at':'2026-10-21T11:59:00Z'}, AT+dt.timedelta(hours=2))
        with self.assertRaises(ValueError):
            study.instant('2026-10-21T12:00:00')

    def test_correction_cannot_overlap_later_session(self):
        data = study.apply(self.start(), {'action':'stop','id':SID}, AT+dt.timedelta(seconds=60))
        data = study.apply(data, {'action':'start','id':OTHER,'course':'CISC','topic':'Trees'}, AT+dt.timedelta(seconds=61))
        with self.assertRaises(ValueError):
            study.apply(data, {'action':'correct_end','id':SID,'ended_at':study.stamp(AT+dt.timedelta(seconds=62))}, AT+dt.timedelta(seconds=90))

    def observation(self, data, oid, at=AT, outcome='independent'):
        return study.apply(data, {'action':'observe','id':oid,'session_id':SID,'revision':data['revision'], 'topic':'Conditional intersections','outcome':outcome,'evidence':'Recognized A is a subset of B and explained why the intersection is A.','source':'Question 2'}, at)

    def test_evidence_requires_existing_session_and_current_revision(self):
        data = self.start()
        with self.assertRaises(ValueError):
            study.apply(data, {'action':'observe','id':OTHER,'session_id':SID,'revision':0,'topic':'Sets','outcome':'independent','evidence':'Actual attempt'}, AT)
        with self.assertRaises(ValueError):
            study.apply(data, {'action':'observe','id':OTHER,'session_id':'c'*32,'revision':1,'topic':'Sets','outcome':'independent','evidence':'Actual attempt'}, AT)
        saved = self.observation(data, OTHER)
        self.assertEqual(len(saved['observations']),1)
        self.assertEqual(study.apply(saved, {'action':'observe','id':OTHER}, AT), saved)

    def test_profile_needs_repeated_spaced_evidence_and_retraction_updates_it(self):
        data = self.start()
        for n in range(3):
            data = self.observation(data, ('%032x' % n), AT+dt.timedelta(days=n))
        node = study.genome(data, AT+dt.timedelta(days=3))[0]
        self.assertEqual(node['status'], 'demonstrated')
        data = study.apply(data, {'action':'retract','id':'%032x'%0,'revision':data['revision']}, AT+dt.timedelta(days=3))
        self.assertEqual(study.genome(data, AT+dt.timedelta(days=3))[0]['status'], 'developing')
        self.assertEqual(len(data['observations']),3)
        self.assertIsNotNone(data['observations'][0]['retracted_at'])
        self.assertEqual(study.genome(data, AT+dt.timedelta(days=30))[0]['confidence'],'low')

    def test_same_day_repetition_does_not_mark_demonstrated(self):
        data=self.start()
        for n in range(3):
            data=self.observation(data,'%032x'%n,AT+dt.timedelta(seconds=n))
        self.assertEqual(study.genome(data,AT)[0]['status'],'developing')

    def test_recent_struggle_changes_assessment_and_heartbeat_keeps_revision(self):
        data=self.start()
        data=self.observation(data,OTHER,outcome='struggled')
        self.assertEqual(study.genome(data,AT)[0]['status'],'needs practice')
        heartbeat=study.apply(data,{'action':'heartbeat','id':SID},AT+dt.timedelta(seconds=30))
        self.assertEqual(heartbeat['revision'],data['revision'])
        self.assertEqual(heartbeat['changes'],data['changes'])

class StudyIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old=server.NOTES
        server.NOTES=self.tmp.name
        self.discord=patch.object(server.study_discord,'change',return_value={'state':'unavailable','message':'Discord closed'})
        self.discord.start()
    def tearDown(self):
        self.discord.stop()
        server.NOTES=self.old
        server.TOUCHED.clear()
        self.tmp.cleanup()

    def test_persists_before_adapter_call_and_round_trips_log(self):
        def adapter(*args):
            self.assertTrue(Path(self.tmp.name,'study/state.json').exists())
            return {'state':'dnd','previous':'invisible','message':'DND set'}
        with patch.object(server.study_discord,'change',side_effect=adapter):
            result=server.act_study({'action':'start','id':SID,'course':'STAT','topic':'Trees | <test>'})
        self.assertEqual(result['active']['discord']['previous'],'invisible')
        with patch.object(server.study_discord,'change',return_value={'state':'unavailable','message':'Closed'}):
            result=server.act_study({'action':'stop','id':SID})
        self.assertEqual(result['sessions'][0]['discord']['state'],'restore_failed')
        self.assertEqual(result['sessions'][0]['discord']['previous'],'invisible')
        self.assertIn('Trees \\| <test>',server.read('study/log.md'))
        self.assertIsNone(server.study_state()['active'])

    def test_retry_preserves_original_status_and_manual_choice(self):
        with patch.object(server.study_discord,'change',return_value={'state':'unverified','previous':'invisible','message':'Check status'}):
            server.act_study({'action':'start','id':SID,'course':'STAT','topic':'Sets'})
        with patch.object(server.study_discord,'change',return_value={'state':'dnd','previous':'dnd','message':'Confirmed'}):
            result=server.act_study({'action':'discord_retry','id':SID})
        self.assertEqual(result['active']['discord']['previous'],'invisible')
        with patch.object(server.study_discord,'change',return_value={'state':'unchanged','message':'Manual choice retained'}):
            result=server.act_study({'action':'stop','id':SID})
        self.assertEqual(result['sessions'][0]['discord']['state'],'unchanged')

    def test_study_assets_served(self):
        srv=server.Server(('127.0.0.1',0),server.Handler)
        threading.Thread(target=srv.serve_forever,daemon=True).start()
        try:
            conn=http.client.HTTPConnection('127.0.0.1',srv.server_address[1])
            for asset in ['/study.js','/study.css']:
                conn.request('GET',asset)
                response=conn.getresponse()
                self.assertEqual(response.status,200)
                self.assertTrue(response.read())
            conn.close()
        finally:
            srv.shutdown();srv.server_close()

    def test_authenticated_http_flow_and_heartbeat_does_not_commit(self):
        srv=server.Server(('127.0.0.1',0),server.Handler)
        threading.Thread(target=srv.serve_forever,daemon=True).start()
        def call(method,body=None,authed=True,host=None):
            conn=http.client.HTTPConnection('127.0.0.1',srv.server_address[1])
            headers={'Content-Type':'application/json'}
            if authed:headers['X-Brain-Token']=server.TOKEN
            if host:headers['Host']=host
            conn.request(method,'/api/study',json.dumps(body) if body else None,headers)
            response=conn.getresponse()
            result=response.status,json.loads(response.read())
            conn.close()
            return result
        try:
            self.assertEqual(call('GET',authed=False)[0],403)
            self.assertEqual(call('GET',host='evil.example')[0],403)
            with patch.object(server.SYNC,'commit') as commit:
                code,result=call('POST',{'action':'start','id':SID,'course':'STAT','topic':'Sets'})
                self.assertEqual(code,200)
                self.assertEqual(result['study']['active']['id'],SID)
                commit.reset_mock()
                self.assertEqual(call('POST',{'action':'heartbeat','id':SID})[0],200)
                commit.assert_not_called()
                self.assertEqual(call('POST',{'action':'start','id':OTHER,'course':'CISC','topic':'Trees'})[0],400)
                self.assertEqual(call('POST',{'action':'stop','id':SID})[0],200)
            self.assertIsNone(call('GET')[1]['active'])
        finally:
            srv.shutdown();srv.server_close()

if __name__=='__main__':
    unittest.main()
