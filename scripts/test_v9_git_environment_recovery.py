"""Independent literal oracles: REC-AC1/2. Temporary data only, no real Git delivery."""
from pathlib import Path
import hashlib
import importlib.util
import sys
import unittest
from unittest import mock
import tempfile
import os
import json
import subprocess
import shlex
import shutil
import io
import importlib
import types

ROOT=Path(__file__).resolve().parents[1]
OLD=(b'[core]\n\trepositoryformatversion = 0\n\tbare = false\n'
     b'[remote "origin"]\n\turl = https://github.com/koma236/FitLog.git\n'
     b'[branch "main"]\n\tremote = origin\n\tmerge = refs/heads/main\n'
     b'[branch "old"]\n\tvscode-merge-base = origin/main\n')
LINE=b'\tvscode-merge-base = origin/main\n'
CURRENT=OLD.replace(b'[branch "old"]\n',LINE+b'[branch "old"]\n')
OLD_SHA=hashlib.sha256(OLD).hexdigest()

class RecoveryCase(unittest.TestCase):
 def setUp(self):
  path=ROOT/'scripts/v9_git_environment_recovery.py'
  if not path.is_file():self.fail('The approved recovery behavior has not been implemented yet.')
  name='fitlog_env_recovery_under_test'
  if name not in sys.modules:
   spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
   sys.modules[name]=module;spec.loader.exec_module(module)
  self.m=sys.modules[name]
 def api(self,name):
  value=getattr(self.m,name,None)
  if not callable(value):self.fail('Approved behavior not implemented: '+name)
  return value

class ConfigDeltaTests(RecoveryCase):
 def test_only_the_main_metadata_addition_is_authorized(self):
  value=self.m.validate_delta(OLD_SHA,CURRENT)
  self.assertEqual(value['kind'],'main_vscode_metadata_added')
  self.assertEqual(value['old_sha256'],OLD_SHA)
  self.assertEqual(value['current_sha256'],hashlib.sha256(CURRENT).hexdigest())
 def test_existing_other_branch_metadata_is_kept(self):
  self.assertEqual(self.m.validate_delta(OLD_SHA,CURRENT)['kind'],'main_vscode_metadata_added')
  self.assertIn(b'[branch "old"]\n'+LINE,OLD)
 def test_no_change_is_not_a_recovery(self):
  with self.assertRaises(self.m.RecoveryError):self.m.validate_delta(OLD_SHA,OLD)
 def test_whitespace_and_line_ending_variants_are_refused(self):
  for replacement in [b'    vscode-merge-base = origin/main\n',b'\tvscode-merge-base=origin/main\n',b'\tvscode-merge-base = origin/main\r\n',b'\tvscode-merge-base = origin/main']:
   bad=OLD.replace(b'[branch "old"]\n',replacement+b'[branch "old"]\n')
   with self.subTest(replacement=replacement),self.assertRaises(self.m.RecoveryError):self.m.validate_delta(OLD_SHA,bad)
 def test_other_section_or_new_branch_metadata_is_refused(self):
  bads=[OLD+LINE,CURRENT+b'[branch "another"]\n'+LINE,CURRENT.replace(b'[branch "main"]',b'[branch.main]'),CURRENT.replace(b'[branch "main"]',b'[BRANCH "main"]'),CURRENT.replace(b'[branch "main"]\n',b'[branch "main"] remote = origin\n')]
  for bad in bads:
   with self.subTest(bad=bad),self.assertRaises(self.m.RecoveryError):self.m.validate_delta(OLD_SHA,bad)
 def test_extra_or_duplicate_changes_are_refused(self):
  bads=[CURRENT.replace(b'[branch "old"]\n',LINE+b'[branch "old"]\n'),CURRENT.replace(b'github.com/koma236',b'github.com/other'),CURRENT+b'[credential]\n\thelper = unapproved\n',b'\xef\xbb\xbf'+CURRENT,CURRENT+b'\xff']
  for bad in bads:
   with self.subTest(bad=bad),self.assertRaises(self.m.RecoveryError):self.m.validate_delta(OLD_SHA,bad)
 def test_invalid_old_digest_and_input_type_are_refused_without_echo(self):
  for digest,raw in [('not-a-digest',CURRENT),(OLD_SHA,'not bytes'),(OLD_SHA,b'unapproved-secret-marker')]:
   with self.subTest(digest=digest),self.assertRaises(self.m.RecoveryError) as raised:self.m.validate_delta(digest,raw)
   self.assertNotIn('unapproved-secret-marker',str(raised.exception))

class JsonAndCommitTests(RecoveryCase):
 def test_json_duplicate_nested_nonfinite_and_nonobject_records_refuse(self):
  parse=self.api('strict_json')
  self.assertEqual(parse(b'{"outer":{"x":1}}'),{'outer':{'x':1}})
  for raw in [b'{"x":1,"x":2}',b'{"x":{"y":1,"y":2}}',b'{"x":NaN}',b'[]',b'not-json-private-marker']:
   with self.subTest(raw=raw),self.assertRaises(self.m.RecoveryError) as raised:parse(raw)
   self.assertNotIn('private-marker',str(raised.exception))
 def test_json_record_size_is_bounded(self):
  parse=self.api('strict_json')
  with self.assertRaises(self.m.RecoveryError):parse(b'{"x":"'+b'a'*(1024*1024)+b'"}')
 def test_raw_commit_headers_not_message_text_choose_parent_and_tree(self):
  parse=self.api('parse_commit')
  raw=(b'tree '+b'1'*40+b'\nparent '+b'2'*40+b'\nauthor Test <t@example.invalid> 0 +0000\n\nmessage\ntree '+b'3'*40+b'\nparent '+b'4'*40+b'\n')
  self.assertEqual(parse(raw),{'tree':'1'*40,'parent':'2'*40})
 def test_raw_commit_rejects_multiple_missing_or_malformed_parent_tree(self):
  parse=self.api('parse_commit')
  for raw in [b'tree '+b'1'*40+b'\n\nroot',b'tree '+b'1'*40+b'\nparent '+b'2'*40+b'\nparent '+b'3'*40+b'\n\nmerge',b'tree not-an-oid\nparent '+b'2'*40+b'\n\nmessage',b'tree '+b'1'*40+b'\ntree '+b'3'*40+b'\nparent '+b'2'*40+b'\n\nmessage']:
   with self.subTest(raw=raw),self.assertRaises(self.m.RecoveryError):parse(raw)

class EnvironmentTests(RecoveryCase):
 def test_child_environment_is_new_allowlist_without_parent_overrides(self):
  with mock.patch.dict('os.environ',{'GH_TOKEN':'fake','GIT_SSH_COMMAND':'unapproved','GIT_CONFIG_KEY_7':'url.fake.insteadOf','PYTHONPATH':'unapproved'},clear=False):
   value=self.m.basic_environment()
  self.assertEqual(value['PATH'],'/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin')
  self.assertEqual(value['GIT_NO_REPLACE_OBJECTS'],'1')
  self.assertEqual(value['GIT_OPTIONAL_LOCKS'],'0')
  self.assertFalse({'GH_TOKEN','GIT_SSH_COMMAND','GIT_CONFIG_KEY_7','PYTHONPATH'} & value.keys())
 def test_observable_override_name_refusal_never_echoes_value(self):
  check=self.api('ensure_clean_parent')
  for key in ['GIT_CONFIG_PARAMETERS','GIT_CONFIG_COUNT','GIT_CONFIG_KEY_8','GIT_CONFIG_VALUE_8','GIT_SSH_COMMAND','GIT_ASKPASS','GH_TOKEN','GH_CONFIG_DIR','GIT_GRAFT_FILE','BASH_ENV','ENV','SHELLOPTS','BASH_FUNC_x%%','DYLD_INSERT_LIBRARIES','LD_PRELOAD','PYTHONPATH','VSCODE_GIT_ASKPASS_NODE']:
   with self.subTest(key=key),self.assertRaises(self.m.RecoveryError) as raised:check({key:'private-value-marker'})
   self.assertNotIn('private-value-marker',str(raised.exception))
  check({'PATH':'ordinary','SAFE_EXTRA':'ordinary'})

