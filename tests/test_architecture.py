"""Queue publication, frozen execution and public import/service compatibility."""
import copy
import json
import importlib.util
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from XPolicyLab.evaluation.catalog import Catalog
from XPolicyLab.evaluation.runner import Manager
from XPolicyLab.evaluation.snapshot import prepare
from XPolicyLab.evaluation.store import Store

ROOT = Path(__file__).resolve().parents[1]
PARAMS = dict(policy="demo_policy", benchmark="protocol", task="interface_check", episodes=1, seed=7)


class PublicationTests(unittest.TestCase):
    def test_all_501_jobs_with_equal_timestamps_are_claimed_fifo(self):
        with tempfile.TemporaryDirectory() as directory, patch('XPolicyLab.evaluation.store.now', return_value='same'):
            store = Store(directory)
            snapshot = dict(version=1, parameters=PARAMS, configuration={})
            ids = [store.create(PARAMS, 'fixture', snapshot)['id'] for _ in range(501)]
            self.assertEqual(len(store.list()), 500)
            self.assertEqual([store.claim()['id'] for _ in ids], ids)
            self.assertIsNone(store.claim())
            self.assertEqual(len(store.active()), 501)

    def test_failed_preparation_never_publishes_and_orphans_are_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            original = store._write
            def fail_snapshot(path, value):
                if path.name == 'snapshot.json':
                    raise OSError('fixture disk failure')
                return original(path, value)
            with patch.object(store, '_write', side_effect=fail_snapshot):
                with self.assertRaises(OSError):
                    store.create(PARAMS, 'fixture', dict(version=1, parameters=PARAMS, configuration={}))
            self.assertEqual(store.list(), [])
            self.assertIsNone(store.claim())
            orphan = Path(directory) / 'runs' / ('e' * 16)
            orphan.mkdir(parents=True)
            (orphan / 'evidence.log').write_text('preserve me')
            recovered = Store(directory)
            self.assertIn(str(orphan), recovered.recovery_report['unpublished'])
            self.assertTrue((orphan / 'evidence.log').exists())

    def test_database_failure_after_file_preparation_leaves_only_an_unpublished_directory(self):
        from contextlib import contextmanager
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory)
            connect=store.connect
            @contextmanager
            def reject_insert():
                with connect() as connection:
                    connection.set_authorizer(lambda action,*_: sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_INSERT else sqlite3.SQLITE_OK)
                    yield connection
            with patch.object(store,'connect',reject_insert):
                with self.assertRaises(sqlite3.DatabaseError):
                    store.create(PARAMS,'fixture',dict(version=1,parameters=PARAMS,configuration={}))
            self.assertEqual(store.list(),[])
            self.assertEqual(len(store.unpublished_directories()['unpublished']),1)
            self.assertIsNone(store.claim())

    def test_cancellation_and_completion_have_a_single_terminal_winner(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            first = store.create(PARAMS, 'fixture')['id']
            store.claim()
            store.request_cancel(first)
            store.finish(first, 'succeeded', {'saved': True})
            self.assertEqual(store.get(first)['status'], 'cancelled')
            second = store.create(PARAMS, 'fixture')['id']
            store.claim()
            store.finish(second, 'succeeded', {})
            store.request_cancel(second)
            self.assertEqual(store.get(second)['status'], 'succeeded')
            self.assertFalse(store.update(second, status='running'))

    def test_legacy_history_is_readable_and_unsafe_queued_work_is_not_resumed(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            old = store.create(PARAMS, 'legacy')['id']
            recovered = Store(directory)
            self.assertEqual(recovered.get(old)['status'], 'interrupted')
            self.assertIn('快照', recovered.get(old)['error'])
            self.assertEqual(recovered.get(old)['parameters'], PARAMS)

    def test_snapshot_detects_artifact_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            snapshot = prepare(Catalog(), PARAMS)
            run = store.create(snapshot['parameters'], snapshot['revision'], snapshot)
            (store.directory(run['id']) / 'snapshot.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, '摘要'):
                store.load_snapshot(run['id'])


class FrozenExecutionTests(unittest.TestCase):
    def test_credentials_are_references_in_snapshots_and_resolved_only_for_execution(self):
        from XPolicyLab.evaluation.snapshot import validate_credential_references, resolve_environment
        with self.assertRaises(ValueError):
            validate_credential_references({'environment': {'HF_TOKEN': 'inline-value'}})
        value={'HF_TOKEN': {'env': 'QA_CREDENTIAL'}}
        validate_credential_references({'environment': value})
        with patch.dict(os.environ, {'QA_CREDENTIAL': 'fixture-value'}):
            self.assertEqual(resolve_environment(value)['HF_TOKEN'], 'fixture-value')
            self.assertNotIn('fixture-value',json.dumps(value))

    def finish(self, runner, run_id):
        end = time.monotonic() + 8
        while time.monotonic() < end:
            run = runner.store.get(run_id)
            if run['status'] not in ('queued', 'running', 'cancelling'):
                return run
            time.sleep(.03)
        self.fail('fixture timed out')

    def test_restart_executes_original_snapshot_after_catalog_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot = prepare(Catalog(), PARAMS)
            store = Store(directory)
            run = store.create(snapshot['parameters'], snapshot['revision'], snapshot)
            changed = Catalog({'real_profiles': []})
            changed.validate = lambda _: (_ for _ in ()).throw(AssertionError('live catalog was used'))
            runner = Manager(changed, directory)
            try:
                result = self.finish(runner, run['id'])
                self.assertEqual(result['status'], 'succeeded', result['error'])
                self.assertEqual(result['metrics']['protocol_total'], 1)
            finally:
                runner.close()

    def test_changed_external_client_is_rejected_before_spawn(self):
        from XPolicyLab.evaluation.snapshot import fingerprint, verify
        with tempfile.TemporaryDirectory() as directory:
            client = Path(directory) / 'client.py'
            client.write_text('original')
            snapshot = prepare(Catalog(), PARAMS)
            snapshot['dependencies'] = [fingerprint(client, 'fixture client')]
            client.write_text('modified')
            with self.assertRaisesRegex(ValueError, 'fixture client'):
                verify(snapshot)

    def test_cli_and_web_use_identical_plans_and_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            request = Path(directory) / 'request.json'
            request.write_text(json.dumps(PARAMS))
            process = subprocess.run([sys.executable, str(ROOT / 'scripts/run_evaluation.py'), '--request', str(request), '--data-dir', str(Path(directory) / 'cli')],
                                     cwd=directory, text=True, capture_output=True, timeout=15)
            self.assertEqual(process.returncode, 0, process.stderr)
            cli = json.loads(process.stdout)
            runner = Manager(Catalog(), Path(directory) / 'web')
            try:
                web = self.finish(runner, runner.create(PARAMS)['id'])
                self.assertEqual(cli['parameters'], web['parameters'])
                self.assertEqual(cli['metrics'], web['metrics'])
            finally:
                runner.close()


@unittest.skipUnless(all(importlib.util.find_spec(name) for name in ("numpy", "cv2", "websockets", "msgpack_numpy", "yaml")), "requires policy server dependencies")
class ServiceIdentityTests(unittest.TestCase):
    def test_alias_identity_in_both_import_orders_and_working_directories(self):
        pairs = [('environment.contracts', 'XPolicyLab.environment.contracts', 'ExecutionFeedback'),
                 ('client_server.ws.model_server', 'XPolicyLab.client_server.ws.model_server', 'PolicyServer')]
        for first, second, name in pairs:
            for a, b in ((first, second), (second, first)):
                for cwd in (ROOT, ROOT.parent, Path('/tmp')):
                    script = f'import sys,importlib;sys.path[:0]={[str(ROOT),str(ROOT.parent)]!r};a=importlib.import_module({a!r});b=importlib.import_module({b!r});assert getattr(a,{name!r}) is getattr(b,{name!r})'
                    result = subprocess.run([sys.executable, '-c', script], cwd=cwd, capture_output=True, text=True, timeout=15)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_vendor_utils_package_keeps_its_own_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'utils.py').write_text('vendor_marker=True')
            code=f'import sys;sys.path[:0]={[str(ROOT),str(ROOT.parent)]!r};import XPolicyLab;sys.path.insert(0,{directory!r});import utils;assert utils.vendor_marker;from XPolicyLab.utils.process_data import decode_image_bit'
            result=subprocess.run([sys.executable,'-c',code],cwd='/tmp',capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_service_config_defaults_overrides_and_explicit_flags(self):
        from client_server.service import parse_args_and_config
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'deploy.yml'
            path.write_text('policy_name: demo_policy\nhost: localhost\nport: null\n')
            with self.assertRaises(ValueError):
                parse_args_and_config(['--config-path', str(path)])
            ws = parse_args_and_config(['--config-path', str(path)], ws_only=True, default_port=19000)
            self.assertEqual(ws['port'], 19000)
            for overrides in (['port=1111','host=override'], ['--port','1111','--host','override']):
                cfg = parse_args_and_config(['--config_path',str(path),'--port','2222','--host','explicit','--overrides',*overrides])
                self.assertEqual((cfg['port'],cfg['host']), (2222,'explicit'))
            path.write_text('[invalid,mapping]')
            with self.assertRaises(ValueError):
                parse_args_and_config(['--config-path', str(path)])


if __name__ == '__main__':
    unittest.main()

class BackendSnapshotTests(unittest.TestCase):
    def fixture(self):
        import test_evaluation
        fixture=test_evaluation.EvaluationTests('test_default_batch_has_four_suites_and_2000_episodes')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def test_libero_restarts_with_original_client_and_plan(self):
        fixture=self.fixture();fixture.prepare_fake_processes();fixture.manager.close()
        snapshot=prepare(fixture.catalog,fixture.parameters(episodes=2))
        run=fixture.manager.store.create(snapshot['parameters'],snapshot['revision'],snapshot)
        fixture.config['libero']['client_root']='/changed/client'
        fixture.config['libero']['client_python']='/changed/python'
        fixture.catalog.checkpoint_path=lambda _: (_ for _ in ()).throw(AssertionError('live checkpoint lookup'))
        fixture.manager=Manager(fixture.catalog,fixture.base/'history')
        self.addCleanup(fixture.manager.close)
        result=fixture.finish(run['id'])
        self.assertEqual(result['status'],'succeeded',result['error'])
        self.assertEqual(result['parameters']['tasks'],list(__import__('XPolicyLab.evaluation.libero',fromlist=['LIBERO_STANDARD_SUITES']).LIBERO_STANDARD_SUITES))
        self.assertEqual(result['metrics']['episodes'],80)
        self.assertNotIn('/changed/',(fixture.manager.store.directory(run['id'])/'console.log').read_text())

    def test_client_change_is_recorded_as_failure_without_a_process(self):
        fixture=self.fixture();fixture.prepare_fake_processes()
        with fixture.manager.lock:
            run=fixture.manager.create(fixture.parameters(episodes=2))
            (fixture.client/'main.py').write_text('changed after submission')
        result=fixture.finish(run['id'])
        self.assertEqual(result['status'],'failed')
        self.assertIn('LIBERO client',result['error'])
        self.assertNotIn('$ bash',(fixture.manager.store.directory(run['id'])/'console.log').read_text())

    def test_hardware_uses_selected_profile_snapshot(self):
        fixture=self.fixture()
        (fixture.root/'scripts').mkdir()
        (fixture.root/'scripts/run_environment.py').write_text('import sys,json\nprint(json.dumps(sys.argv[1:]))\n')
        config=fixture.base/'hardware.json';config.write_text('{"device":"original"}')
        profile=dict(id='arm',policy='Pi_05',python=sys.executable,env_factory='fixture:create',policy_url='ws://127.0.0.1:12345',env_config=str(config))
        fixture.config['real_profiles']=[profile]
        fixture.manager=Manager(fixture.catalog,fixture.base/'history')
        self.addCleanup(fixture.manager.close)
        with fixture.manager.lock:
            run=fixture.manager.create(dict(policy='Pi_05',benchmark='real',task='arm',max_steps=4))
            profile['policy_url']='ws://changed.invalid:9999';profile['env_factory']='wrong:factory'
        result=fixture.finish(run['id'])
        self.assertEqual(result['status'],'succeeded',result['error'])
        log=(fixture.manager.store.directory(run['id'])/'console.log').read_text()
        self.assertIn('ws://127.0.0.1:12345',log);self.assertIn('fixture:create',log)
        self.assertNotIn('wrong:factory',log)
        self.assertIsNone(result['metrics']['success'])
        self.assertFalse(result['metrics']['success_known'])

    def test_hardware_unknown_success_stays_distinct_from_false(self):
        from XPolicyLab.evaluation.backends.hardware import read_result
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'events.jsonl'
            for value in (None,False,True):
                path.write_text(json.dumps(dict(event='episode_end',result=dict(success=value,terminated=True,truncated=False,steps=3)))+'\n')
                result=read_result(path)
                self.assertIs(result['success'],value)
                self.assertEqual(result['success_known'],value is not None)
                self.assertNotIn('success_rate',result)

class DeployContractTests(unittest.TestCase):
    def test_checker_reports_every_missing_demo_key_and_accepts_null_and_extras(self):
        import importlib.util,contextlib,io
        spec=importlib.util.spec_from_file_location('qa_checker',ROOT/'scripts/check_workspace.py')
        checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);subprocess.run(['git','init','-q',str(root)],check=True)
            (root/'configs').mkdir();(root/'configs/policy_workspace.json').write_text(json.dumps({'active_policies':['fixture']}))
            for name in ['README.md','README_zh.md','AGENTS.md','CONTRIBUTING.md','policy/README.md','environment/README.md','web/README.md','evaluation/README.md','UPSTREAM.md','model_template.py','start.sh','XPolicyLab.py','_robolab_compat.py','client_server/service.py']:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('')
            adapter=root/'policy/fixture';adapter.mkdir()
            for name in checker.REQUIRED_FILES:(adapter/name).write_text('')
            template=(ROOT/'policy/demo_policy/deploy.yml').read_text().replace('policy_name: demo_policy','policy_name: fixture')+'\nmodel_specific: supported\n'
            checker.ROOT=root
            for key in ['ckpt_name','gpu_id',None]:
                deploy=template if key is None else '\n'.join(line for line in template.splitlines() if not line.startswith(key+':'))
                (adapter/'deploy.yml').write_text(deploy)
                stream=io.StringIO()
                with contextlib.redirect_stderr(stream),contextlib.redirect_stdout(stream):result=checker.main()
                if key is None:self.assertEqual(result,0,stream.getvalue())
                else:self.assertIn('missing '+key,stream.getvalue());self.assertEqual(result,1)


@unittest.skipUnless(all(importlib.util.find_spec(name) for name in ('numpy','cv2','websockets','msgpack_numpy','yaml')), 'requires policy server dependencies')
class ServiceProcessTests(unittest.TestCase):
    def test_public_entrypoints_construct_the_same_effective_config_and_legacy_tcp(self):
        import socket,signal
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory)
            boot=directory/'boot.py'
            boot.write_text('''import sys,types,json,runpy
from pathlib import Path
root=Path(sys.argv[1]);entry=sys.argv[2];output=Path(sys.argv[3]);args=sys.argv[4:]
sys.path[:0]=[str(root),str(root.parent)]
module=types.ModuleType('XPolicyLab.policy.fixture.model')
class Model:
 def __init__(self,config):output.write_text(json.dumps(config))
module.Model=Model
sys.modules[module.__name__]=module
sys.argv=[entry,*args]
if entry=='ws':runpy.run_module('client_server.ws.model_server',run_name='__main__')
else:runpy.run_path(str(root/'setup_policy_server.py'),run_name='__main__')
''')
            config=directory/'deploy.yml'
            config.write_text('policy_name: fixture\nhost: 127.0.0.1\nport: null\n')
            for entry,protocol in [('root','ws'),('ws','ws'),('root','legacy_tcp')]:
                with self.subTest(entry=entry,protocol=protocol):
                    with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
                    output=directory/'model.json';output.unlink(missing_ok=True)
                    with (directory/'service.log').open('w') as log:
                        process=subprocess.Popen([sys.executable,str(boot),str(ROOT),entry,str(output),'--config-path',str(config),'--port',str(port),'--protocol',protocol],cwd='/tmp',stdout=log,stderr=subprocess.STDOUT)
                        try:
                            end=time.monotonic()+5
                            while True:
                                if process.poll() is not None:self.fail((directory/'service.log').read_text())
                                try:
                                    with socket.create_connection(('127.0.0.1',port),timeout=.1):break
                                except OSError:
                                    if time.monotonic()>end:self.fail('service did not bind')
                                    time.sleep(.03)
                            actual=json.loads(output.read_text())
                            self.assertEqual((actual['host'],actual['port'],actual['protocol']),('127.0.0.1',port,protocol))
                        finally:
                            process.send_signal(signal.SIGINT)
                            try:process.wait(timeout=5)
                            except subprocess.TimeoutExpired:process.kill();process.wait()
                        self.assertEqual(process.returncode,0,(directory/'service.log').read_text())
            result=subprocess.run([sys.executable,str(boot),str(ROOT),'root',str(directory/'invalid.json'),'--config-path',str(config)],cwd='/tmp',capture_output=True,text=True,timeout=5)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse((directory/'invalid.json').exists())
