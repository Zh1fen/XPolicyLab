"""Actual adapter shell argv and process cleanup using CPU-only server/client stubs."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
POLICIES=json.loads((ROOT/'configs/policy_workspace.json').read_text())['active_policies']


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='robolab lifecycle ')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'workspace with spaces/XPolicyLab'
        (self.root/'utils').mkdir(parents=True)
        for name in ('eval_lifecycle.sh','get_free_port.sh','wait_for_policy_server.sh'):
            shutil.copy2(ROOT/'utils'/name,self.root/'utils'/name)
        (self.root/'utils/wait_actual.sh').write_text((ROOT/'utils/wait_for_policy_server.sh').read_text())
        # Record the adapter's original timeout/host, shorten only fixture waits.
        (self.root/'utils/wait_for_policy_server.sh').write_text('''#!/bin/bash
set -e
"${QA_PYTHON}" "${QA_STUB}" wait "$@"
exec bash "$(dirname "$0")/wait_actual.sh" "$1" "$2" "$3" "$4" 1
''')
        self.stub=Path(self.temp.name)/'stub.py'
        self.stub.write_text('''import json,os,socket,subprocess,sys,time
from pathlib import Path
role,args=sys.argv[1],sys.argv[2:]
item=dict(role=role,args=args,pid=os.getpid())
if role in ('server','va'):
 child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
 item['child']=child.pid
with open(os.environ['QA_EVENTS'],'a') as f:f.write(json.dumps(item)+'\\n')
if role=='wait':sys.exit(0)
if role=='client':
 if os.environ.get('QA_BLOCK'):time.sleep(60)
 sys.exit(int(os.environ.get('QA_CLIENT_FAIL','0')))
if os.environ.get('QA_SERVER_FAIL'):sys.exit(17)
if os.environ.get('QA_NO_LISTEN'):time.sleep(60)
port=int(args[8] if role=='server' else args[1])
s=socket.socket();s.bind(('127.0.0.1',port));s.listen()
while True:
 c,_=s.accept();c.close()
''')
        self.events=Path(self.temp.name)/'events.jsonl'
        self.environment=dict(os.environ,QA_PYTHON=sys.executable,QA_STUB=str(self.stub),QA_EVENTS=str(self.events),LINGBOT_VA_VA_PORT='19999')
        for policy in POLICIES:
            adapter=self.root/'policy'/policy;adapter.mkdir(parents=True)
            shutil.copy2(ROOT/'policy'/policy/'eval.sh',adapter/'eval.sh')
            for filename,role in (('setup_eval_policy_server.sh','server'),('setup_eval_env_client.sh','client'),('launch_wan_va_server.sh','va')):
                (adapter/filename).write_text(f'#!/bin/bash\nexec "${{QA_PYTHON}}" "${{QA_STUB}}" {role} "$@"\n')
        self.addCleanup(self.kill_fixture_processes)

    def entries(self):
        return [json.loads(line) for line in self.events.read_text().splitlines()] if self.events.exists() else []

    def kill_fixture_processes(self):
        for entry in self.entries():
            if entry['role']=='wait':continue
            for pid in [entry['pid'],entry.get('child')]:
                if pid:
                    try:os.kill(pid,signal.SIGKILL)
                    except ProcessLookupError:pass

    def is_running(self,pid):
        path=Path(f'/proc/{pid}/stat')
        return path.exists() and path.read_text().split(') ',1)[1][0]!='Z'

    def assert_reaped(self):
        end=time.monotonic()+3
        while time.monotonic()<end:
            alive=[pid for event in self.entries() if event['role']!='wait' for pid in (event['pid'],event.get('child')) if pid and self.is_running(pid)]
            if not alive:return
            time.sleep(.03)
        self.fail(f'fixture processes still active: {alive}')

    def command(self,policy,filename='eval.sh'):
        return ['bash',str(self.root/'policy'/policy/filename),'Bench space','task space','checkpoint name','profile','joint','7','1','2','policy env','eval env']

    def test_all_eight_preserve_actual_argv_and_reap_descendants(self):
        baseline=ROOT/'artifacts/architecture-qa/baseline/policy'
        for policy in POLICIES:
            with self.subTest(policy=policy):
                self.events.unlink(missing_ok=True)
                # Verify semantic argument positions, including model-specific host/config fields.
                result=subprocess.run(self.command(policy),env=self.environment,capture_output=True,text=True,timeout=12)
                self.assertEqual(result.returncode,0,result.stderr)
                events=self.entries()
                server=next(event['args'] for event in events if event['role']=='server')
                client=next(event['args'] for event in events if event['role']=='client')
                self.assertEqual(server[:8],['Bench space','task space','checkpoint name','profile','joint','7','1','policy env'])
                self.assertEqual(client[:8],['Bench space','task space','checkpoint name','profile','joint','7','2','eval env'])
                self.assertEqual(client[10],'localhost')
                self.assert_reaped()
                if baseline.is_dir():
                    # Run the saved shell against the same fixture; teardown handles legacy PID-only cleanup.
                    old=self.root/'policy'/policy/'baseline.sh';shutil.copy2(baseline/policy/'eval.sh',old)
                    self.events.unlink()
                    with (self.root/'baseline-output.log').open('w') as log:
                        previous=subprocess.run(self.command(policy,'baseline.sh'),env=self.environment,stdout=log,stderr=subprocess.STDOUT,text=True,timeout=12)
                    self.assertEqual(previous.returncode,0,(self.root/'baseline-output.log').read_text())
                    original=self.entries();old_server=next(event['args'] for event in original if event['role']=='server');old_client=next(event['args'] for event in original if event['role']=='client')
                    server[8]=old_server[8]='PORT';client[9]=old_client[9]='PORT'
                    self.assertEqual(server,old_server);self.assertEqual(client,old_client)
                    self.kill_fixture_processes()

    def test_failure_timeout_client_exit_and_interrupt_cleanup(self):
        for scenario,flags in [('server',{'QA_SERVER_FAIL':'1'}),('timeout',{'QA_NO_LISTEN':'1'}),('client',{'QA_CLIENT_FAIL':'9'}),('interrupt',{'QA_BLOCK':'1'})]:
            with self.subTest(scenario=scenario):
                self.events.unlink(missing_ok=True)
                process=subprocess.Popen(self.command('demo_policy'),env=dict(self.environment,**flags),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True)
                if scenario=='interrupt':
                    end=time.monotonic()+5
                    while not any(event['role']=='client' for event in self.entries()) and time.monotonic()<end:time.sleep(.02)
                    os.killpg(process.pid,signal.SIGTERM)
                output,_=process.communicate(timeout=12)
                self.assertNotEqual(process.returncode,0,output)
                if scenario=='client':self.assertEqual(process.returncode,9)
                self.assert_reaped()

    def test_lingbot_owned_backend_is_registered_and_stopped(self):
        adapter=self.root/'policy/LingBot_VA'
        # Stub conda activation without using any model environment.
        conda=Path(self.temp.name)/'conda';(conda/'etc/profile.d').mkdir(parents=True)
        (conda/'etc/profile.d/conda.sh').write_text('conda() { return 0; }\n')
        binary=Path(self.temp.name)/'bin';binary.mkdir()
        command=binary/'conda';command.write_text(f'#!/bin/bash\necho "{conda}"\n');command.chmod(0o755)
        env=dict(self.environment,PATH=str(binary)+os.pathsep+os.environ['PATH'],LINGBOT_VA_BASE_MODEL_PATH='fixture base')
        env.pop('LINGBOT_VA_VA_PORT')
        result=subprocess.run(self.command('LingBot_VA'),env=env,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual([event['role'] for event in self.entries() if event['role']!='wait'],['va','server','client'])
        self.assert_reaped()


if __name__=='__main__':unittest.main()

class ConsoleLifecycleTests(LifecycleTests):
    # Only the added case is needed; inherited shell cases are covered by LifecycleTests.
    test_all_eight_preserve_actual_argv_and_reap_descendants=None
    test_failure_timeout_client_exit_and_interrupt_cleanup=None
    test_lingbot_owned_backend_is_registered_and_stopped=None

    def test_console_cancel_reaps_adapter_owned_process_groups(self):
        from unittest.mock import patch
        from XPolicyLab.evaluation.catalog import Catalog
        from XPolicyLab.evaluation.runner import Manager
        (self.root/'configs').mkdir()
        (self.root/'configs/policy_workspace.json').write_text(json.dumps({'active_policies':['demo_policy']}))
        (self.root/'policy/demo_policy/checkpoints/run/1/params').mkdir(parents=True)
        (self.root.parent/'env_cfg').mkdir()
        (self.root.parent/'env_cfg/profile.yml').write_text('config: {}')
        (self.root.parent/'scripts').mkdir()
        (self.root.parent/'scripts/eval_policy.sh').touch()
        config={'standard':{'RoboDojo':{'eval_env':'fixture','tasks':['task'],'policies':['demo_policy'],'robots':['profile']}},'policy_environments':{'demo_policy':'fixture'}}
        with patch.dict(os.environ,dict(self.environment,QA_BLOCK='1')),patch('XPolicyLab.evaluation.catalog.shutil.which',return_value=sys.executable):
            runner=Manager(Catalog(config,self.root),self.root/'history')
            try:
                run=runner.create(dict(policy='demo_policy',benchmark='RoboDojo',task='task',checkpoint='run/1',robot='profile'))
                end=time.monotonic()+6
                while not any(item['role']=='client' for item in self.entries()) and time.monotonic()<end:time.sleep(.02)
                self.assertTrue(any(item['role']=='client' for item in self.entries()))
                runner.cancel(run['id'])
                while runner.store.get(run['id'])['status']!='cancelled' and time.monotonic()<end+6:time.sleep(.03)
                self.assertEqual(runner.store.get(run['id'])['status'],'cancelled')
                self.assert_reaped()
            finally:runner.close()