class PrivateRecordTests(RecoveryCase):
 def setUp(self):
  super().setUp()
  self.temp=tempfile.TemporaryDirectory(prefix='fitlog-record-test-',dir='/private/tmp')
  self.addCleanup(self.temp.cleanup)
  self.home=Path(self.temp.name)/'home';self.home.mkdir(mode=0o700)
  self.folder=self.home/'records';self.folder.mkdir(mode=0o700)
 def record(self):
  path=self.folder/'record.json';path.write_bytes(b'{"kind":"fixture"}');path.chmod(0o600);return path
 def test_private_record_reads_without_rewriting_bytes_or_mtime(self):
  read=self.api('read_private');path=self.record();before=path.stat().st_mtime_ns
  self.assertEqual(read(path,self.home),b'{"kind":"fixture"}')
  self.assertEqual(path.stat().st_mtime_ns,before)
 def test_public_mode_leaf_symlink_and_parent_symlink_refuse(self):
  read=self.api('read_private');path=self.record();path.chmod(0o644)
  with self.assertRaises(self.m.RecoveryError):read(path,self.home)
  path.chmod(0o600);link=self.folder/'alias.json';link.symlink_to(path)
  with self.assertRaises(self.m.RecoveryError):read(link,self.home)
  other=self.home/'alias';other.symlink_to(self.folder)
  with self.assertRaises(self.m.RecoveryError):read(other/'record.json',self.home)
 def test_public_parent_and_oversized_records_refuse(self):
  read=self.api('read_private');path=self.record();self.folder.chmod(0o755)
  with self.assertRaises(self.m.RecoveryError):read(path,self.home)
  self.folder.chmod(0o700);path.write_bytes(b'a'*(1024*1024+1))
  with self.assertRaises(self.m.RecoveryError):read(path,self.home)
 def test_record_publication_is_private_and_never_overwrites(self):
  write=self.api('write_new');path=self.folder/'new.json'
  write(path,{'kind':'new'},self.home)
  self.assertEqual(path.stat().st_mode & 0o777,0o600)
  before=path.read_bytes()
  with self.assertRaises(self.m.RecoveryError):write(path,{'kind':'different'},self.home)
  self.assertEqual(path.read_bytes(),before)
  self.assertEqual(self.m.strict_json(before),{'kind':'new'})
 def test_publication_creates_only_private_parents_and_does_not_chmod_unsafe_ones(self):
  write=self.api('write_new');path=self.home/'private'/'child'/'new.json'
  write(path,{'kind':'new'},self.home)
  self.assertEqual(path.parent.stat().st_mode & 0o777,0o700)
  self.assertEqual(path.parent.parent.stat().st_mode & 0o777,0o700)
  public=self.home/'public';public.mkdir(mode=0o755)
  with self.assertRaises(self.m.RecoveryError):write(public/'new.json',{'x':1},self.home)
  self.assertEqual(public.stat().st_mode & 0o777,0o755)
 def test_exclusive_lock_refuses_parallel_entry_and_releases_without_deleting(self):
  lease=self.api('FileLease');path=self.folder/'lease.lock'
  with lease(path,self.home):
   with self.assertRaises(self.m.RecoveryError):
    with lease(path,self.home):pass
  self.assertTrue(path.exists())
  with lease(path,self.home):pass
 def test_digest_seal_detects_modified_record(self):
  seal=self.api('seal');check=self.api('check_seal')
  value=seal({'kind':'fixture','nested':{'x':1}},'ticket_digest')
  expected=hashlib.sha256(json.dumps({'kind':'fixture','nested':{'x':1}},sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
  self.assertEqual(value['ticket_digest'],expected);check(value,'ticket_digest')
  value['nested']['x']=2
  with self.assertRaises(self.m.RecoveryError):check(value,'ticket_digest')

class RuntimeInventoryTests(RecoveryCase):
 def setUp(self):
  super().setUp();self.temp=tempfile.TemporaryDirectory(prefix='fitlog-runtime-test-',dir='/private/tmp');self.addCleanup(self.temp.cleanup)
  self.folder=Path(self.temp.name);self.runtime=self.folder/'runtime';self.runtime.mkdir(mode=0o700)
  (self.runtime/'bin').mkdir(mode=0o700);(self.runtime/'scripts').mkdir(mode=0o700)
  (self.runtime/'bin/ai-dev').write_bytes(b'#!/bin/sh\nexit 0\n');(self.runtime/'bin/ai-dev').chmod(0o700)
  self.code=self.runtime/'scripts/fixture.py';self.code.write_bytes(b'fixture = 1\n');self.code.chmod(0o600)
  (self.runtime/'.gitignore').write_text('__pycache__/\n')
  self.git('init','-q','-b','fixture/runtime');self.git('add','.');self.git('commit','-qm','fixture')
  self.pin=self.git('rev-parse','HEAD')
 def git(self,*args):
  return subprocess.check_output(['/usr/bin/git','-c','user.name=Fixture','-c','user.email=fixture@example.invalid',*args],cwd=self.runtime,env=self.m.basic_environment(),stderr=subprocess.PIPE,text=True).strip()
 def test_pinned_tree_index_and_raw_worktree_agree(self):
  inventory=self.api('runtime_inventory')
  self.assertEqual(inventory(self.runtime,self.pin),{'bin/ai-dev':b'#!/bin/sh\nexit 0\n','scripts/fixture.py':b'fixture = 1\n'})
 def test_untracked_ignored_cache_and_changed_raw_bytes_refuse(self):
  inventory=self.api('runtime_inventory');cache=self.runtime/'scripts/__pycache__';cache.mkdir();(cache/'fixture.pyc').write_bytes(b'not code')
  with self.assertRaises(self.m.RecoveryError):inventory(self.runtime,self.pin)
  (cache/'fixture.pyc').unlink();cache.rmdir();self.code.write_bytes(b'fixture = 2\n')
  with self.assertRaises(self.m.RecoveryError):inventory(self.runtime,self.pin)
 def test_optimization_flags_and_physical_mode_change_refuse(self):
  inventory=self.api('runtime_inventory')
  for flag,undo in [('--assume-unchanged','--no-assume-unchanged'),('--skip-worktree','--no-skip-worktree')]:
   self.git('update-index',flag,'scripts/fixture.py')
   with self.subTest(flag=flag),self.assertRaises(self.m.RecoveryError):inventory(self.runtime,self.pin)
   self.git('update-index',undo,'scripts/fixture.py')
  self.code.chmod(0o700)
  with self.assertRaises(self.m.RecoveryError):inventory(self.runtime,self.pin)
 def test_staged_content_cannot_replace_pinned_content(self):
  inventory=self.api('runtime_inventory');self.code.write_bytes(b'fixture = 2\n');self.git('add','scripts/fixture.py')
  with self.assertRaises(self.m.RecoveryError):inventory(self.runtime,self.pin)
 def test_replace_ref_cannot_replace_pinned_content(self):
  inventory=self.api('runtime_inventory');self.code.write_bytes(b'fixture = 2\n');self.git('add','scripts/fixture.py')
  tree=self.git('write-tree');replacement=self.git('commit-tree',tree,'-p',self.pin,'-m','replacement fixture')
  self.git('replace',self.pin,replacement)
  with self.assertRaises(self.m.RecoveryError):inventory(self.runtime,self.pin)
 def test_runtime_reads_never_execute_clean_filter(self):
  inventory=self.api('runtime_inventory');marker=self.folder/'filter.marker';clean=self.folder/'clean.sh'
  clean.write_text('#!/bin/sh\n/usr/bin/touch '+shlex.quote(str(marker))+'\n/bin/cat\n');clean.chmod(0o700)
  (self.runtime/'.gitattributes').write_text('scripts/fixture.py filter=probe\n')
  self.git('config','filter.probe.clean',str(clean));self.code.write_bytes(b'fixture = 1\n')
  self.git('add','.gitattributes','scripts/fixture.py');self.git('commit','-qm','filter fixture');self.pin=self.git('rev-parse','HEAD')
  marker.unlink(missing_ok=True);self.code.write_bytes(b'fixture = 1\n')
  self.assertEqual(inventory(self.runtime,self.pin)['scripts/fixture.py'],b'fixture = 1\n')
  self.assertFalse(marker.exists())

class CoreFixture:
 """Simulated approval evidence is confined to an owned temporary HOME, never real state."""
 def __init__(self,m):
  self.m=m;self.temp=tempfile.TemporaryDirectory(prefix='fitlog-legacy-fixture-',dir='/private/tmp')
  self.home=Path(self.temp.name)/'home';self.home.mkdir(mode=0o700)
  self.root=self.home/'project';self.root.mkdir(mode=0o700);self.task='FIXTURE-RECOVERY'
  # The legacy recovery protocol is independently fixed to R0, not the active task runtime.
  self.runtime=Path('/Users/saki/.codex-personal/runtimes/ai-dev-harness-169642d')
  sys.dont_write_bytecode=True
  if str(self.runtime/'scripts') not in sys.path:sys.path.insert(0,str(self.runtime/'scripts'))
  self.w=importlib.import_module('v9.workflow');self.h=importlib.import_module('v9.handoff')
  self.c=importlib.import_module('v9.controller');self.g=importlib.import_module('v9.gitops')
  self.put(self.root/'tracked.txt',b'one\n');self.git('init','-q','-b','feature/fixture');self.git('add','tracked.txt');self.git('commit','-qm','fixture baseline')
  self.baseline=self.git('rev-parse','HEAD')
  self.git('remote','add','origin','https://github.com/koma236/FitLog.git')
  self.git('config','branch.main.remote','origin');self.git('config','branch.main.merge','refs/heads/main')
  self.put(self.home/'.config/git-fixture/config',b'[user]\nname = Fixture\nemail = fixture@example.invalid\n')
  self.dirs(self.home/'.config/gh-fixture');self.dirs(self.home/'.codex-personal')
  self.put(self.home/'.ai-dev-harness/personal-git.toml',b'schema_version = 1\naccount = "koma236"\ngh_config_dir = ".config/gh-fixture"\ngit_config_file = ".config/git-fixture/config"\n')
  self.put(self.root/'.ai-dev/project.toml',b'schema_version = 1\nchecks = [{id="unit",argv=["/usr/bin/true"],cwd=".",timeout_seconds=60,env={}}]\nscopes=[]\n[project]\nid="fixture"\n')
  source=b'Fixture requirements and acceptance. Simulated design evidence for boundary tests only.\n'
  self.put(self.root/'docs/spec.md',source)
  manifest={'schema_version':9,'required_roles':['requirements','acceptance','design'],'sources':[{'id':'source-'+role,'role':role,'path':'docs/spec.md','sha256':hashlib.sha256(source).hexdigest()} for role in ['requirements','acceptance','design']],'requirements':[{'id':'REQ-1','source':'source-requirements','text':'Change fixture tracked result'}],'acceptance':[{'id':'AC-1','source':'source-acceptance','requirements':['REQ-1'],'text':'Fixture boundary passes'}],'questions':[]}
  paths=['tracked.txt','.ai-dev/project.toml','.ai-dev/spec.json','.ai-dev/plan.json','docs/spec.md','.claude/hooks/review-budget.cjs']
  plan={'schema_version':10,'baseline_commit':self.baseline,'tasks':[{'id':self.task,'title':'Fixture task','kind':'standard','requirements':['REQ-1'],'acceptance':['AC-1'],'depends_on':[],'paths':paths,'test_oracle':'Handwritten fixture; not actual approval','done_when':'Boundary test only'}]}
  self.put(self.root/'.ai-dev/spec.json',json.dumps(manifest).encode());self.put(self.root/'.ai-dev/plan.json',json.dumps(plan).encode())
  self.put(self.root/'.claude/hooks/review-budget.cjs',(ROOT/'.claude/hooks/review-budget.cjs').read_bytes())
  self.put(self.root/'tracked.txt',b'two\n')
  ctx=self.c._inputs(self.root,task=self.task,implementation_provider='codex',manifest_file='.ai-dev/spec.json',plan_file='.ai-dev/plan.json',home=self.home,harness_root=self.runtime)
  state=self.w.new_workflow(ctx['binding']);snapshot=state['binding']['snapshot_hash']
  state=self.w.reserve_attempt(state,'fixture-design',phase='design_review',input_snapshot=snapshot,max_rounds=1,max_seconds=60)
  self.state_path=self.h.workflow_state_path(self.home,self.root,self.task);self.dirs(self.state_path.parent)
  store=self.w.WorkflowStore(self.state_path);store.create(state)
  self.h.create_job({'schema_version':10,'operation':'execute_reserved','project':str(self.root),'task':self.task,'attempt_id':'fixture-design','phase':'design_review','provider':'claude','implementation_provider':'codex','manifest_file':'.ai-dev/spec.json','plan_file':'.ai-dev/plan.json'},project=self.root,home=self.home,harness_root=self.runtime)
  state=self.w.mark_attempt_running(state,'fixture-design')
  state=self.w.complete_attempt(state,'fixture-design',status='succeeded',rounds_used=1,seconds_used=1,output_snapshot=snapshot,evidence={'kind':'design','design_binding':ctx['design_binding'],'verdict':{'approved':True,'summary':'Simulated fixture only','findings':[]}})
  for phase in ['specification','plan']:state=self.w.approve(state,phase,actor='fixture',evidence=self.w.approval_evidence(state,phase))
  state=self.w.reserve_attempt(state,'fixture-verify',phase='verify',input_snapshot=snapshot,max_rounds=1,max_seconds=60);state=self.w.mark_attempt_running(state,'fixture-verify')
  assert subprocess.run(['/usr/bin/true'],env=m.basic_environment(self.home)).returncode==0
  state=self.w.complete_attempt(state,'fixture-verify',status='succeeded',rounds_used=1,seconds_used=1,output_snapshot=snapshot,evidence={'kind':'checks','checks_digest':state['binding']['checks_digest'],'verified_snapshot':snapshot,'results':[{'id':'unit','exit_code':0,'elapsed_ms':1,'status':'passed'}]})
  state=self.w.approve(state,'implementation',actor='fixture',evidence=self.w.approval_evidence(state,'implementation'))
  state=self.w.reserve_attempt(state,'fixture-quality',phase='review',input_snapshot=snapshot,max_rounds=1,max_seconds=60);state=self.w.mark_attempt_running(state,'fixture-quality')
  state=self.w.complete_attempt(state,'fixture-quality',status='succeeded',rounds_used=1,seconds_used=1,output_snapshot=snapshot,evidence={'kind':'quality','quality_status':'passed','verified_snapshot':snapshot,'implementation_attempt_id':state['approvals']['implementation']['evidence']['attempt_id']})
  state=self.w.approve(state,'review',actor='fixture',evidence=self.w.approval_evidence(state,'review'))
  store.save(state,expected_revision=store.load()['revision'])
  issue=self.g.prepare_action(self.root,task=self.task,action='issue',details={'remote':'origin','title':'Fixture only','body':'Fake transport; never GitHub'},home=self.home,run=self.transport)
  self.execute(issue)
  self.job=self.g.prepare_action(self.root,task=self.task,action='commit',details={'message':'fixture approved change'},home=self.home,run=self.transport)
  self.execute(self.job);self.commit=self.git('rev-parse','HEAD')
  config=self.root/'.git/config';old=config.read_bytes();self.old_config=old
  config.write_bytes(old.replace(b'[branch "main"]\n',b'[branch "main"]\n'+LINE))
 def dirs(self,path):
  relative=path.relative_to(self.home);current=self.home
  for part in relative.parts:
   current/=part
   if not current.exists():current.mkdir(mode=0o700)
 def put(self,path,raw):
  self.dirs(path.parent);path.write_bytes(raw);path.chmod(0o600)
 def git(self,*args):
  return subprocess.check_output(['/usr/bin/git','-c','user.name=Fixture','-c','user.email=fixture@example.invalid',*args],cwd=self.root,env=self.m.basic_environment(self.home),text=True,stderr=subprocess.PIPE).strip()
 def transport(self,args,**kwargs):
  if args[:2]==['gh','api']:return subprocess.CompletedProcess(args,0,'koma236\n','')
  if args[:3]==['gh','issue','create']:return subprocess.CompletedProcess(args,0,'https://github.com/koma236/FitLog/issues/1\n','')
  if args[0]=='gh':raise AssertionError('Unexpected external fixture transport')
  return subprocess.run(args,**kwargs)
 def execute(self,job):
  value=json.loads(job.read_text());expected='APPROVE '+value['action'].upper()+' '+value['proposal_digest'][:12]
  assert self.g.execute_action(job,project=self.root,home=self.home,run=self.transport,input_fn=lambda _prompt:expected,terminal_check=lambda:True,output=io.StringIO())==0
 def files(self):return {str(p.relative_to(self.home)):(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns) for p in self.home.rglob('*') if p.is_file()}

class LegacyContextTests(RecoveryCase):
 def fixture(self):
  fixture=CoreFixture(self.m);self.addCleanup(fixture.temp.cleanup);return fixture
 def test_real_pinned_context_is_read_only_and_uses_fresh_namespace(self):
  read=self.api('read_legacy_context');f=self.fixture();before=f.files()
  poison=types.ModuleType('forbidden_legacy_parent_module')
  aliases={name:poison for name in list(sys.modules) if name=='harness' or name=='v9' or name.startswith('v9.')}
  with mock.patch.dict(sys.modules,aliases):value=read(f.job,f.root,f.runtime,f.home)
  self.assertEqual(value['commit'],f.commit)
  self.assertEqual(value['task'],f.task)
  self.assertEqual(value['delta']['kind'],'main_vscode_metadata_added')
  self.assertEqual(value['personal_environment']['account'],'koma236')
  self.assertEqual(before,f.files())
 def test_changed_revision_or_automatic_review_is_not_approved_commit(self):
  read=self.api('read_legacy_context');f=self.fixture();original=f.state_path.read_bytes();state=json.loads(original)
  state['revision']+=1;f.state_path.write_text(json.dumps(state))
  with self.assertRaises(self.m.RecoveryError):read(f.job,f.root,f.runtime,f.home)
  f.state_path.write_bytes(original);state=json.loads(original);state['approvals']['review']['kind']='auto_delegated';f.state_path.write_text(json.dumps(state))
  with self.assertRaises(self.m.RecoveryError):read(f.job,f.root,f.runtime,f.home)
 def test_dirty_worktree_and_extra_config_change_refuse(self):
  read=self.api('read_legacy_context');f=self.fixture();tracked=f.root/'tracked.txt';tracked.write_bytes(b'unapproved\n')
  with self.assertRaises(self.m.RecoveryError):read(f.job,f.root,f.runtime,f.home)
  tracked.write_bytes(b'two\n');config=f.root/'.git/config';config.write_bytes(config.read_bytes()+b'[credential]\n\thelper = unapproved\n')
  with self.assertRaises(self.m.RecoveryError):read(f.job,f.root,f.runtime,f.home)
 def test_grafts_and_public_commit_job_refuse(self):
  read=self.api('read_legacy_context');f=self.fixture();graft=f.root/'.git/info/grafts';graft.write_text('')
  with self.assertRaises(self.m.RecoveryError):read(f.job,f.root,f.runtime,f.home)
  graft.unlink();f.job.chmod(0o644)
  with self.assertRaises(self.m.RecoveryError):read(f.job,f.root,f.runtime,f.home)

class LifecycleTests(RecoveryCase):
 def setUp(self):
  super().setUp();self.temp=tempfile.TemporaryDirectory(prefix='fitlog-lifecycle-',dir='/private/tmp');self.addCleanup(self.temp.cleanup)
  self.home=Path(self.temp.name)/'home';self.home.mkdir(mode=0o700);self.folder=self.home/'records';self.folder.mkdir(mode=0o700)
 def ticket(self,action='delivery'):
  return {'schema_version':1,'kind':'environment_recovery_ticket','action':action,'created_at':1000,'expires_at':1900,'ticket_digest':'a'*64}
 def test_ticket_time_rejects_bool_future_expired_or_extended_window(self):
  check=self.api('check_ticket_time');check(self.ticket(),1000);check(self.ticket(),1899)
  for now in [999,1900,1901]:
   with self.subTest(now=now),self.assertRaises(self.m.RecoveryError):check(self.ticket(),now)
  for field,value in [('created_at',True),('expires_at',1901),('expires_at',False)]:
   ticket=self.ticket();ticket[field]=value
   with self.subTest(field=field,value=value),self.assertRaises(self.m.RecoveryError):check(ticket,1000)
 def test_confirmation_is_one_exact_line_and_requires_real_terminal(self):
  confirm=self.api('confirm_ticket');expected='APPROVE ENV-RECOVERY '+('a'*16)
  for line in [' '+expected,expected+' ',expected.upper(),expected+'x',expected+'\x01','APPROVE ENV-RECOVERY '+('a'*12),'']:
   with self.subTest(line=line),self.assertRaises(self.m.RecoveryError):confirm(self.ticket(),input_fn=lambda _:line,terminal_check=lambda:True,output=io.StringIO())
  with self.assertRaises(self.m.RecoveryError):confirm(self.ticket(),input_fn=lambda _:expected,terminal_check=lambda:False,output=io.StringIO())
  def eof(_):raise EOFError
  with self.assertRaises(self.m.RecoveryError):confirm(self.ticket(),input_fn=eof,terminal_check=lambda:True,output=io.StringIO())
  confirm(self.ticket(),input_fn=lambda _:expected,terminal_check=lambda:True,output=io.StringIO())
  confirm(self.ticket('pr'),input_fn=lambda _:'APPROVE ENV-RECOVERY-PR '+('a'*16),terminal_check=lambda:True,output=io.StringIO())
 def test_unresolved_intent_blocks_even_when_remote_might_already_match(self):
  check=self.api('check_namespace');namespace=self.folder
  check(namespace,self.home)
  intent=self.m.seal({'schema_version':1,'kind':'environment_recovery_intent','ticket_digest':'b'*64,'started_at':1000},'intent_digest')
  self.m.write_new(namespace/('ticket-'+('b'*64)+'.intent.json'),intent,self.home)
  with self.assertRaises(self.m.RecoveryError):check(namespace,self.home)
 def test_bounded_child_preserves_exact_argv_env_and_no_parent_inheritance(self):
  run=self.api('run_bounded')
  environment=self.m.basic_environment(self.home)
  with mock.patch.object(self.m.subprocess,'Popen',wraps=subprocess.Popen) as spawn:
   result=run([self.m.PYTHON,'-I','-S','-B','-c','import os,json,sys;print(json.dumps([sys.argv[1:],dict(os.environ)]))','literal $ not shell'],env=environment,cwd=self.home,timeout=5)
  self.assertEqual(spawn.call_args.kwargs['env'],environment)
  argv,env=json.loads(result.stdout);self.assertEqual(argv,['literal $ not shell'])
  self.assertEqual({key:value for key,value in env.items() if key!='__CF_USER_TEXT_ENCODING'},environment)
  self.assertFalse({'GH_TOKEN','GIT_SSH_COMMAND','PYTHONPATH'} & env.keys())
 def test_timeout_terminates_process_group_including_grandchild(self):
  run=self.api('run_bounded');marker=self.folder/'escaped-child'
  code="import subprocess,time;subprocess.Popen(["+repr(self.m.PYTHON)+",'-I','-S','-B','-c',"+repr("import time,pathlib;time.sleep(1);pathlib.Path("+repr(str(marker))+").write_text('escaped')")+"]);time.sleep(20)"
  with self.assertRaises(self.m.RecoveryError):run([self.m.PYTHON,'-I','-S','-B','-c',code],env=self.m.basic_environment(self.home),cwd=self.home,timeout=.2)
  import time;time.sleep(1.1);self.assertFalse(marker.exists())

 def test_launch_guard_runs_after_cwd_preparation_before_popen(self):
  clock=[1899];canonical=self.m.canonical
  def delayed(path):
   value=canonical(path);clock[0]=1900;return value
  def guard():
   if clock[0]>=1900:raise self.m.ChildNotStarted('V9_ENV_RECOVERY: ticket_expired_before_start')
  with mock.patch.object(self.m,'canonical',side_effect=delayed),mock.patch.object(self.m.subprocess,'Popen',side_effect=AssertionError('must not spawn expired operation')) as spawn:
   with self.assertRaises(self.m.ChildNotStarted):self.m.run_bounded([self.m.PYTHON,'-I','-S','-B','-c','pass'],env=self.m.basic_environment(self.home),cwd=self.home,timeout=5,before_start=guard)
  spawn.assert_not_called()


class DeliveryTests(RecoveryCase):
 def setUp(self):
  super().setUp();self.temp=tempfile.TemporaryDirectory(prefix='fitlog-delivery-',dir='/private/tmp');self.addCleanup(self.temp.cleanup)
  self.home=Path(self.temp.name)/'home';self.home.mkdir(mode=0o700);self.now=1000;self.sent=[];self.remote=None
  self.context={'schema_version':1,'project':str(self.home/'project'),'task':'fixture','commit':'1'*40,'parent':'2'*40,'tree':'3'*40,'branch':'feat/fixture','origin_job':str(self.home/'ledger'/('commit-'+('4'*64)+'.json')),'origin_job_sha256':'5'*64,'origin_result_sha256':'6'*64,'state_sha256':'7'*64,'workflow_revision':3,'binding_digest':'8'*64,'approvals_digest':'9'*64,'snapshot_hash':'a'*64,'runtime':'/fixture/runtime','runtime_digest':'b'*64,'policy_digest':'c'*64,'personal_environment':{'account':'koma236','configs':[],'gh_config_dir':'/fixture/gh','git_config_file':'/fixture/git'},'original_personal_environment':{},'delta':{'kind':'main_vscode_metadata_added'},'remote':{'name':'origin','fetch_url':'https://github.com/koma236/FitLog.git','push_url':'https://github.com/koma236/FitLog.git','repository':'koma236/FitLog'},'normal_records_digest':'d'*64}
  self.source={'project':str(self.home/'source'),'head':'e'*40,'files':{'controller':'f'*64}}
 def lane(self):
  cls=self.api('RecoveryLane');return cls(self.home,self.source,lambda _job,_project:self.context,self.transport,lambda:self.now)
 def transport(self,context,operation,payload=None,started=None,before_start=None):
  if operation=='identity':return None
  if operation=='observe':return self.remote
  if operation=='deliver':
   if before_start:before_start()
   self.sent.append(payload)
   if started:started(12345)
   self.remote='1'*40;return None
  raise AssertionError('Unexpected operation '+operation)
 def prepare(self,lane):return lane.prepare(Path(self.context['origin_job']),Path(self.context['project']))
 def execute(self,lane,path,change=None):
  ticket=json.loads(path.read_text())
  def confirm(_):
   if change:change()
   return 'APPROVE ENV-RECOVERY '+ticket['ticket_digest'][:16]
  return lane.execute(path,Path(self.context['project']),input_fn=confirm,terminal_check=lambda:True,output=io.StringIO())
 def test_absent_ref_delivers_immutable_sha_and_status_is_read_only(self):
  lane=self.lane();path=self.prepare(lane);result_path=self.execute(lane,path)
  self.assertEqual(self.sent,['1'*40+':refs/heads/feat/fixture'])
  before={str(p):(p.read_bytes(),p.stat().st_mtime_ns) for p in self.home.rglob('*') if p.is_file()}
  proof=lane.status(result_path,Path(self.context['project']))
  self.assertEqual(proof['remote_sha'],'1'*40);self.assertEqual(proof['mode'],'sent')
  after={str(p):(p.read_bytes(),p.stat().st_mtime_ns) for p in self.home.rglob('*') if p.is_file()};self.assertEqual(before,after)
  with self.assertRaises(self.m.RecoveryError):self.execute(lane,path)
 def test_existing_same_sha_is_observation_only_not_a_send(self):
  lane=self.lane();self.remote='1'*40;path=self.prepare(lane);result=self.execute(lane,path)
  self.assertEqual(self.sent,[]);self.assertEqual(lane.status(result,Path(self.context['project']))['mode'],'observed')
 def test_different_sha_and_approval_wait_drift_never_send(self):
  lane=self.lane();self.remote='2'*40
  with self.assertRaises(self.m.RecoveryError):self.prepare(lane)
  self.remote=None;path=self.prepare(lane)
  with self.assertRaises(self.m.RecoveryError):self.execute(lane,path,lambda:setattr(self,'remote','1'*40))
  self.assertEqual(self.sent,[])
 def test_context_drift_while_waiting_never_sends(self):
  lane=self.lane();path=self.prepare(lane)
  with self.assertRaises(self.m.RecoveryError):self.execute(lane,path,lambda:self.context.update(commit='2'*40))
  self.assertEqual(self.sent,[])
 def test_timeout_after_worker_start_is_unknown_and_prevents_retry(self):
  lane=self.lane();path=self.prepare(lane);original=lane.transport
  def broken(context,operation,payload=None,started=None,before_start=None):
   if operation=='deliver':
    started(12345);raise self.m.RecoveryError('V9_ENV_RECOVERY: child_timeout_or_output_limit')
   return original(context,operation,payload,started,before_start)
  lane.transport=broken
  with self.assertRaises(self.m.RecoveryError):self.execute(lane,path)
  value=json.loads(path.with_suffix('.result.json').read_text());self.assertEqual(value['status'],'unknown')
  with self.assertRaises(self.m.RecoveryError):self.prepare(lane)
  with self.assertRaises(self.m.RecoveryError):lane.status(path.with_suffix('.result.json'),Path(self.context['project']))
 def test_changed_post_readback_never_produces_success(self):
  lane=self.lane();path=self.prepare(lane);original=lane.transport
  def mismatched(context,operation,payload=None,started=None,before_start=None):
   result=original(context,operation,payload,started,before_start)
   if operation=='deliver':self.remote='2'*40
   return result
  lane.transport=mismatched
  with self.assertRaises(self.m.RecoveryError):self.execute(lane,path)
  self.assertEqual(json.loads(path.with_suffix('.result.json').read_text())['status'],'unknown')
 def test_boolean_schema_is_not_integer_schema_one(self):
  lane=self.lane();path=self.prepare(lane);value=json.loads(path.read_text());value['schema_version']=True;value.pop('ticket_digest');value=self.m.seal(value,'ticket_digest')
  forged=path.with_name('ticket-'+value['ticket_digest']+'.json');self.m.write_new(forged,value,self.home)
  with self.assertRaises(self.m.RecoveryError):lane.read_ticket(forged,Path(self.context['project']))
 def test_expired_ticket_rejects_before_intent_or_send(self):
  lane=self.lane();path=self.prepare(lane);self.now=1900
  with self.assertRaises(self.m.RecoveryError):self.execute(lane,path)
  self.assertFalse(path.with_suffix('.intent.json').exists());self.assertEqual(self.sent,[])


 def test_child_effect_before_tracking_callback_is_unknown_and_blocks_new_ticket(self):
  import time
  lane=self.lane();path=self.prepare(lane);marker=self.home/'child-effect';original=lane.transport
  def real_child(context,operation,payload=None,started=None,before_start=None):
   if operation!='deliver':return original(context,operation,payload,started,before_start)
   if before_start:before_start()
   code="from pathlib import Path;Path("+repr(str(marker))+").write_text('effect');import time;time.sleep(20)"
   return self.m.run_bounded([self.m.PYTHON,'-I','-S','-B','-c',code],env=self.m.basic_environment(self.home),cwd=self.home,timeout=5,started=started)
  lane.transport=real_child;fired=False
  def trace(frame,event,arg):
   nonlocal fired
   if not fired and event=='line' and frame.f_code.co_name=='run_bounded' and frame.f_code.co_filename==self.m.__file__ and getattr(frame.f_locals.get('process'),'pid',None):
    fired=True;end=time.monotonic()+2
    while not marker.exists() and time.monotonic()<end:time.sleep(.01)
    raise KeyboardInterrupt('fixture interruption before tracking callback')
   return trace
  previous=sys.gettrace()
  try:
   sys.settrace(trace)
   with self.assertRaises(KeyboardInterrupt):self.execute(lane,path)
  finally:sys.settrace(previous)
  self.assertTrue(marker.exists());self.assertFalse(path.with_suffix('.worker.json').exists())
  self.assertEqual(json.loads(path.with_suffix('.result.json').read_text())['status'],'unknown')
  self.now+=1
  with self.assertRaises(self.m.RecoveryError):self.prepare(lane)
 def test_constructor_interruption_is_unknown(self):
  lane=self.lane();path=self.prepare(lane);original=lane.transport
  def child(context,operation,payload=None,started=None,before_start=None):
   if operation!='deliver':return original(context,operation,payload,started,before_start)
   if before_start:before_start()
   return self.m.run_bounded([self.m.PYTHON,'-I','-S','-B','-c','pass'],env=self.m.basic_environment(self.home),cwd=self.home,timeout=5,started=started)
  lane.transport=child
  with mock.patch.object(self.m.subprocess,'Popen',side_effect=KeyboardInterrupt('uncertain constructor')):
   with self.assertRaises(KeyboardInterrupt):self.execute(lane,path)
  self.assertEqual(json.loads(path.with_suffix('.result.json').read_text())['status'],'unknown');self.now+=1
  with self.assertRaises(self.m.RecoveryError):self.prepare(lane)
 def test_expiry_during_final_revalidation_has_no_intent_or_send(self):
  lane=self.lane();path=self.prepare(lane);reader=lane.context_reader;calls=1;self.now=1899
  def expire(job,project):
   nonlocal calls
   calls+=1
   if calls==3:self.now=1900
   return reader(job,project)
  lane.context_reader=expire
  with self.assertRaises(self.m.RecoveryError):self.execute(lane,path)
  self.assertEqual(self.sent,[]);self.assertFalse(path.with_suffix('.intent.json').exists());self.assertFalse(path.with_suffix('.result.json').exists())
 def test_expiry_during_intent_publication_never_starts_transport(self):
  lane=self.lane();path=self.prepare(lane);write=self.m.write_new;self.now=1899
  def delayed(file,value,home):
   result=write(file,value,home)
   if file.name.endswith('.intent.json'):self.now=1900
   return result
  with mock.patch.object(self.m,'write_new',side_effect=delayed),self.assertRaises(self.m.RecoveryError):self.execute(lane,path)
  self.assertEqual(self.sent,[]);self.assertEqual(json.loads(path.with_suffix('.result.json').read_text())['status'],'failed')


 def test_constructor_exec_error_is_uncertain_and_blocks_fresh_ticket(self):
  lane=self.lane();path=self.prepare(lane);original=lane.transport
  def child(context,operation,payload=None,started=None,before_start=None):
   if operation!='deliver':return original(context,operation,payload,started,before_start)
   if before_start:before_start()
   return self.m.run_bounded([self.m.PYTHON,'-I','-S','-B','-c','pass'],env=self.m.basic_environment(self.home),cwd=self.home,timeout=5,started=started)
  lane.transport=child
  with mock.patch.object(self.m.subprocess,'Popen',side_effect=FileNotFoundError(2,'fixture exec absent')):
   with self.assertRaises(self.m.RecoveryError):self.execute(lane,path)
  self.assertEqual(json.loads(path.with_suffix('.result.json').read_text())['status'],'unknown');self.assertFalse(path.with_suffix('.worker.json').exists())
  self.now+=1
  with self.assertRaises(self.m.RecoveryError):self.prepare(lane)
 def test_completion_after_expiry_is_valid_when_started_before_expiry(self):
  lane=self.lane();path=self.prepare(lane);self.now=1899;original=lane.transport
  def long_send(context,operation,payload=None,started=None,before_start=None):
   value=original(context,operation,payload,started,before_start)
   if operation=='deliver':self.now=1901
   return value
  lane.transport=long_send;result=self.execute(lane,path);self.assertEqual(lane.status(result,Path(self.context['project']))['remote_sha'],'1'*40)


 def test_readback_child_start_failure_after_send_remains_unknown(self):
  lane=self.lane();path=self.prepare(lane);original=lane.transport
  def readback_failure(context,operation,payload=None,started=None,before_start=None):
   if operation=='observe' and self.sent:raise self.m.ChildNotStarted('V9_ENV_RECOVERY: child_start_failed')
   return original(context,operation,payload,started,before_start)
  lane.transport=readback_failure
  with self.assertRaises(self.m.RecoveryError):self.execute(lane,path)
  self.assertEqual(len(self.sent),1);self.assertEqual(json.loads(path.with_suffix('.result.json').read_text())['status'],'unknown');self.now+=1
  with self.assertRaises(self.m.RecoveryError):self.prepare(lane)
 def test_post_send_legacy_worker_start_failure_remains_unknown(self):
  lane=self.lane();path=self.prepare(lane);reader=lane.context_reader
  def worker_failure(job,project):
   if self.sent:raise self.m.ChildNotStarted('V9_ENV_RECOVERY: child_start_failed')
   return reader(job,project)
  lane.context_reader=worker_failure
  with self.assertRaises(self.m.RecoveryError):self.execute(lane,path)
  self.assertEqual(len(self.sent),1);self.assertEqual(json.loads(path.with_suffix('.result.json').read_text())['status'],'unknown');self.now+=1
  with self.assertRaises(self.m.RecoveryError):self.prepare(lane)


 def test_constructor_parent_io_after_real_child_effect_is_unknown(self):
  import errno,time
  lane=self.lane();path=self.prepare(lane);marker=self.home/'constructor-effect';original=lane.transport;read=os.read;caught=[]
  def parent_read(fd,size):
   frame=sys._getframe(1)
   if frame.f_code.co_name=='_execute_child' and fd==frame.f_locals.get('errpipe_read'):
    caught.append(frame.f_locals['self']);deadline=time.monotonic()+3
    while not marker.exists() and time.monotonic()<deadline:time.sleep(.01)
    self.assertTrue(marker.exists());raise OSError(errno.EIO,'fixture constructor parent I/O failure')
   return read(fd,size)
  def child(context,operation,payload=None,started=None,before_start=None):
   if operation!='deliver':return original(context,operation,payload,started,before_start)
   code="from pathlib import Path;Path("+repr(str(marker))+").write_text('effect')"
   with mock.patch.object(os,'read',new=parent_read):
    return self.m.run_bounded([self.m.PYTHON,'-I','-S','-B','-c',code],env=self.m.basic_environment(self.home),cwd=self.home,timeout=5,started=started,before_start=before_start)
  lane.transport=child
  try:
   with self.assertRaises(self.m.RecoveryError):self.execute(lane,path)
  finally:
   for process in caught:process.wait(timeout=3)
  self.assertTrue(caught);self.assertTrue(marker.exists());self.assertEqual(json.loads(path.with_suffix('.result.json').read_text())['status'],'unknown');self.now+=1
  with self.assertRaises(self.m.RecoveryError):self.prepare(lane)
 def test_pre_spawn_preparation_failure_is_failed_and_allows_fresh_ticket(self):
  lane=self.lane();path=self.prepare(lane);original=lane.transport
  def child(context,operation,payload=None,started=None,before_start=None):
   if operation!='deliver':return original(context,operation,payload,started,before_start)
   return self.m.run_bounded([self.m.PYTHON,'-I','-S','-B','-c','pass'],env=self.m.basic_environment(self.home),cwd=self.home,timeout=5,started=started,before_start=before_start)
  lane.transport=child
  with mock.patch.object(self.m.tempfile,'TemporaryFile',side_effect=PermissionError(13,'fixture scratch unavailable')),mock.patch.object(self.m.subprocess,'Popen') as spawn:
   with self.assertRaises(self.m.ChildNotStarted):self.execute(lane,path)
  spawn.assert_not_called();self.assertEqual(json.loads(path.with_suffix('.result.json').read_text())['status'],'failed');self.now+=1
  self.assertTrue(self.prepare(lane).exists())


class PrTests(DeliveryTests):
 def setUp(self):
  super().setUp();self.pr=None;self.creations=0
  self.body=self.home/'body.txt';self.body.write_text('Reviewed fixture body\n');self.body.chmod(0o600)
 def transport(self,context,operation,payload=None,started=None,before_start=None):
  if operation=='find-pr':return self.pr
  if operation=='create-pr':
   if before_start:before_start()
   if started:started(12345)
   self.creations+=1;self.pr={'repository':'koma236/FitLog','head':'feat/fixture','head_sha':'1'*40,'base':'main','url':'https://github.com/koma236/FitLog/pull/19'};return None
  return super().transport(context,operation,payload,started,before_start)
 def delivered(self,lane):return self.execute(lane,self.prepare(lane))
 def approve_pr(self,lane,path,change=None):
  ticket=json.loads(path.read_text())
  def approve(_):
   if change:change()
   return 'APPROVE ENV-RECOVERY-PR '+ticket['ticket_digest'][:16]
  return lane.execute(path,Path(self.context['project']),input_fn=approve,terminal_check=lambda:True,output=io.StringIO())
 def test_pr_needs_successful_delivery_and_separate_exact_confirmation(self):
  lane=self.lane();delivery=self.delivered(lane)
  prepare=getattr(lane,'prepare_pr',None);self.assertTrue(callable(prepare),'Approved prepare-pr behavior not implemented')
  path=prepare(delivery,Path(self.context['project']),'main','Fixture title',self.body)
  self.assertEqual(self.creations,0)
  ticket=json.loads(path.read_text())
  with self.assertRaises(self.m.RecoveryError):lane.execute(path,Path(self.context['project']),input_fn=lambda _:'APPROVE ENV-RECOVERY '+ticket['ticket_digest'][:16],terminal_check=lambda:True,output=io.StringIO())
  result=self.approve_pr(lane,path);self.assertEqual(json.loads(result.read_text())['status'],'succeeded');self.assertEqual(self.creations,1)
 def test_pr_body_or_remote_drift_while_waiting_refuses_creation(self):
  lane=self.lane();delivery=self.delivered(lane)
  prepare=getattr(lane,'prepare_pr',None);self.assertTrue(callable(prepare),'Approved prepare-pr behavior not implemented')
  path=prepare(delivery,Path(self.context['project']),'main','Fixture title',self.body)
  with self.assertRaises(self.m.RecoveryError):self.approve_pr(lane,path,lambda:self.body.write_text('Unapproved changed body'))
  self.assertEqual(self.creations,0)
 def test_existing_matching_pr_is_observed_and_conflicting_pr_refuses(self):
  lane=self.lane();delivery=self.delivered(lane)
  prepare=getattr(lane,'prepare_pr',None);self.assertTrue(callable(prepare),'Approved prepare-pr behavior not implemented')
  self.pr={'repository':'koma236/FitLog','head':'feat/fixture','head_sha':'1'*40,'base':'main','url':'https://github.com/koma236/FitLog/pull/19'}
  path=prepare(delivery,Path(self.context['project']),'main','Fixture title',self.body);result=self.approve_pr(lane,path)
  self.assertEqual(self.creations,0);self.assertEqual(json.loads(result.read_text())['mode'],'observed')
  self.now+=1;self.pr['head_sha']='2'*40
  with self.assertRaises(self.m.RecoveryError):prepare(delivery,Path(self.context['project']),'main','Fixture title',self.body)


 def test_company_body_case_alias_is_refused_before_open(self):
  lane=self.lane();delivery=self.delivered(lane);directory=self.home/'.codex';directory.mkdir(mode=0o700)
  body=directory/'body.txt';body.write_text('fake company body');body.chmod(0o600);alias=self.home/'.CoDeX/body.txt'
  with mock.patch.object(self.m.pwd,'getpwuid',return_value=types.SimpleNamespace(pw_dir=str(self.home))):
   with mock.patch.object(self.m.os,'open',wraps=os.open) as opened:
    with self.assertRaises(self.m.RecoveryError):lane.prepare_pr(delivery,Path(self.context['project']),'main','Fixture title',alias)
   self.assertFalse(any(str(call.args[0])==str(alias) for call in opened.call_args_list))


class TransportTests(RecoveryCase):
 def setUp(self):
  super().setUp();self.temp=tempfile.TemporaryDirectory(prefix='fitlog-transport-',dir='/private/tmp');self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name);self.context={'project':str(self.root),'branch':'feat/fixed','commit':'1'*40,'personal_environment':{'git_config_file':str(self.root/'personal.git'),'gh_config_dir':str(self.root/'personal-gh')},'remote':{'name':'origin','repository':'koma236/FitLog','fetch_url':'https://github.com/koma236/FitLog.git','push_url':'https://github.com/koma236/FitLog.git'}}
 def transport(self):return self.api('FixedTransport')(self.root)
 def test_delivery_has_fixed_binary_nonforce_immutable_source_and_profile_only(self):
  transport=self.transport();calls=[]
  def child(argv,**kwargs):calls.append((argv,kwargs));return subprocess.CompletedProcess(argv,0,b'',b'')
  with mock.patch.object(self.m,'run_bounded',side_effect=child):transport(self.context,'deliver','1'*40+':refs/heads/feat/fixed',lambda _pid:None)
  argv,options=calls[0]
  self.assertEqual(argv,['/usr/bin/git','-c','core.fsmonitor=false','push','https://github.com/koma236/FitLog.git','1'*40+':refs/heads/feat/fixed'])
  self.assertEqual(options['env']['GIT_CONFIG_GLOBAL'],str(self.root/'personal.git'));self.assertEqual(options['env']['GH_CONFIG_DIR'],str(self.root/'personal-gh'))
  self.assertEqual(options['env']['GIT_NO_REPLACE_OBJECTS'],'1');self.assertNotIn('GH_TOKEN',options['env']);self.assertNotIn('GIT_SSH_COMMAND',options['env'])
  with self.assertRaises(self.m.RecoveryError):transport(self.context,'deliver','HEAD:refs/heads/feat/fixed')
 def test_remote_output_must_be_absent_or_one_exact_ref(self):
  transport=self.transport()
  for raw,expected in [(b'',None),((('1'*40)+'\trefs/heads/feat/fixed\n').encode(),'1'*40)]:
   with mock.patch.object(self.m,'run_bounded',return_value=subprocess.CompletedProcess([],0,raw,b'')):self.assertEqual(transport(self.context,'observe'),expected)
  for raw in [b'not-a-sha\trefs/heads/feat/fixed\n',(('1'*40)+'\trefs/heads/other\n').encode(),((('1'*40)+'\trefs/heads/feat/fixed\n')*2).encode()]:
   with mock.patch.object(self.m,'run_bounded',return_value=subprocess.CompletedProcess([],0,raw,b'')),self.assertRaises(self.m.RecoveryError):transport(self.context,'observe')
 def test_unknown_transport_operation_is_never_a_command_callback(self):
  transport=self.transport()
  with mock.patch.object(self.m,'run_bounded') as child,self.assertRaises(self.m.RecoveryError):transport(self.context,'arbitrary-command',['/bin/sh'])
  child.assert_not_called()
 def test_real_bare_repo_receives_literal_approved_sha_even_if_head_changes(self):
  transport=self.transport();source=self.root/'source';source.mkdir();bare=self.root/'remote.git';env=self.m.basic_environment(self.root)
  def git(*args,cwd=source):return subprocess.check_output(['/usr/bin/git','-c','user.name=Fixture','-c','user.email=fixture@example.invalid',*args],cwd=cwd,env=env,stderr=subprocess.PIPE).decode().strip()
  git('init','-b','feat/fixed');(source/'tracked').write_text('approved');git('add','tracked');git('commit','-m','approved');approved=git('rev-parse','HEAD')
  (source/'tracked').write_text('unapproved');git('add','tracked');git('commit','-m','unapproved');self.assertNotEqual(approved,git('rev-parse','HEAD'));git('init','--bare',str(bare))
  self.context.update(project=str(source),commit=approved)
  real=self.m.run_bounded;seen=[]
  def fake_transport_only(argv,**kwargs):
   seen.append(argv.copy());rewritten=[str(bare) if item=='https://github.com/koma236/FitLog.git' else item for item in argv]
   return real(rewritten,**kwargs)
  with mock.patch.object(self.m,'run_bounded',side_effect=fake_transport_only):transport(self.context,'deliver',approved+':refs/heads/feat/fixed')
  self.assertEqual(git('rev-parse','refs/heads/feat/fixed',cwd=bare),approved);self.assertEqual(seen[0][-1],approved+':refs/heads/feat/fixed')


 def test_mutating_transport_forwards_guard_to_real_spawn_boundary(self):
  transport=self.transport();guard=lambda:None
  with mock.patch.object(self.m,'run_bounded',return_value=subprocess.CompletedProcess([],0,b'',b'')) as run:
   transport(self.context,'deliver','1'*40+':refs/heads/feat/fixed',None,guard)
  self.assertIs(run.call_args.kwargs['before_start'],guard)


class SourceTests(RecoveryCase):
 def setUp(self):
  super().setUp();self.temp=tempfile.TemporaryDirectory(prefix='fitlog-source-',dir='/private/tmp');self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name);self.env=self.m.basic_environment(self.root)
 def git(self,*args):return subprocess.check_output(['/usr/bin/git','-c','user.name=Fixture','-c','user.email=fixture@example.invalid',*args],cwd=self.root,env=self.env,stderr=subprocess.PIPE).decode().strip()
 def fixture(self):
  files=['.claude/hooks/quality-gate.cjs','.codex/hooks/quality-gate.cjs','.ai-dev/v9-git-entrypoints.json','.ai-dev/v9-env-recovery.json','bin/ai-dev-git-env-recovery','scripts/v9_git_environment_recovery.py']
  self.git('init','-b','feat/recovery')
  for rel in files:
   target=self.root/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_text('fixture '+rel);target.chmod(0o755 if rel.startswith('bin/') else 0o600)
  self.git('add','.');self.git('commit','-m','fixture')
  return files
 def test_source_must_match_committed_raw_bytes_and_modes(self):
  check=self.api('committed_source');files=self.fixture();value=check(self.root)
  self.assertEqual(value['head'],self.git('rev-parse','HEAD'));self.assertEqual(set(value['files']),set(files))
  target=self.root/'scripts/v9_git_environment_recovery.py';target.write_text('uncommitted change')
  with self.assertRaises(self.m.RecoveryError):check(self.root)
 def test_source_executable_mode_and_plain_index_are_required(self):
  check=self.api('committed_source');self.fixture();launcher=self.root/'bin/ai-dev-git-env-recovery';launcher.chmod(0o600)
  with self.assertRaises(self.m.RecoveryError):check(self.root)
  launcher.chmod(0o755);self.git('update-index','--assume-unchanged','scripts/v9_git_environment_recovery.py')
  with self.assertRaises(self.m.RecoveryError):check(self.root)
 def test_python_identity_is_fixed_to_host_binary_and_ancestors(self):
  check=self.api('verify_python');check()
  real=self.m.sha
  with mock.patch.object(self.m,'sha',return_value='0'*64),self.assertRaises(self.m.RecoveryError):check()


