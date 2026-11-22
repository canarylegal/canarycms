"""Synthetic-only reporter and real loopback TLS tests; no Core configuration is used."""
from datetime import datetime, timezone
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

SCRIPT = Path(__file__).parents[1]/'monitoring_delivery.py'
spec = importlib.util.spec_from_file_location('monitoring_delivery', SCRIPT)
m = importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
NOW = 1800000000

class Fixture:
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.config={'enabled':True,'endpoint':'https://localhost/observe','installation_id':'f2db25ec-83e0-4617-87a2-968f45cb3512',
          'state_dir':str(self.root/'state'),'report_file':str(self.root/'health.json'),'token_file':str(self.root/'token'),
          'expected_checks':['application','database','storage','onlyoffice','public_access']}
        Path(self.config['token_file']).write_text('synthetic-secret-123456789');Path(self.config['token_file']).chmod(0o600)
        self.path=self.root/'config.json';self.write_config();self.report()
    def tearDown(self):self.tmp.cleanup()
    def write_config(self):self.path.write_text(json.dumps(self.config));self.path.chmod(0o600)
    def report(self, now=NOW, **changes):
        checks={n:{'status':'ok','secret':'NEVER-SEND-provider-token'} for n in ('database','storage','onlyoffice','public_access')}
        checks.update({n:{'status':v} for n,v in changes.items()})
        Path(self.config['report_file']).write_text(json.dumps({'checked_at':datetime.fromtimestamp(now,timezone.utc).isoformat(),'checks':checks}))
    def state(self):return json.loads((self.root/'state/state.json').read_text())
    def good(self,c,e):m.validate_event(e);return {'status':204}
    def bad(self,c,e):return {'status':503,'retry_after':60}
