"""Explicit environment recovery; original v9 records remain read-only."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import stat
import fcntl
import pwd
import sys
import importlib.abc
import importlib.util

REPOSITORY='koma236/FitLog'
ACCOUNT='koma236'
PYTHON='/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12'
FIXED_PATH='/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin'
MAX_RECORD=1024*1024
METADATA_LINE=b'\tvscode-merge-base = origin/main\n'
MAIN_HEADER=b'[branch "main"]\n'

class RecoveryError(ValueError):
    """Only fixed diagnostic categories; never input/config/credential excerpts."""

class ChildNotStarted(RecoveryError):
    """Positive proof of refusal/failure before entering process construction."""

def fail(category):
    raise RecoveryError('V9_ENV_RECOVERY: '+category)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def digest(value):
    return sha(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())

def strict_json(raw):
    if not isinstance(raw,bytes) or len(raw)>MAX_RECORD:fail('record_json_refused')
    def pairs(items):
        value={}
        for key,item in items:
            if key in value:fail('record_json_refused')
            value[key]=item
        return value
    try:
        value=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,
                         parse_constant=lambda _value:fail('record_json_refused'))
        if not isinstance(value,dict):fail('record_json_refused')
        json.dumps(value,ensure_ascii=False).encode('utf-8')
    except (ValueError,UnicodeError,RecursionError):
        fail('record_json_refused')
    return value

def parse_commit(raw):
    if not isinstance(raw,bytes) or len(raw)>MAX_RECORD or b'\0' in raw or b'\n\n' not in raw:
        fail('commit_object_refused')
    headers=raw.split(b'\n\n',1)[0].split(b'\n')
    result={}
    for key in ('tree','parent'):
        values=[line[len(key)+1:] for line in headers if line.startswith(key.encode()+b' ')]
        if len(values)!=1 or not re.fullmatch(b'[0-9a-f]{40}',values[0]):fail('commit_object_refused')
        result[key]=values[0].decode('ascii')
    return result

OVERRIDE_NAMES=frozenset({'GIT_CONFIG_PARAMETERS','GIT_CONFIG_COUNT','GIT_CONFIG','GIT_CONFIG_GLOBAL',
    'GIT_CONFIG_SYSTEM','GIT_DIR','GIT_WORK_TREE','GIT_INDEX_FILE','GIT_COMMON_DIR','GIT_OBJECT_DIRECTORY',
    'GIT_ALTERNATE_OBJECT_DIRECTORIES','GIT_SSH','GIT_SSH_COMMAND','GIT_ASKPASS','SSH_ASKPASS','GIT_EXEC_PATH',
    'GIT_GRAFT_FILE','GH_TOKEN','GITHUB_TOKEN','GH_HOST','GH_CONFIG_DIR','BASH_ENV','ENV','SHELLOPTS'})
OVERRIDE_PREFIXES=('GIT_CONFIG_KEY_','GIT_CONFIG_VALUE_','BASH_FUNC_','DYLD_','LD_','PYTHON','VSCODE_GIT_ASKPASS_')

def ensure_clean_parent(environment):
    if any(name in OVERRIDE_NAMES or name.startswith(OVERRIDE_PREFIXES) for name in environment):
        fail('environment_override_refused')

def canonical(path):
    try:
        raw=os.fspath(path)
        if not isinstance(raw,str) or len(raw)>4096 or '\0' in raw:fail('path_refused')
        value=Path(raw)
        if not value.is_absolute() or '..' in value.parts:fail('path_refused')
        company_home=Path(pwd.getpwuid(os.getuid()).pw_dir)/'.codex'
        parts=tuple(part.casefold() for part in value.parts)
        forbidden=tuple(part.casefold() for part in company_home.parts)
        if parts[:len(forbidden)]==forbidden or 'manabi-backoffice' in raw.casefold():
            fail('path_refused')
        if value.resolve()!=value:fail('path_refused')
        return value
    except (OSError,RuntimeError,TypeError,ValueError):
        fail('path_refused')

def private_parents(path,home,*,create=False):
    home=canonical(home);path=canonical(path)
    if home not in path.parents:fail('private_path_refused')
    current=home
    for part in path.relative_to(home).parts[:-1]:
        current/=part
        if create:
            try:current.mkdir(mode=0o700)
            except FileExistsError:pass
        try:info=current.lstat()
        except OSError:fail('private_path_refused')
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)&0o077:
            fail('private_path_refused')
    return path

def read_private(path,home):
    path=private_parents(path,home)
    try:
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as stream:
            info=os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600 or info.st_size>MAX_RECORD:
                fail('private_record_refused')
            raw=stream.read(MAX_RECORD+1)
            after=path.lstat()
            if len(raw)>MAX_RECORD or (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns):
                fail('private_record_changed')
            return raw
    except OSError:fail('private_record_refused')

def write_new(path,value,home):
    path=private_parents(path,home,create=True)
    try:raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')+b'\n'
    except (ValueError,TypeError,UnicodeError):fail('record_json_refused')
    if len(raw)>MAX_RECORD:fail('record_size_refused')
    temporary=None
    try:
        fd,name=tempfile.mkstemp(prefix='.new-',dir=path.parent);temporary=Path(name)
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.link(temporary,path,follow_symlinks=False)
        directory_fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(directory_fd)
        finally:os.close(directory_fd)
    except FileExistsError:fail('record_exists')
    except OSError:
        # Retract only our own inode after directory persistence failure.
        if temporary is not None:
            try:
                actual=path.lstat();own=temporary.lstat()
                if (actual.st_dev,actual.st_ino)==(own.st_dev,own.st_ino):path.unlink()
            except OSError:pass
        fail('record_publication_failed')
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)

def seal(value,field):
    if not isinstance(value,dict) or field in value:fail('record_schema_refused')
    return {**value,field:digest(value)}

def check_seal(value,field):
    if not isinstance(value,dict) or not isinstance(value.get(field),str) or not re.fullmatch('[0-9a-f]{64}',value[field]):
        fail('record_digest_refused')
    if value[field]!=digest({key:item for key,item in value.items() if key!=field}):fail('record_digest_refused')

class FileLease:
    def __init__(self,path,home):self.path=path;self.home=home;self.fd=None
    def __enter__(self):
        path=private_parents(self.path,self.home,create=True)
        try:
            self.fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
            info=os.fstat(self.fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600:
                fail('lease_refused')
            fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            return self
        except (OSError,RecoveryError):
            if self.fd is not None:os.close(self.fd);self.fd=None
            fail('operation_busy_or_unsafe')
    def __exit__(self,_kind,_value,_trace):
        if self.fd is not None:
            try:fcntl.flock(self.fd,fcntl.LOCK_UN)
            finally:os.close(self.fd);self.fd=None

def owned_bytes(path,limit=MAX_RECORD):
    path=canonical(path)
    try:
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as stream:
            info=os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o022 or info.st_size>limit:
                fail('owned_file_refused')
            raw=stream.read(limit+1);after=path.lstat()
            if len(raw)>limit or (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_mode,info.st_uid)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_mode,after.st_uid):
                fail('owned_file_changed')
            return raw
    except OSError:fail('owned_file_refused')

def git_inspect(root,args):
    try:
        result=subprocess.run(['/usr/bin/git','-c','core.fsmonitor=false',*args],cwd=canonical(root),env=basic_environment(),
                              capture_output=True,check=False,timeout=10)
    except (OSError,subprocess.SubprocessError):fail('git_metadata_refused')
    if result.returncode or len(result.stdout)>16*1024*1024:fail('git_metadata_refused')
    return result.stdout

def runtime_inventory(runtime,commit):
    runtime=canonical(runtime)
    if not isinstance(commit,str) or not re.fullmatch('[0-9a-f]{40}',commit):fail('runtime_identity_refused')
    actual={};count=0;total=0;modes={};oids={}
    def walk(path):
        nonlocal count,total
        count+=1
        if count>4096:fail('runtime_entry_limit')
        try:info=path.lstat()
        except OSError:fail('runtime_file_refused')
        if info.st_uid!=os.getuid() or info.st_mode&0o022 or stat.S_ISLNK(info.st_mode):fail('runtime_file_refused')
        if stat.S_ISDIR(info.st_mode):
            for child in sorted(path.iterdir()):walk(child)
        elif stat.S_ISREG(info.st_mode):
            raw=owned_bytes(path);total+=len(raw)
            if total>16*1024*1024:fail('runtime_byte_limit')
            name=path.relative_to(runtime).as_posix();actual[name]=raw
            modes[name]='100755' if info.st_mode&0o100 else '100644'
            oids[name]=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        else:fail('runtime_file_refused')
    walk(runtime/'bin');walk(runtime/'scripts')
    if 'bin/ai-dev' not in actual:fail('runtime_launcher_missing')
    try:
        identity=git_inspect(runtime,['rev-parse','--show-toplevel','--path-format=absolute','--git-common-dir','HEAD']).decode().strip().splitlines()
        if len(identity)!=3 or canonical(identity[0])!=runtime or identity[2]!=commit:fail('runtime_identity_refused')
        if os.path.lexists(Path(identity[1])/'info/grafts'):fail('grafts_refused')
        raw_tree=git_inspect(runtime,['ls-tree','-r','-z',commit,'--','bin','scripts'])
        raw_index=git_inspect(runtime,['ls-files','--stage','-v','-z','--','bin','scripts'])
        tree={};index={}
        for raw,pattern,target in [(raw_tree,r'(100644|100755) blob ([0-9a-f]{40})\t([\s\S]+)',tree),(raw_index,r'H (100644|100755) ([0-9a-f]{40}) 0\t([\s\S]+)',index)]:
            if not raw.endswith(b'\0'):fail('runtime_manifest_refused')
            for entry in raw[:-1].decode('utf-8').split('\0'):
                matched=re.fullmatch(pattern,entry)
                if not matched or matched[3] in target:fail('runtime_manifest_refused')
                target[matched[3]]=(matched[1],matched[2])
    except UnicodeError:fail('runtime_manifest_refused')
    expected={name:(modes[name],oids[name]) for name in actual}
    if tree!=expected or index!=expected:fail('runtime_content_refused')
    return actual

PINNED_RUNTIME_COMMIT='169642d0c8040e24e048ee5f04777345e5242016'
REQUIRED_LEGACY={'__init__.py','auto.py','cli.py','config.py','controller.py','execution.py','git_environment.py',
                 'gitops.py','handoff.py','spec.py','workflow.py','migration.py','design_review.py','bootstrap.py','review_admission.cjs'}

def runtime_location(runtime):
    runtime=canonical(runtime);home=canonical(Path(pwd.getpwuid(os.getuid()).pw_dir))
    if home not in runtime.parents:fail('runtime_location_refused')
    for value in (runtime,*runtime.parents):
        info=value.lstat();owner=os.getuid() if value==home or home in value.parents else 0
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=owner or info.st_mode&0o022:fail('runtime_location_refused')

def selected_hook(project):
    registration=project/'.ai-dev-helm.json';selected=None
    if registration.exists():selected=strict_json(owned_bytes(registration)).get('reviewBudgetScript')
    if selected is not None:
        if not isinstance(selected,str) or not selected or Path(selected).is_absolute() or '..' in Path(selected).parts:fail('hook_selection_refused')
        path=canonical(project/selected)
    else:
        path=next((project/area/'hooks/review-budget.cjs' for area in ['.claude','.codex'] if (project/area/'hooks/review-budget.cjs').is_file()),None)
        if path is None:fail('hook_selection_refused')
        path=canonical(path)
    if project not in path.parents:fail('hook_selection_refused')
    return path

def legacy_sources(runtime,project,inventory):
    names={Path(name).name for name in inventory if Path(name).parent.as_posix()=='scripts/v9'}
    if not REQUIRED_LEGACY <= names:fail('legacy_runtime_incomplete')
    selected={name:raw for name,raw in inventory.items() if (name.startswith('scripts/v9/') and Path(name).suffix in {'.py','.cjs'}) or name in {'scripts/harness.py','scripts/ai_dev_handoff.py','bin/ai-dev'}}
    if not {'scripts/harness.py','scripts/ai_dev_handoff.py','bin/ai-dev'} <= selected.keys():fail('legacy_runtime_incomplete')
    values=[('runtime/'+name,sha(raw)) for name,raw in selected.items()]
    hook=selected_hook(project);values.append(('project/'+hook.relative_to(project).as_posix(),sha(owned_bytes(hook))))
    fingerprint=sha(json.dumps(sorted(values),separators=(',',':')).encode())
    return fingerprint,selected

class SourceOnly(importlib.abc.MetaPathFinder,importlib.abc.Loader):
    def __init__(self,runtime,sources):
        self.modules={}
        for relative,raw in sources.items():
            if not relative.endswith('.py'):continue
            if relative in {'scripts/harness.py','scripts/ai_dev_handoff.py'}:name=Path(relative).stem
            elif relative.startswith('scripts/v9/'):
                name='.'.join(Path(relative).relative_to('scripts').with_suffix('').parts)
                if name.endswith('.__init__'):name=name[:-9]
            else:continue
            self.modules[name]=(runtime/relative,raw,Path(relative).name=='__init__.py')
    def find_spec(self,fullname,path=None,target=None):
        if fullname not in {'harness','ai_dev_handoff','v9'} and not fullname.startswith('v9.'):return None
        if fullname not in self.modules:fail('legacy_import_refused')
        filename,_raw,package=self.modules[fullname]
        return importlib.util.spec_from_loader(fullname,self,origin=str(filename),is_package=package)
    def create_module(self,spec):return None
    def exec_module(self,module):
        filename,raw,package=self.modules[module.__name__];module.__file__=str(filename)
        if package:module.__path__=[str(filename.parent)]
        exec(compile(raw,str(filename),'exec'),module.__dict__)

def exact_fields(value,fields):
    if not isinstance(value,dict) or set(value)!=set(fields):fail('record_schema_refused')

def _read_legacy_worker(request):
    exact_fields(request,{'job','project','runtime','home'})
    if any(name in {'harness','ai_dev_handoff','v9'} or name.startswith('v9.') for name in sys.modules):fail('legacy_namespace_not_fresh')
    home=canonical(request['home']);project=canonical(request['project']);runtime=canonical(request['runtime']);job_path=canonical(request['job'])
    if os.environ.get('HOME')!=str(home):fail('legacy_home_refused')
    runtime_location(runtime);inventory=runtime_inventory(runtime,PINNED_RUNTIME_COMMIT)
    job_raw=read_private(job_path,home);job=strict_json(job_raw)
    exact_fields(job,{'schema_version','operation','action','project','task','binding_digest','workflow_revision','proposal','proposal_digest','personal_environment'})
    if job['schema_version']!=10 or job['operation']!='git_action' or job['action']!='commit' or job['project']!=str(project) or not isinstance(job['task'],str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9._-]{0,127}',job['task']):fail('legacy_job_refused')
    task=job['task'];directory=home/'.ai-dev-harness/v9/git'/sha(str(project).encode())/sha(task.encode())
    check_seal(job,'proposal_digest')
    if job_path!=directory/('commit-'+job['proposal_digest']+'.json'):fail('legacy_job_path_refused')
    result_path=job_path.with_suffix('.result.json');result_raw=read_private(result_path,home);result=strict_json(result_raw)
    exact_fields(result,{'schema_version','action','proposal_digest','status','evidence','result_digest'});check_seal(result,'result_digest')
    if (type(result['schema_version']) is not int or result['schema_version']!=10) or result['action']!='commit' or result['status']!='succeeded' or result['proposal_digest']!=job['proposal_digest']:fail('legacy_result_refused')
    exact_fields(result['evidence'],{'commit','parent','tree','branch'})
    state_path=home/'.ai-dev-harness/v9/workflows'/sha(str(project).encode())/(sha(task.encode())+'.json')
    state_raw=read_private(state_path,home);state=strict_json(state_raw)
    if type(job['workflow_revision']) is not int or state.get('revision')!=job['workflow_revision'] or digest(state.get('binding'))!=job['binding_digest']:fail('legacy_binding_refused')
    fingerprint,sources=legacy_sources(runtime,project,inventory)
    if state['binding'].get('runtime_digest')!=fingerprint:fail('legacy_runtime_refused')
    sys.meta_path.insert(0,SourceOnly(runtime,sources))
    import v9.gitops as core
    from v9.controller import _inputs
    from v9.handoff import workflow_job_path,_validate_job
    from v9.workflow import WorkflowStore,latest_evidence
    from v9.git_environment import PersonalGitEnvironment
    job_loaded=core._load_job(job_path,home)
    if job_loaded!=job:fail('legacy_job_changed')
    state=WorkflowStore(state_path).load();core._require_workflow(state,action='commit')
    if any(state['approvals'][phase]['kind']!='human_approved' for phase in ['specification','plan','implementation','review']):fail('legacy_approval_refused')
    context_job=next((workflow_job_path(home,project,task,item['id']) for item in reversed(state['attempts']) if item['origin_schema']==10 and workflow_job_path(home,project,task,item['id']).is_file()),None)
    if context_job is None:fail('legacy_saved_context_missing')
    saved=_validate_job(strict_json(read_private(context_job,home)))
    meta=git_inspect(project,['rev-parse','--show-toplevel','--path-format=absolute','--git-common-dir','HEAD']).decode().strip().splitlines()
    if len(meta)!=3 or canonical(meta[0])!=project or os.path.lexists(Path(meta[1])/'info/grafts'):fail('legacy_project_refused')
    branch=git_inspect(project,['symbolic-ref','--quiet','--short','HEAD']).decode().strip()
    evidence=result['evidence'];proposal=job['proposal']
    if branch.casefold() in {'main','master'} or branch!=proposal['branch'] or branch!=evidence['branch'] or meta[2]!=evidence['commit']:fail('legacy_head_refused')
    raw_commit=parse_commit(git_inspect(project,['cat-file','commit',evidence['commit']]))
    if raw_commit!={'tree':evidence['tree'],'parent':evidence['parent']} or raw_commit['parent']!=proposal['parent']:fail('legacy_commit_refused')
    tree={}
    for item in git_inspect(project,['ls-tree','-r','-z',evidence['commit']]).split(b'\0'):
        if not item:continue
        match=re.fullmatch(rb'(100644|100755) blob ([0-9a-f]{40})\t([\s\S]+)',item)
        if not match or match[3] in tree:fail('legacy_index_refused')
        tree[match[3]]=(match[1],match[2])
    index={}
    for item in git_inspect(project,['ls-files','--stage','-v','-z']).split(b'\0'):
        if not item:continue
        match=re.fullmatch(rb'H (100644|100755) ([0-9a-f]{40}) 0\t([\s\S]+)',item)
        if not match or match[3] in index:fail('legacy_index_refused')
        index[match[3]]=(match[1],match[2])
    if tree!=index:fail('legacy_index_refused')
    fresh=_inputs(project,task=task,implementation_provider=saved['implementation_provider'],manifest_file=saved['manifest_file'],plan_file=saved['plan_file'],home=home,routes=None,harness_root=runtime)
    if fresh['binding']!=state['binding'] or not fresh['config']['execution_ready'] or proposal['snapshot']!=state['binding']['snapshot_hash']:fail('legacy_inputs_refused')
    implementation=latest_evidence(state,'implementation')
    if implementation['evidence']['kind']!='checks' or any(row['status']!='passed' or row['exit_code']!=0 for row in implementation['evidence']['results']):fail('legacy_checks_refused')
    personal=PersonalGitEnvironment.load(project,home).binding;original=job['personal_environment']
    exact_fields(personal,{'account','configs','gh_config_dir','git_config_file'});exact_fields(original,personal.keys())
    if personal['account']!=ACCOUNT or any(personal[key]!=original[key] for key in ['account','gh_config_dir','git_config_file']) or len(personal['configs'])!=len(original['configs']):fail('legacy_personal_identity_refused')
    common_config=canonical(Path(meta[1])/'config');changed=[]
    for old,new in zip(original['configs'],personal['configs']):
        exact_fields(old,{'path','sha256'});exact_fields(new,{'path','sha256'})
        if old['path']!=new['path']:fail('legacy_config_refused')
        if canonical(old['path'])==common_config:
            changed.append(validate_delta(old['sha256'],owned_bytes(common_config)))
            if new['sha256']!=changed[-1]['current_sha256']:fail('legacy_config_changed')
        elif old!=new:fail('legacy_config_refused')
    if len(changed)!=1:fail('legacy_config_refused')
    remotes=proposal['remotes'];github=[item for item in remotes if item.get('repository') is not None]
    if len(github)!=1 or github[0]['name']!='origin' or github[0]['repository']!=REPOSITORY:fail('legacy_remote_refused')
    normal=[]
    for file in sorted(directory.glob('push-*.json')):
        raw=read_private(file,home);value=strict_json(raw)
        if file.name.endswith('.result.json'):
            exact_fields(value,{'schema_version','action','proposal_digest','status','evidence','result_digest'});check_seal(value,'result_digest')
            if value['schema_version']!=10 or value['action']!='push' or value['status']!='succeeded':fail('legacy_push_unresolved')
        else:
            core._load_job(file,home)
            if not file.with_suffix('.result.json').is_file():fail('legacy_push_unresolved')
        normal.append((file.name,sha(raw)))
    if read_private(state_path,home)!=state_raw or read_private(job_path,home)!=job_raw or read_private(result_path,home)!=result_raw:fail('legacy_record_changed')
    again=runtime_inventory(runtime,PINNED_RUNTIME_COMMIT)
    if again!=inventory or legacy_sources(runtime,project,again)[0]!=fingerprint:fail('legacy_runtime_changed')
    return {'schema_version':1,'project':str(project),'task':task,'commit':evidence['commit'],'parent':evidence['parent'],'tree':evidence['tree'],'branch':branch,'origin_job':str(job_path),'origin_job_sha256':sha(job_raw),'origin_result_sha256':sha(result_raw),'state_sha256':sha(state_raw),'workflow_revision':state['revision'],'binding_digest':job['binding_digest'],'approvals_digest':digest(state['approvals']),'snapshot_hash':state['binding']['snapshot_hash'],'runtime':str(runtime),'runtime_digest':fingerprint,'policy_digest':state['binding']['policy_digest'],'personal_environment':personal,'original_personal_environment':original,'delta':changed[0],'remote':github[0],'normal_records_digest':digest(normal)}

def read_legacy_context(job,project,runtime,home):
    request={'job':str(job),'project':str(project),'runtime':str(runtime),'home':str(home)}
    try:
        result=run_bounded([PYTHON,'-I','-S','-B',str(Path(__file__).resolve()),'_read-context'],
                           input_bytes=json.dumps(request).encode(),env=basic_environment(home),cwd=canonical(project),timeout=120)
    except (OSError,subprocess.SubprocessError):fail('legacy_verifier_failed')
    if result.returncode or len(result.stdout)>MAX_RECORD:fail('legacy_context_refused')
    return strict_json(result.stdout)


def basic_environment(home=None):
    return {'PATH':FIXED_PATH,'HOME':str(home or Path.home()),'CODEX_HOME':str((home or Path.home())/'.codex-personal'),
            'TMPDIR':'/private/tmp','LANG':'en_US.UTF-8','LC_ALL':'en_US.UTF-8',
            'GIT_CONFIG_GLOBAL':os.devnull,'GIT_CONFIG_NOSYSTEM':'1','GIT_NO_REPLACE_OBJECTS':'1',
            'GIT_OPTIONAL_LOCKS':'0','GIT_TERMINAL_PROMPT':'0','GIT_NO_LAZY_FETCH':'1'}

def config_pairs(raw):
    env=basic_environment()
    try:
        with tempfile.TemporaryDirectory(prefix='fitlog-env-config-',dir='/private/tmp') as folder:
            env['GIT_CEILING_DIRECTORIES']=str(Path(folder).parent)
            result=subprocess.run(['/usr/bin/git','config','--no-includes','--file','-','--null','--list'],
                                  input=raw,cwd=folder,env=env,capture_output=True,timeout=10,check=False)
    except (OSError,subprocess.SubprocessError):
        fail('config_parse_refused')
    if result.returncode or len(result.stdout)>MAX_RECORD or (result.stdout and not result.stdout.endswith(b'\0')):
        fail('config_parse_refused')
    pairs=[]
    try:
        for item in result.stdout.split(b'\0')[:-1]:
            key,separator,value=item.partition(b'\n')
            pairs.append((key.decode('utf-8'),value.decode('utf-8') if separator else None))
    except UnicodeError:
        fail('config_parse_refused')
    if any(key.startswith(('include.','includeif.')) for key,_ in pairs):
        fail('config_include_refused')
    return pairs

def validate_delta(old_sha256,current):
    if not isinstance(old_sha256,str) or not re.fullmatch('[0-9a-f]{64}',old_sha256):
        fail('metadata_change_refused')
    if not isinstance(current,bytes) or len(current)>MAX_RECORD:
        fail('metadata_change_refused')
    try:current.decode('utf-8')
    except UnicodeError:fail('metadata_change_refused')
    lines=current.splitlines(keepends=True)
    if lines.count(MAIN_HEADER)!=1 or b'\r' in current or b'\0' in current or current.startswith(b'\xef\xbb\xbf'):
        fail('metadata_change_refused')
    begin=lines.index(MAIN_HEADER)+1
    end=next((i for i in range(begin,len(lines)) if lines[i].lstrip().startswith(b'[')),len(lines))
    places=[i for i in range(begin,end) if lines[i]==METADATA_LINE]
    if len(places)!=1:fail('metadata_change_refused')
    old=b''.join(lines[:places[0]]+lines[places[0]+1:])
    if sha(old)!=old_sha256 or old==current:fail('metadata_change_refused')
    old_pairs=config_pairs(old);new_pairs=config_pairs(current)
    key='branch.main.vscode-merge-base'
    if any(k==key for k,_ in old_pairs):fail('metadata_change_refused')
    added=[(k,v) for k,v in new_pairs if k==key]
    if added!=[(key,'origin/main')] or [(k,v) for k,v in new_pairs if k!=key]!=old_pairs:
        fail('metadata_change_refused')
    return {'kind':'main_vscode_metadata_added','old_sha256':old_sha256,'current_sha256':sha(current),
            'added_line_sha256':sha(METADATA_LINE)}

def check_ticket_time(ticket,now):
    created=ticket.get('created_at');expires=ticket.get('expires_at')
    if type(created) is not int or type(expires) is not int or expires-created!=900 or not created<=now<expires:
        fail('ticket_expired_or_invalid')

def confirm_ticket(ticket,*,input_fn=input,terminal_check=None,output=None):
    output=output or sys.stdout
    if terminal_check is None:terminal_check=lambda:sys.stdin.isatty() and sys.stdout.isatty()
    if not terminal_check():fail('real_terminal_required')
    prefix=ticket.get('ticket_digest')
    if not isinstance(prefix,str) or not re.fullmatch('[0-9a-f]{64}',prefix):fail('ticket_digest_refused')
    label='ENV-RECOVERY-PR' if ticket['action']=='pr' else 'ENV-RECOVERY'
    print(json.dumps(ticket,ensure_ascii=False,sort_keys=True,indent=2),file=output)
    try:line=input_fn('Type APPROVE '+label+' '+prefix[:16]+': ')
    except EOFError:fail('confirmation_refused')
    if line!='APPROVE '+label+' '+prefix[:16]:fail('confirmation_refused')

def check_namespace(namespace,home):
    if not namespace.exists():return
    # Every intent consumes its ticket, including failed/unknown results. An unresolved
    # operation also prevents preparing or executing a different ticket for this commit.
    for path in namespace.glob('*.intent.json'):
        intent=strict_json(read_private(path,home));check_seal(intent,'intent_digest')
        exact_fields(intent,{'schema_version','kind','ticket_digest','started_at','intent_digest'})
        if (type(intent['schema_version']) is not int or intent['schema_version']!=1) or intent['kind']!='environment_recovery_intent':fail('intent_schema_refused')
        td=intent['ticket_digest']
        if not isinstance(td,str) or not re.fullmatch('[0-9a-f]{64}',td) or path.name!='ticket-'+td+'.intent.json':fail('intent_path_refused')
        result_path=path.with_name('ticket-'+td+'.result.json')
        if not result_path.exists():fail('unresolved_operation')
        result=strict_json(read_private(result_path,home));check_seal(result,'result_digest')
        if result.get('ticket_digest')!=td or result.get('intent_digest')!=intent['intent_digest'] or result.get('status') not in {'succeeded','failed'}:
            fail('unresolved_operation')

def run_bounded(argv,*,env,cwd,timeout,input_bytes=None,started=None,before_start=None):
    """Own one child session; bound output on disk and kill its whole group on interruption."""
    import signal,time
    process=None;spawn_attempted=False
    def stop():
        if process is None:return
        try:os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        try:process.wait(timeout=.5)
        except subprocess.TimeoutExpired:pass
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        process.wait(timeout=3)
    try:
        with tempfile.TemporaryFile(dir='/private/tmp') as stdout,tempfile.TemporaryFile(dir='/private/tmp') as stderr,tempfile.TemporaryFile(dir='/private/tmp') as stdin:
            if input_bytes is not None:stdin.write(input_bytes);stdin.seek(0)
            location=canonical(cwd)
            if before_start is not None:before_start()
            spawn_attempted=True
            process=subprocess.Popen(argv,env=env,cwd=location,stdin=stdin,stdout=stdout,stderr=stderr,start_new_session=True)
            if started is not None:started(process.pid)
            deadline=time.monotonic()+timeout
            while process.poll() is None:
                if time.monotonic()>=deadline or os.fstat(stdout.fileno()).st_size>MAX_RECORD or os.fstat(stderr.fileno()).st_size>MAX_RECORD:
                    stop();fail('child_timeout_or_output_limit')
                time.sleep(min(.05,max(0,deadline-time.monotonic())))
            # A completed leader must not leave a worker in the same session running.
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            if os.fstat(stdout.fileno()).st_size>MAX_RECORD or os.fstat(stderr.fileno()).st_size>MAX_RECORD:fail('child_output_limit')
            stdout.seek(0);stderr.seek(0)
            return subprocess.CompletedProcess(argv,process.returncode,stdout.read(MAX_RECORD+1),stderr.read(MAX_RECORD+1))
    except OSError:
        stop()
        if not spawn_attempted:raise ChildNotStarted('V9_ENV_RECOVERY: preparation_failed') from None
        fail('child_start_or_io_uncertain')
    except BaseException:
        stop();raise

TICKET_FIELDS={'schema_version','kind','action','project','task','origin_job','context','source','remote_observed','mode','refspec','created_at','expires_at','delivery_result','pr','ticket_digest'}
RESULT_FIELDS={'schema_version','kind','ticket_digest','intent_digest','worker_digest','status','action','mode','remote_sha','pr','completed_at','result_digest'}

class RecoveryLane:
    """Private append-only transaction coordinator; dependencies are internal, never CLI inputs."""
    def __init__(self,home,source,context_reader,transport,clock):
        self.home=canonical(home);self.source=source;self.context_reader=context_reader;self.transport=transport;self.clock=clock
    def namespace(self,job):
        job=canonical(job)
        matched=re.fullmatch(r'commit-([0-9a-f]{64})\.json',job.name)
        if not matched:fail('commit_job_path_refused')
        return job.parent/'environment-recoveries'/matched[1]
    def fresh(self,job,project):
        # Freeze the returned object: a caller or transport cannot mutate a ticket's evidence.
        return strict_json(json.dumps(self.context_reader(job,project),ensure_ascii=False).encode())
    def read_ticket(self,path,project):
        path=canonical(path);ticket=strict_json(read_private(path,self.home));exact_fields(ticket,TICKET_FIELDS);check_seal(ticket,'ticket_digest')
        if (type(ticket['schema_version']) is not int or ticket['schema_version']!=1) or ticket['kind']!='environment_recovery_ticket' or ticket['action'] not in {'delivery','pr'}:fail('ticket_schema_refused')
        job=canonical(ticket['origin_job']);namespace=self.namespace(job)
        if path!=namespace/('ticket-'+ticket['ticket_digest']+'.json') or ticket['project']!=str(project) or ticket['source']!=self.source:fail('ticket_identity_refused')
        if ticket['context'].get('project')!=str(project) or ticket['context'].get('origin_job')!=str(job) or ticket['task']!=ticket['context'].get('task'):fail('ticket_context_refused')
        if ticket['refspec']!=ticket['context']['commit']+':refs/heads/'+ticket['context']['branch']:fail('ticket_refspec_refused')
        if ticket['action']=='delivery':
            if ticket['delivery_result'] is not None or ticket['pr'] is not None or ticket['mode'] not in {'sent','observed'}:fail('ticket_delivery_refused')
            expected=None if ticket['mode']=='sent' else ticket['context']['commit']
            if ticket['remote_observed']!=expected:fail('ticket_observation_refused')
        return ticket
    def validate_context(self,ticket,project):
        context=self.fresh(Path(ticket['origin_job']),project)
        if context!=ticket['context']:fail('context_changed')
        self.transport(context,'identity')
        return context
    def prepare(self,job,project):
        project=canonical(project);namespace=self.namespace(job)
        with FileLease(namespace/'operation.lock',self.home):
            check_namespace(namespace,self.home)
            context=self.fresh(job,project);self.transport(context,'identity');remote=self.transport(context,'observe')
            if remote not in {None,context['commit']}:fail('remote_sha_refused')
            now=int(self.clock())
            ticket=seal({'schema_version':1,'kind':'environment_recovery_ticket','action':'delivery','project':str(project),'task':context['task'],'origin_job':str(job),'context':context,'source':self.source,'remote_observed':remote,'mode':'sent' if remote is None else 'observed','refspec':context['commit']+':refs/heads/'+context['branch'],'created_at':now,'expires_at':now+900,'delivery_result':None,'pr':None},'ticket_digest')
            path=namespace/('ticket-'+ticket['ticket_digest']+'.json');write_new(path,ticket,self.home);return path
    def execute(self,path,project,*,input_fn=input,terminal_check=None,output=None):
        project=canonical(project);ticket=self.read_ticket(path,project);namespace=path.parent
        with FileLease(namespace/'operation.lock',self.home):
            check_namespace(namespace,self.home)
            intent_path=path.with_suffix('.intent.json');result_path=path.with_suffix('.result.json');worker_path=path.with_suffix('.worker.json')
            if os.path.lexists(intent_path) or os.path.lexists(result_path) or os.path.lexists(worker_path):fail('ticket_already_consumed')
            check_ticket_time(ticket,int(self.clock()));self.validate_context(ticket,project)
            if self.transport(ticket['context'],'observe')!=ticket['remote_observed']:fail('remote_changed')
            if ticket['action']=='pr':self.validate_pr(ticket,project)
            confirm_ticket(ticket,input_fn=input_fn,terminal_check=terminal_check,output=output)
            check_ticket_time(ticket,int(self.clock()));context=self.validate_context(ticket,project)
            if self.transport(context,'observe')!=ticket['remote_observed']:fail('remote_changed')
            if ticket['action']=='pr':self.validate_pr(ticket,project)
            intent_time=int(self.clock());check_ticket_time(ticket,intent_time)
            intent=seal({'schema_version':1,'kind':'environment_recovery_intent','ticket_digest':ticket['ticket_digest'],'started_at':intent_time},'intent_digest')
            write_new(intent_path,intent,self.home)
            worker_digest=None;pr=None;checking_result=False
            def before_start():
                try:check_ticket_time(ticket,int(self.clock()))
                except RecoveryError:raise ChildNotStarted('V9_ENV_RECOVERY: ticket_expired_before_start') from None
            def started(pid):
                nonlocal worker_digest
                worker=seal({'schema_version':1,'kind':'environment_recovery_worker','ticket_digest':ticket['ticket_digest'],'intent_digest':intent['intent_digest'],'pid':pid,'pgid':pid,'started_at':int(self.clock())},'worker_digest')
                write_new(worker_path,worker,self.home);worker_digest=worker['worker_digest']
            def result(status,remote):
                return seal({'schema_version':1,'kind':'environment_recovery_result','ticket_digest':ticket['ticket_digest'],'intent_digest':intent['intent_digest'],'worker_digest':worker_digest,'status':status,'action':ticket['action'],'mode':ticket['mode'],'remote_sha':remote,'pr':pr,'completed_at':int(self.clock())},'result_digest')
            try:
                before_start()
                if ticket['action']=='delivery' and ticket['mode']=='sent':self.transport(context,'deliver',ticket['refspec'],started,before_start)
                elif ticket['action']=='pr':
                    if ticket['mode']=='created':self.transport(context,'create-pr',ticket['pr'],started,before_start)
                    checking_result=True
                    pr=self.transport(context,'find-pr',ticket['pr'])
                    self.match_pr(pr,ticket['pr'],context)
                checking_result=True
                remote=self.transport(context,'observe')
                if remote!=context['commit']:fail('post_readback_refused')
                self.validate_context(ticket,project)
                write_new(result_path,result('succeeded',remote),self.home)
            except BaseException as error:
                if not os.path.lexists(result_path):
                    try:write_new(result_path,result('failed' if isinstance(error,ChildNotStarted) and not checking_result else 'unknown',None),self.home)
                    except (OSError,RecoveryError):pass  # Durable unresolved intent still blocks any retry.
                raise
            return result_path
    def read_delivery(self,result_path,project):
        result_path=canonical(result_path);result=strict_json(read_private(result_path,self.home));exact_fields(result,RESULT_FIELDS);check_seal(result,'result_digest')
        td=result['ticket_digest']
        if not isinstance(td,str) or not re.fullmatch('[0-9a-f]{64}',td) or result_path.name!='ticket-'+td+'.result.json':fail('result_path_refused')
        ticket_path=result_path.with_name('ticket-'+td+'.json');ticket=self.read_ticket(ticket_path,project)
        if (type(result['schema_version']) is not int or result['schema_version']!=1) or result['kind']!='environment_recovery_result' or result['status']!='succeeded' or result['action']!='delivery' or ticket['action']!='delivery' or result['mode']!=ticket['mode'] or result['remote_sha']!=ticket['context']['commit'] or result['pr'] is not None:fail('delivery_result_refused')
        if type(result['completed_at']) is not int or result['completed_at']<ticket['created_at'] or result['completed_at']>int(self.clock()):fail('result_time_refused')
        intent_path=ticket_path.with_suffix('.intent.json');intent=strict_json(read_private(intent_path,self.home));check_seal(intent,'intent_digest')
        exact_fields(intent,{'schema_version','kind','ticket_digest','started_at','intent_digest'})
        if (type(intent['schema_version']) is not int or intent['schema_version']!=1) or intent['kind']!='environment_recovery_intent' or intent['ticket_digest']!=td or result['intent_digest']!=intent['intent_digest'] or type(intent['started_at']) is not int or not ticket['created_at']<=intent['started_at']<ticket['expires_at'] or result['completed_at']<intent['started_at']:fail('intent_chain_refused')
        if ticket['mode']=='sent':
            worker=strict_json(read_private(ticket_path.with_suffix('.worker.json'),self.home));check_seal(worker,'worker_digest')
            exact_fields(worker,{'schema_version','kind','ticket_digest','intent_digest','pid','pgid','started_at','worker_digest'})
            if (type(worker['schema_version']) is not int or worker['schema_version']!=1) or worker['kind']!='environment_recovery_worker' or worker['ticket_digest']!=td or worker['intent_digest']!=intent['intent_digest'] or result['worker_digest']!=worker['worker_digest'] or type(worker['pid']) is not int or worker['pid']<=0 or worker['pgid']!=worker['pid'] or type(worker['started_at']) is not int or not intent['started_at']<=worker['started_at']<=result['completed_at']:fail('worker_chain_refused')
        elif result['worker_digest'] is not None or os.path.lexists(ticket_path.with_suffix('.worker.json')):fail('observation_worker_refused')
        check_namespace(result_path.parent,self.home)
        context=self.validate_context(ticket,project)
        if self.transport(context,'observe')!=context['commit']:fail('remote_changed')
        return ticket,result
    def status(self,result_path,project):
        ticket,result=self.read_delivery(result_path,canonical(project))
        return {'delivery_result_digest':result['result_digest'],'remote_sha':result['remote_sha'],'observed_at':int(self.clock()),'mode':result['mode']}

    def match_pr(self,observed,details,context):
        if not isinstance(observed,dict):fail('pr_observation_refused')
        exact_fields(observed,{'repository','head','head_sha','base','url'})
        if observed['repository']!=REPOSITORY or observed['head']!=context['branch'] or observed['head_sha']!=context['commit'] or observed['base']!='main' or not isinstance(observed['url'],str) or not re.fullmatch(r'https://github\.com/koma236/FitLog/pull/[1-9][0-9]*',observed['url']):fail('pr_identity_refused')
    def prepare_pr(self,delivery_result,project,base,title,body):
        project=canonical(project);delivery_result=canonical(delivery_result)
        ticket,delivery=self.read_delivery(delivery_result,project);namespace=delivery_result.parent
        with FileLease(namespace/'operation.lock',self.home):
            check_namespace(namespace,self.home)
            # Recheck inside the same per-commit lock held through publication.
            ticket,delivery=self.read_delivery(delivery_result,project)
            if base!='main' or not isinstance(title,str) or not title.strip() or len(title)>256 or any(ord(c)<32 for c in title):fail('pr_details_refused')
            body=canonical(body);raw=owned_bytes(body,65536)
            try:raw.decode('utf-8')
            except UnicodeError:fail('pr_body_refused')
            if b'\0' in raw:fail('pr_body_refused')
            details={'base':base,'title':title,'body_file':str(body),'body_sha256':sha(raw),'observed':None}
            observed=self.transport(ticket['context'],'find-pr',details)
            if observed is not None:self.match_pr(observed,details,ticket['context'])
            details['observed']=observed
            now=int(self.clock())
            proposal=seal({**{key:value for key,value in ticket.items() if key!='ticket_digest'},'action':'pr','delivery_result':{'path':str(delivery_result),'result_digest':delivery['result_digest']},'pr':details,'remote_observed':ticket['context']['commit'],'mode':'created' if observed is None else 'observed','created_at':now,'expires_at':now+900},'ticket_digest')
            path=namespace/('ticket-'+proposal['ticket_digest']+'.json');write_new(path,proposal,self.home);return path
    def validate_pr(self,ticket,project):
        details=ticket['pr'];exact_fields(details,{'base','title','body_file','body_sha256','observed'})
        if details['base']!='main' or ticket['mode'] not in {'created','observed'} or not isinstance(details['title'],str) or not details['title'].strip() or len(details['title'])>256 or any(ord(c)<32 for c in details['title']):fail('pr_details_refused')
        raw=owned_bytes(canonical(details['body_file']),65536)
        if sha(raw)!=details['body_sha256']:fail('pr_body_changed')
        delivery=ticket['delivery_result'];exact_fields(delivery,{'path','result_digest'})
        parent,result=self.read_delivery(canonical(delivery['path']),project)
        if result['result_digest']!=delivery['result_digest'] or parent['context']!=ticket['context']:fail('pr_delivery_changed')
        observed=self.transport(ticket['context'],'find-pr',details)
        if observed!=details['observed']:fail('pr_observation_changed')
        if ticket['mode']=='created':
            if observed is not None:fail('pr_mode_refused')
        else:self.match_pr(observed,details,ticket['context'])

class FixedTransport:
    def __init__(self,home):self.home=canonical(home)
    def __call__(self,context,operation,payload=None,started=None,before_start=None):
        project=canonical(context['project']);personal=context['personal_environment'];remote=context['remote'];commit=context['commit'];branch=context['branch']
        if not re.fullmatch('[0-9a-f]{40}',commit) or not re.fullmatch(r'(?!.*\.\.)(?!.*\.lock(?:/|$))(?!.*//)[A-Za-z0-9][A-Za-z0-9._/-]{0,254}',branch) or branch.casefold() in {'main','master'}:fail('transport_target_refused')
        if remote.get('name')!='origin' or remote.get('repository')!=REPOSITORY:fail('transport_remote_refused')
        url=remote.get('push_url')
        allowed={'https://github.com/koma236/FitLog.git','https://github.com/koma236/FitLog','git@github.com:koma236/FitLog.git','git@github.com:koma236/FitLog','ssh://git@github.com/koma236/FitLog.git'}
        if url not in allowed or remote.get('fetch_url') not in allowed:fail('transport_url_refused')
        env=basic_environment(self.home);env['GIT_CONFIG_GLOBAL']=str(canonical(personal['git_config_file']));env['GH_CONFIG_DIR']=str(canonical(personal['gh_config_dir']))
        def call(args,*,mutating=False,codes=(0,)):
            binary='/usr/bin/git' if args[0]=='git' else '/usr/local/bin/gh'
            argv=[binary,*(['-c','core.fsmonitor=false'] if args[0]=='git' else []),*args[1:]]
            result=run_bounded(argv,env=env,cwd=project,timeout=120 if mutating else 30,started=started if mutating else None,before_start=before_start if mutating else None)
            if result.returncode not in codes:fail('transport_command_failed')
            return result.stdout
        if operation=='identity':
            keys=call(['git','config','--null','--name-only','--get-regexp',r'^url\..*\.'],codes=(0,1))
            if any(key.lower().endswith((b'.insteadof',b'.pushinsteadof')) for key in keys.split(b'\0') if key):fail('url_rewrite_refused')
            fetch=call(['git','remote','get-url','--all','origin'])
            send=call(['git','remote','get-url','--push','--all','origin'])
            if fetch!=(remote['fetch_url']+'\n').encode() or send!=(url+'\n').encode():fail('remote_identity_changed')
            if call(['gh','api','--hostname','github.com','user','--jq','.login'])!=(ACCOUNT+'\n').encode():fail('account_identity_changed')
            return None
        if operation=='observe':
            ref='refs/heads/'+branch;raw=call(['git','ls-remote','--refs',url,ref])
            if raw==b'':return None
            matched=re.fullmatch(rb'([0-9a-f]{40})\t'+re.escape(ref.encode())+b'\n',raw)
            if not matched:fail('remote_observation_refused')
            return matched[1].decode()
        if operation=='deliver':
            if payload!=commit+':refs/heads/'+branch:fail('immutable_refspec_refused')
            call(['git','push',url,payload],mutating=True);return None
        if operation=='find-pr':
            raw=call(['gh','pr','list','--repo',REPOSITORY,'--head',branch,'--state','open','--json','url,headRefName,headRefOid,baseRefName,headRepository,headRepositoryOwner'])
            values=strict_json(b'{"items":'+raw+b'}')['items']
            if not isinstance(values,list) or len(values)>1:fail('pr_ambiguous')
            if not values:return None
            value=values[0]
            try:
                repository=value['headRepositoryOwner']['login']+'/'+value['headRepository']['name']
                result={'repository':repository,'head':value['headRefName'],'head_sha':value['headRefOid'],'base':value['baseRefName'],'url':value['url']}
            except (KeyError,TypeError):fail('pr_observation_refused')
            return result
        if operation=='create-pr':
            exact_fields(payload,{'base','title','body_file','body_sha256','observed'})
            if payload['base']!='main' or sha(owned_bytes(canonical(payload['body_file']),65536))!=payload['body_sha256']:fail('pr_body_changed')
            # Use a snapshot in owned scratch, so editing the original file after the
            # last hash check cannot change the bytes sent by gh.
            with tempfile.TemporaryDirectory(prefix='fitlog-pr-body-',dir='/private/tmp') as folder:
                body=Path(folder)/'body.txt';raw=owned_bytes(canonical(payload['body_file']),65536)
                if sha(raw)!=payload['body_sha256']:fail('pr_body_changed')
                fd=os.open(body,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
                call(['gh','pr','create','--repo',REPOSITORY,'--base','main','--head',branch,'--title',payload['title'],'--body-file',str(body)],mutating=True)
            return None
        fail('transport_operation_refused')


SOURCE_FILES=('.claude/hooks/quality-gate.cjs','.codex/hooks/quality-gate.cjs','.ai-dev/v9-git-entrypoints.json','.ai-dev/v9-env-recovery.json','bin/ai-dev-git-env-recovery','scripts/v9_git_environment_recovery.py')
PYTHON_SHA='80ee2dd97bc26259d4e30853336f72ad38aa4aa0531bb196cc444d899422689d'

def verify_python():
    path=canonical(PYTHON)
    for value in (path,*path.parents):
        info=value.lstat()
        mode=0o775 if value==path or value in list(path.parents)[:3] else 0o755
        expected=stat.S_ISREG(info.st_mode) if value==path else stat.S_ISDIR(info.st_mode)
        if not expected or info.st_uid!=0 or info.st_gid!=0 or stat.S_IMODE(info.st_mode)!=mode:fail('python_identity_refused')
    if path.stat().st_size>16*1024*1024 or sha(path.read_bytes())!=PYTHON_SHA:fail('python_identity_refused')
    framework=Path('/Library/Frameworks/Python.framework/Versions/3.12')
    for value,directory in [(framework/'Python',False),(framework/'lib/python3.12',True)]:
        canonical(value);info=value.lstat()
        if (not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)) or info.st_uid!=0 or info.st_gid!=0 or stat.S_IMODE(info.st_mode)!=0o775):fail('python_installation_refused')

def committed_source(source):
    source=canonical(source);meta=git_inspect(source,['rev-parse','--show-toplevel','--path-format=absolute','--git-common-dir','HEAD']).decode().strip().splitlines()
    if len(meta)!=3 or meta[0]!=str(source) or not re.fullmatch('[0-9a-f]{40}',meta[2]) or os.path.lexists(Path(meta[1])/'info/grafts'):fail('source_repository_refused')
    branch=git_inspect(source,['symbolic-ref','--quiet','--short','HEAD']).decode().strip()
    if branch.casefold() in {'main','master'}:fail('source_trunk_refused')
    tree={};index={}
    for command,pattern,target in [(['ls-tree','-r','-z',meta[2],'--',*SOURCE_FILES],rb'(100644|100755) blob ([0-9a-f]{40})\t([\s\S]+)',tree),(['ls-files','--stage','-v','-z','--',*SOURCE_FILES],rb'H (100644|100755) ([0-9a-f]{40}) 0\t([\s\S]+)',index)]:
        for item in git_inspect(source,command).split(b'\0'):
            if not item:continue
            match=re.fullmatch(pattern,item)
            if not match:fail('source_manifest_refused')
            name=match[3].decode()
            if name in target:fail('source_manifest_refused')
            target[name]=(match[1],match[2])
    if set(tree)!=set(SOURCE_FILES) or tree!=index:fail('source_index_refused')
    files={}
    for relative in SOURCE_FILES:
        path=source/relative;raw=owned_bytes(path);info=path.lstat();executable=relative.startswith('bin/')
        mode=b'100755' if executable else b'100644';oid=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest().encode()
        if tree[relative]!=(mode,oid) or bool(info.st_mode&0o100)!=executable:fail('source_content_refused')
        files[relative]=sha(raw)
    return {'project':str(source),'head':meta[2],'files':files}

def public_lane(project):
    import time
    home=canonical(Path(pwd.getpwuid(os.getuid()).pw_dir));source=canonical(Path(__file__).resolve().parents[1]);project=canonical(project)
    if str(home)!='/Users/saki' or os.environ.get('HOME')!=str(home) or os.environ.get('CODEX_HOME')!=str(home/'.codex-personal'):fail('personal_home_refused')
    # The launcher already inspected inherited names before replacing the environment.
    # Here there must be no arbitrary environment channel into the isolated worker.
    allowed={'PATH','HOME','CODEX_HOME','TMPDIR','LANG','LC_ALL','__CF_USER_TEXT_ENCODING'}
    if set(os.environ)-allowed or os.environ.get('PATH')!=FIXED_PATH or os.environ.get('TMPDIR')!='/private/tmp':fail('closed_environment_refused')
    verify_python();source_binding=committed_source(source)
    registry=strict_json(owned_bytes(source/'.ai-dev/v9-git-entrypoints.json'))
    exact_fields(registry,{'schema_version','repository','account','harness_root','harness_commit'})
    configuration=strict_json(owned_bytes(source/'.ai-dev/v9-env-recovery.json'))
    if type(configuration.get('schema_version')) is not int or configuration!={'schema_version':1,'repository':REPOSITORY,'account':ACCOUNT,'metadata_rule':'main_vscode_metadata_added'}:fail('recovery_configuration_refused')
    if (type(registry['schema_version']) is not int or registry['schema_version']!=1) or registry['repository']!=REPOSITORY or registry['account']!=ACCOUNT or registry['harness_commit']!=PINNED_RUNTIME_COMMIT:fail('runtime_registry_refused')
    runtime=canonical(registry['harness_root'])
    common=git_inspect(source,['rev-parse','--path-format=absolute','--git-common-dir']).strip()
    if project==source or git_inspect(project,['rev-parse','--path-format=absolute','--git-common-dir']).strip()!=common:fail('same_clone_required')
    def reader(job,target):
        verify_python()
        if target!=project or committed_source(source)!=source_binding:fail('source_changed')
        if sha(owned_bytes(source/'.ai-dev/v9-git-entrypoints.json'))!=source_binding['files']['.ai-dev/v9-git-entrypoints.json'] or sha(owned_bytes(source/'.ai-dev/v9-env-recovery.json'))!=source_binding['files']['.ai-dev/v9-env-recovery.json']:fail('configuration_changed')
        context=read_legacy_context(job,target,runtime,home)
        if context['delta']['old_sha256']!='6bd06089bbf149e6b9886a2ca23d81570d99d254c8515dade6877b75ef29860d' or context['delta']['current_sha256']!='42fa0496c05567620998cb9e9de6134408050f83f8a767b56ccc53dbd8800b3b':fail('approved_config_scope_changed')
        return context
    return RecoveryLane(home,source_binding,reader,FixedTransport(home),lambda:int(time.time()))

def public_main(argv):
    import argparse
    parser=argparse.ArgumentParser(prog='ai-dev-git-env-recovery',allow_abbrev=False)
    commands=parser.add_subparsers(dest='action',required=True)
    prepare=commands.add_parser('prepare',allow_abbrev=False);prepare.add_argument('--commit-job',required=True);prepare.add_argument('--project',required=True);prepare.add_argument('--remote',required=True,choices=['origin'])
    execute=commands.add_parser('execute',allow_abbrev=False);execute.add_argument('ticket');execute.add_argument('--project',required=True)
    status=commands.add_parser('status',allow_abbrev=False);status.add_argument('--delivery-result',required=True);status.add_argument('--project',required=True)
    pr=commands.add_parser('prepare-pr',allow_abbrev=False)
    for name in ['delivery-result','project','base','title','body-file']:pr.add_argument('--'+name,required=True)
    args=parser.parse_args(argv);project=canonical(args.project);lane=public_lane(project)
    if args.action=='prepare':result={'ticket':str(lane.prepare(canonical(args.commit_job),project))}
    elif args.action=='execute':result={'result':str(lane.execute(canonical(args.ticket),project))}
    elif args.action=='status':result=lane.status(canonical(args.delivery_result),project)
    else:result={'ticket':str(lane.prepare_pr(canonical(args.delivery_result),project,args.base,args.title,canonical(args.body_file)))}
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))


if __name__=='__main__':
    try:
        if sys.argv[1:]==['_read-context']:
            request=strict_json(sys.stdin.buffer.read(MAX_RECORD+1))
            print(json.dumps(_read_legacy_worker(request),ensure_ascii=False,sort_keys=True))
        else:public_main(sys.argv[1:])
    except RecoveryError as error:
        print(str(error),file=sys.stderr);raise SystemExit(2)
    except (OSError,ValueError,KeyError,TypeError,ImportError):
        print('V9_ENV_RECOVERY: context_refused',file=sys.stderr);raise SystemExit(2)