class LauncherTests(RecoveryCase):
 def setUp(self):
  super().setUp();self.temp=tempfile.TemporaryDirectory(prefix='fitlog-launcher-',dir='/private/tmp');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  source=ROOT/'bin/ai-dev-git-env-recovery'
  if not source.is_file():self.fail('Approved launcher not implemented')
  (self.root/'bin').mkdir();(self.root/'scripts').mkdir();self.launcher=self.root/'bin/ai-dev-git-env-recovery';self.launcher.write_bytes(source.read_bytes());self.launcher.chmod(0o755)
  (self.root/'scripts/v9_git_environment_recovery.py').write_text('import os,sys,json;print(json.dumps([sys.argv[1:],dict(os.environ)]))')
  self.env={'PATH':'/usr/bin:/bin','HOME':'/Users/saki','CODEX_HOME':'/Users/saki/.codex-personal'}
 def run_launcher(self,extra=None,args=None):return subprocess.run([str(self.launcher),*(args or ['prepare','literal $ argument'])],env={**self.env,**(extra or {})},cwd=self.root,capture_output=True,timeout=5)
 def test_closed_child_environment_and_literal_arguments(self):
  result=self.run_launcher({'SAFE_EXTRA':'not inherited'});self.assertEqual(result.returncode,0,result.stderr)
  argv,env=json.loads(result.stdout);self.assertEqual(argv,['prepare','literal $ argument']);self.assertNotIn('SAFE_EXTRA',env)
  self.assertEqual(set(env)-{'__CF_USER_TEXT_ENCODING'},{'HOME','CODEX_HOME','PATH','TMPDIR','LANG','LC_ALL'})
  self.assertEqual(env['PATH'],'/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin')
 def test_observable_dangerous_names_fail_before_controller_and_do_not_echo_values(self):
  for name in ['GIT_DIR','GIT_CONFIG_COUNT','GIT_CONFIG_KEY_4','GIT_SSH_COMMAND','GH_TOKEN','PYTHONPATH','BASH_ENV','ENV','LD_PRELOAD','VSCODE_GIT_ASKPASS_NODE']:
   result=self.run_launcher({name:'private-value-marker'})
   with self.subTest(name=name):self.assertNotEqual(result.returncode,0);self.assertEqual(result.stdout,b'');self.assertNotIn(b'private-value-marker',result.stderr)
 def test_legacy_function_export_is_neutralized_and_not_inherited(self):
  marker=self.root/'function-executed'
  result=self.run_launcher({'printf':'() { touch '+str(marker)+'; }'})
  self.assertEqual(result.returncode,0,result.stderr);self.assertFalse(marker.exists())
  self.assertNotIn('printf',json.loads(result.stdout)[1])
 def test_internal_worker_and_unknown_action_are_not_public_launcher_actions(self):
  for action in ['_read-context','unknown-action']:
   result=self.run_launcher(args=[action]);self.assertNotEqual(result.returncode,0);self.assertEqual(result.stdout,b'')
 def test_home_mismatch_and_startup_marker_refuse_without_execution(self):
  startup=self.root/'startup';marker=self.root/'executed';startup.write_text('touch '+str(marker)+'\n')
  result=self.run_launcher({'BASH_ENV':str(startup)});self.assertNotEqual(result.returncode,0);self.assertFalse(marker.exists())
  for extra in [{'HOME':'/private/tmp'},{'CODEX_HOME':'/private/tmp'}]:self.assertNotEqual(self.run_launcher(extra).returncode,0)