class ReporterTests(Fixture, unittest.TestCase):
    def test_missing_or_disabled_config_does_nothing(self):
        self.assertIsNone(m.settings(None));self.assertIsNone(m.settings(self.root/'absent'))
        self.path.write_text('{"enabled": false, "endpoint": "http://invalid"}')
        self.assertIsNone(m.settings(self.path));self.assertFalse((self.root/'state').exists())
    def test_enabled_config_requires_https_and_private_secret(self):
        for endpoint in ['http://localhost','https://u:p@localhost','https://localhost/?token=x','https://localhost/#x']:
            self.config['endpoint']=endpoint;self.write_config()
            with self.assertRaises(ValueError):m.settings(self.path)
        self.config['endpoint']='https://localhost';self.write_config();Path(self.config['token_file']).chmod(0o644)
        with self.assertRaises(ValueError):m.settings(self.path)
    def test_disabled_cli_succeeds_without_creating_state(self):
        result=subprocess.run([sys.executable,str(SCRIPT)],capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(result.stdout),{'status':'disabled'})
    def test_bad_config_cli_is_sanitized(self):
        self.config['endpoint']='http://NEVER-SEND-secret';self.write_config()
        result=subprocess.run([sys.executable,str(SCRIPT),'--config',str(self.path)],capture_output=True,text=True)
        self.assertEqual(result.returncode,1);self.assertNotIn('NEVER-SEND',result.stdout+result.stderr)
    def test_redacted_observation_then_heartbeat(self):
        sent=[]
        def send(c,e):sent.append(e);return self.good(c,e)
        result=m.run(self.config,NOW,send)
        self.assertEqual(result['status'],'ok');self.assertEqual([e['kind'] for e in sent],['observation','heartbeat'])
        self.assertNotIn('NEVER-SEND',json.dumps(sent));self.assertEqual(sent[0]['checks']['backup'],'disabled')
        self.assertEqual(sent[0]['checks']['application'],'up')
    def test_service_failure_does_not_suppress_dispatcher_heartbeat(self):
        self.report(database='failed');sent=[]
        def send(c,e):sent.append(e);return self.good(c,e)
        self.assertTrue(m.run(self.config,NOW,send)['heartbeat_delivered'])
        self.assertEqual(sent[0]['checks']['database'],'down')
    def test_stale_missing_future_and_malformed_source_withhold_heartbeat(self):
        for text in ['{}','[]','broken',json.dumps({'checked_at':'bad','checks':{}})]:
            Path(self.config['report_file']).write_text(text)
            self.assertFalse(m.run(self.config,NOW,self.good)['heartbeat_delivered'])
        for when in [NOW-601,NOW+1]:
            self.report(now=when);self.assertFalse(m.run(self.config,NOW,self.good)['source_fresh'])
        Path(self.config['report_file']).unlink();self.assertFalse(m.run(self.config,NOW,self.good)['source_fresh'])
    def test_missing_required_check_is_unknown(self):
        self.report();report=json.loads(Path(self.config['report_file']).read_text());del report['checks']['database']
        Path(self.config['report_file']).write_text(json.dumps(report))
        self.assertEqual(m.observation(self.config,NOW)['checks']['database'],'unknown')
    def test_persist_before_send_and_restart_retry_keeps_id(self):
        def fail(c,e):self.assertEqual(self.state()['outbox'][0]['event']['event_id'],e['event_id']);return self.bad(c,e)
        m.run(self.config,NOW,fail);event=self.state()['outbox'][0]['event']
        calls=[]
        def send(c,e):calls.append(e);return self.good(c,e)
        m.run(self.config,NOW+1,send);self.assertFalse(calls)
        m.run(self.config,NOW+60,send);self.assertEqual(calls[0],event);self.assertFalse(self.state()['outbox'])
    def test_repeated_observation_is_not_requeued(self):
        m.run(self.config,NOW,self.good);before=self.state()['sequence'];m.run(self.config,NOW+5,self.good)
        self.assertEqual(self.state()['sequence'],before)
    def test_queue_is_bounded_and_full_is_explicit(self):
        for i in range(100):self.report(NOW+i);m.run(self.config,NOW+i,self.bad)
        self.report(NOW+101);result=m.run(self.config,NOW+101,self.bad)
        self.assertEqual(result['queued'],100);self.assertEqual(result['error'],'queue_full')
        self.assertLess((self.root/'state/state.json').stat().st_size,m.MAX_STATE)
    def test_batch_delivery_is_bounded_and_no_heartbeat_until_drained(self):
        for i in range(7):self.report(NOW+i);m.run(self.config,NOW+i,self.bad)
        result=m.run(self.config,NOW+300,self.good)
        self.assertEqual(result['delivered'],5);self.assertEqual(result['queued'],2);self.assertFalse(result['heartbeat_delivered'])
    def test_destination_change_refuses_existing_queue(self):
        m.run(self.config,NOW,self.bad);self.config['endpoint']='https://other.example/events'
        with self.assertRaises(ValueError):m.run(self.config,NOW+60,self.good)
    def test_corrupt_state_is_not_silently_reset(self):
        m.run(self.config,NOW,self.bad);(self.root/'state/state.json').write_text('broken')
        with self.assertRaises(ValueError):m.run(self.config,NOW,self.good)
    def test_injected_payload_field_is_rejected_on_restart(self):
        m.run(self.config,NOW,self.bad);s=self.state();s['outbox'][0]['event']['raw_secret']='NEVER-SEND'
        (self.root/'state/state.json').write_text(json.dumps(s))
        with self.assertRaises(ValueError):m.run(self.config,NOW+300,self.good)
    def test_private_state_and_lock(self):
        with m.locked(self.config):
            with self.assertRaises(BlockingIOError):m.run(self.config,NOW,self.good)
        m.run(self.config,NOW,self.good)
        self.assertEqual((self.root/'state/state.json').stat().st_mode&0o777,0o600)
    def test_symlinks_and_oversize_input_rejected(self):
        (self.root/'link').symlink_to(self.path)
        with self.assertRaises(OSError):m.read_file(self.root/'link',m.MAX_INPUT)
        with self.assertRaises(ValueError):m.read_file(self.path,1)
    def test_auth_rejection_retains_queue(self):
        result=m.run(self.config,NOW,lambda c,e:{'status':401})
        self.assertEqual(result['error'],'authentication_rejected');self.assertEqual(result['queued'],1)
    def test_heartbeat_failure_does_not_replay_acknowledged_observation(self):
        result=m.run(self.config,NOW,lambda c,e:{'status':204 if e['kind']=='observation' else 500})
        self.assertEqual(result['error'],'heartbeat_failed');self.assertFalse(self.state()['outbox'])
    def test_disconnect_leaves_queue_intact_without_attempting_delivery(self):
        m.run(self.config,NOW,self.bad);before=(self.root/'state/state.json').read_bytes()
        self.config['enabled']=False;self.write_config();self.assertIsNone(m.settings(self.path))
        self.assertEqual((self.root/'state/state.json').read_bytes(),before)

    def test_replayed_old_source_does_not_restore_health(self):
        m.run(self.config,NOW,self.good);self.report(NOW-5)
        result=m.run(self.config,NOW+1,self.good)
        self.assertFalse(result['source_fresh']);self.assertFalse(result['heartbeat_delivered'])
        self.report(NOW+2);self.assertTrue(m.run(self.config,NOW+2,self.good)['source_fresh'])
    def test_source_that_ages_during_delivery_cannot_send_heartbeat(self):
        self.report(NOW-599)
        with patch.object(m.time,'monotonic',side_effect=[0,3,3]):
            result=m.run(self.config,NOW,self.good)
        self.assertFalse(result['heartbeat_delivered']);self.assertFalse(result['source_fresh'])

    def test_interrupted_save_reuses_one_bounded_scratch_file(self):
        m.run(self.config,NOW,self.bad)
        scratch=self.root/'state/state.tmp';scratch.write_text('incomplete prior write')
        m.run(self.config,NOW+60,self.good)
        self.assertFalse(scratch.exists());self.assertFalse(self.state()['outbox'])
        self.assertEqual({p.name for p in (self.root/'state').iterdir()},{'lock','state.json'})
    def test_emitted_shapes_match_published_contract(self):
        schema=json.loads((SCRIPT.parents[1]/'docs/contracts/monitoring-v1.schema.json').read_text())
        sent=[]
        def send(c,e):sent.append(e);return self.good(c,e)
        m.run(self.config,NOW,send)
        for event in sent:
            variant=next(v for v in schema['oneOf'] if v['properties']['kind']['const']==event['kind'])
            self.assertEqual(set(event),set(variant['required']))
            if event['kind']=='observation':
                check_spec=variant['properties']['checks']
                self.assertEqual(set(event['checks']),set(check_spec['required']))
                for k,v in event['checks'].items():self.assertIn(v,check_spec['properties'][k]['enum'])

    def test_boolean_protocol_version_is_not_an_integer_version(self):
        m.run(self.config,NOW,self.bad);s=self.state();s['outbox'][0]['event']['schema_version']=True
        with self.assertRaises(ValueError):m.validate_state(s,self.config)

    def test_network_deadline_includes_child_process_stall(self):
        with patch.object(m.subprocess,'run',side_effect=subprocess.TimeoutExpired('synthetic',6)) as call:
            result=m.transport(self.config,{})
        self.assertEqual(result['status'],0);self.assertEqual(call.call_args.kwargs['timeout'],6)

class TLSTests(Fixture, unittest.TestCase):
    # Reuse fixture helpers, without inheriting/repeating all base test cases.
    @classmethod
    def setUpClass(cls):
        cls.certdir=tempfile.TemporaryDirectory();p=Path(cls.certdir.name);cls.cert=p/'cert.pem';key=p/'key.pem'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cls.cert),'-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1','-days','1'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        cls.received=[];cls.mode=204
        class Receiver(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                cls.received.append((body,self.headers.get('Idempotency-Key'),self.headers.get('Authorization')))
                if cls.mode=='hang':time.sleep(8);return
                self.send_response(cls.mode)
                if cls.mode==302:self.send_header('Location','https://localhost/NEVER-FOLLOW')
                if cls.mode==429:self.send_header('Retry-After','99999')
                self.end_headers()
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Receiver);cls.server.daemon_threads=True
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cls.cert,key)
        cls.server.socket=context.wrap_socket(cls.server.socket,server_side=True)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.certdir.cleanup()
    def setUp(self):
        super().setUp();self.config['endpoint']=f'https://localhost:{self.server.server_port}/events';self.config['ca_file']=str(self.cert)
        type(self).mode=204;type(self).received.clear()
    def test_tls_delivery_idempotency_header_and_bearer_auth(self):
        self.assertEqual(m.run(self.config,NOW)['status'],'ok')
        event,key,auth=self.received[0];self.assertEqual(key,event['event_id']);self.assertEqual(auth,'Bearer synthetic-secret-123456789')
    def test_untrusted_tls_is_refused(self):
        del self.config['ca_file'];self.assertEqual(m.run(self.config,NOW)['queued'],1);self.assertFalse(self.received)
    def test_redirect_is_not_followed(self):
        type(self).mode=302;result=m.run(self.config,NOW)
        self.assertEqual(result['queued'],1);self.assertEqual(len(self.received),1)
    def test_throttling_is_bounded(self):
        type(self).mode=429;m.run(self.config,NOW)
        self.assertEqual(self.state()['outbox'][0]['next_attempt'],NOW+300)
    def test_stalled_receiver_cannot_hold_command_indefinitely(self):
        type(self).mode='hang';start=time.monotonic();result=m.run(self.config,NOW)
        self.assertEqual(result['queued'],1);self.assertLess(time.monotonic()-start,7)
    def test_connection_refused_retains_queue(self):
        self.config['endpoint']='https://127.0.0.1:1/events'
        self.assertEqual(m.run(self.config,NOW)['queued'],1)

    def test_tls_retry_preserves_observation_id_after_uncertain_acceptance(self):
        type(self).mode=503;m.run(self.config,NOW)
        first=self.received[0][0]
        type(self).mode=204;m.run(self.config,NOW+60)
        self.assertEqual(self.received[1][0],first)
        self.assertEqual(self.received[1][1],first['event_id'])