class PublicationFailureTests(PrivateRecordTests):
 def test_directory_sync_failure_removes_only_this_unpublished_result(self):
  path=self.folder/'new-result.json';real=self.m.os.fsync
  def broken(fd):
   import stat
   if stat.S_ISDIR(os.fstat(fd).st_mode):raise OSError('fixture directory sync failure')
   return real(fd)
  with mock.patch.object(self.m.os,'fsync',side_effect=broken),self.assertRaises(self.m.RecoveryError):self.m.write_new(path,{'status':'succeeded'},self.home)
  self.assertFalse(path.exists())


class PathBoundaryTests(RecoveryCase):
 def test_company_path_is_rejected_before_resolving_or_reading_it(self):
  import pwd
  target=Path(pwd.getpwuid(os.getuid()).pw_dir)/'.codex'/'never-read-this.json'
  with mock.patch.object(Path,'resolve',side_effect=AssertionError('must not resolve company path')),self.assertRaises(self.m.RecoveryError):self.m.canonical(target)


 def test_company_case_alias_is_refused_before_resolution(self):
  with tempfile.TemporaryDirectory(prefix='fitlog-case-alias-',dir='/private/tmp') as folder:
   home=Path(folder)/'home';home.mkdir(mode=0o700)
   for name in ['.CoDeX','.CODEX']:
    target=home/name/'marker.json'
    with mock.patch.object(self.m.pwd,'getpwuid',return_value=types.SimpleNamespace(pw_dir=str(home))):
     with mock.patch.object(Path,'resolve',side_effect=AssertionError('must not resolve case alias')),self.assertRaises(self.m.RecoveryError):self.m.canonical(target)


if __name__=='__main__':unittest.main()
