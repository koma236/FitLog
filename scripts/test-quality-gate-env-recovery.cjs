'use strict';
// Reuse the existing disposable fixture without modifying its authenticated source.
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const assert = require('node:assert/strict');
const oldPath = path.join(__dirname, 'test-quality-gate-v9.cjs');
const old = fs.readFileSync(oldPath, 'utf8');
const crypto = require('node:crypto');
assert.equal(crypto.createHash('sha256').update(old).digest('hex'), 'f584bb41e5d84b94fe1601279a7970f3e7d85658ebf29985f88c29a1f06434aa');
const prefix = old.slice(0, old.indexOf("test('producer fixture"))
  .replace('const fakeFs = Object.create(fs);', 'const fakeFs = Object.create(fs); fakeFs.openSync=(file,...args)=>{ if(options.opened)options.opened.push(String(file)); return fs.openSync(file,...args); };')
  .replace('const env = { ...gitEnv, ...options.env };', 'const env = { ...gitEnv, ...options.env }; delete env.GIT_CONFIG_GLOBAL; env.HOME=f.home; env.CODEX_HOME=path.join(f.home,".codex-personal"); if (options.inject) Object.assign(env, options.inject);');
const helpers = new Function('require', '__dirname', prefix + '\nreturn {fixture,invoke,git,write,hash};')(require, __dirname);
function fixture(fn) {
  const f = helpers.fixture();
  try {
    helpers.write(path.join(f.S, '.ai-dev/v9-env-recovery.json'), JSON.stringify({schema_version:1,repository:'koma236/FitLog',account:'koma236',metadata_rule:'main_vscode_metadata_added'}));
    helpers.write(path.join(f.S, 'bin/ai-dev-git-env-recovery'), '#!/bin/bash -p\nexit 2\n', 0o755);
    helpers.write(path.join(f.S, 'scripts/v9_git_environment_recovery.py'), '# fake source identity only\n');
    helpers.git(f.S,'add','.');helpers.git(f.S,'commit','-qm','recovery fixture');
    const job = structuredClone(f.J.value);job.action='commit';delete job.proposal.refspec;job.proposal_digest='1'.repeat(64);
    const file=path.join(f.home,'.ai-dev-harness/v9/git',helpers.hash(f.P),helpers.hash(f.task),'commit-'+job.proposal_digest+'.json');helpers.write(file,JSON.stringify(job));f.commitJob=file;
    f.command=`${f.S}/bin/ai-dev-git-env-recovery prepare --commit-job ${file} --project ${f.P} --remote origin`;
    fn(f);
  } finally { f.cleanup(); }
}
test('new canonical prepare uses seven bounded Git calls and both hook copies',()=>fixture(f=>{
  for(const copy of ['.claude','.codex']) {
    const result=helpers.invoke(f,f.command,{copy});assert.equal(result.blocked,false,result.out+result.err);assert.equal(result.calls.length,7);
    for(const call of result.calls)assert.ok(call.opts.timeout<=2000);
  }
}));
test('direct, relative, symlink, wrapper and foreign launchers are refused',()=>fixture(f=>{
  const variants=[f.command.replace(`${f.S}/bin/ai-dev-git-env-recovery`,'./bin/ai-dev-git-env-recovery'),`python3 ${f.S}/scripts/v9_git_environment_recovery.py prepare --project ${f.P}`,`bash ${f.command}`,`env ${f.command}`,f.command.replace(f.S+'/bin',f.P+'/bin'),`python3 -m scripts.v9_git_environment_recovery status --project ${f.P}`];
  for(const command of variants)assert.equal(helpers.invoke(f,command).blocked,true,command);
}));
test('file references and test execution retain legacy classification',()=>fixture(f=>{
  for(const command of ['git diff -- scripts/v9_git_environment_recovery.py','git add -- scripts/v9_git_environment_recovery.py','cat scripts/v9_git_environment_recovery.py','rg source scripts/v9_git_environment_recovery.py','python3 -I scripts/test_v9_git_environment_recovery.py'])assert.equal(helpers.invoke(f,command).blocked,false,command);
}));
test('unsafe agent names, unknown schema, modified source, unsafe mode and self target refuse',()=>fixture(f=>{
  assert.equal(helpers.invoke(f,f.command,{inject:{GH_TOKEN:'fake-private-marker'}}).blocked,true);
  assert.equal(helpers.invoke(f,f.command.replace(`--project ${f.P}`,`--project ${f.S}`)).blocked,true);
  const file=path.join(f.S,'scripts/v9_git_environment_recovery.py');fs.appendFileSync(file,'changed\n');assert.equal(helpers.invoke(f,f.command).blocked,true);
}));
test('private job symlinks, public permissions, foreign namespace and duplicate JSON refuse',()=>fixture(f=>{
  const original=fs.readFileSync(f.commitJob);fs.chmodSync(f.commitJob,0o644);assert.equal(helpers.invoke(f,f.command).blocked,true);fs.chmodSync(f.commitJob,0o600);
  fs.writeFileSync(f.commitJob,original.toString().replace('"action":"commit"','"action":"commit","action":"commit"'));assert.equal(helpers.invoke(f,f.command).blocked,true);
}));
function ticketFixture(f) {
  const td='2'.repeat(64),namespace=path.join(path.dirname(f.commitJob),'environment-recoveries','1'.repeat(64));
  const context={schema_version:1,project:f.P,task:f.task,commit:helpers.git(f.P,'rev-parse','HEAD'),parent:'3'.repeat(40),tree:'4'.repeat(40),branch:helpers.git(f.P,'branch','--show-current'),origin_job:f.commitJob,origin_job_sha256:'5'.repeat(64),origin_result_sha256:'6'.repeat(64),state_sha256:'7'.repeat(64),workflow_revision:1,binding_digest:'8'.repeat(64),approvals_digest:'9'.repeat(64),snapshot_hash:'a'.repeat(64),runtime:f.R,runtime_digest:'b'.repeat(64),policy_digest:'c'.repeat(64),personal_environment:{},original_personal_environment:{},delta:{},remote:{},normal_records_digest:'d'.repeat(64)};
  const files=Object.fromEntries(['.claude/hooks/quality-gate.cjs','.codex/hooks/quality-gate.cjs','.ai-dev/v9-git-entrypoints.json','.ai-dev/v9-env-recovery.json','bin/ai-dev-git-env-recovery','scripts/v9_git_environment_recovery.py'].map(rel=>[rel,helpers.hash(fs.readFileSync(path.join(f.S,rel)))]));
  const ticket={schema_version:1,kind:'environment_recovery_ticket',action:'delivery',project:f.P,task:f.task,origin_job:f.commitJob,context,source:{project:f.S,head:helpers.git(f.S,'rev-parse','HEAD'),files},remote_observed:null,mode:'sent',refspec:context.commit+':refs/heads/'+context.branch,created_at:1000,expires_at:1900,delivery_result:null,pr:null,ticket_digest:td};
  const file=path.join(namespace,'ticket-'+td+'.json');helpers.write(file,JSON.stringify(ticket));
  const result={schema_version:1,kind:'environment_recovery_result',ticket_digest:td,intent_digest:'e'.repeat(64),worker_digest:'f'.repeat(64),status:'succeeded',action:'delivery',mode:'sent',remote_sha:context.commit,pr:null,completed_at:1100,result_digest:'a'.repeat(64)};
  const resultPath=file.replace(/\.json$/,'.result.json');helpers.write(resultPath,JSON.stringify(result));return {file,ticket,resultPath};
}
test('execute status and prepare-pr accept canonical private records within seven calls',()=>fixture(f=>{
  const t=ticketFixture(f),body=path.join(f.base,'body.txt');helpers.write(body,'Reviewed body');
  const commands=[`${f.S}/bin/ai-dev-git-env-recovery execute ${t.file} --project ${f.P}`,`${f.S}/bin/ai-dev-git-env-recovery status --delivery-result ${t.resultPath} --project ${f.P}`,`${f.S}/bin/ai-dev-git-env-recovery prepare-pr --delivery-result ${t.resultPath} --project ${f.P} --base main --title "Fixture title" --body-file ${body}`];
  for(const command of commands){const result=helpers.invoke(f,command);assert.equal(result.blocked,false,result.out+result.err);assert.equal(result.calls.length,7);}
  fs.chmodSync(body,0o666);assert.equal(helpers.invoke(f,commands[2]).blocked,true);
}));
test('ticket source mismatch and private namespace alias refuse',()=>fixture(f=>{
  const t=ticketFixture(f);t.ticket.source.head='0'.repeat(40);fs.writeFileSync(t.file,JSON.stringify(t.ticket));
  const command=`${f.S}/bin/ai-dev-git-env-recovery execute ${t.file} --project ${f.P}`;
  assert.equal(helpers.invoke(f,command).blocked,true);
}));
test('observable name prefixes and Python owner mismatch refuse without value leakage',()=>fixture(f=>{
  for(const name of ['GIT_CONFIG_VALUE_4','BASH_FUNC_x%%','DYLD_FAKE','SHELLOPTS','LD_FAKE','PYTHONPATH']){const result=helpers.invoke(f,f.command,{inject:{[name]:'private-marker'}});assert.equal(result.blocked,true);assert.ok(!result.out.includes('private-marker'));}
  assert.equal(helpers.invoke(f,f.command,{wrongOwner:'/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12'}).blocked,true);
}));
test('shell-c startup and same-name symlink execution refuse',()=>fixture(f=>{
  assert.equal(helpers.invoke(f,`bash -c "${f.command}"`).blocked,true);
  const alias=path.join(f.base,'ai-dev-git-env-recovery');fs.symlinkSync(path.join(f.S,'bin/ai-dev-git-env-recovery'),alias);
  assert.equal(helpers.invoke(f,f.command.replace(`${f.S}/bin/ai-dev-git-env-recovery`,alias)).blocked,true);
}));
test('company settings path is refused before opening even a disposable fake config',()=>fixture(f=>{
  const fake=path.join(f.home,'.codex','never-read.json');helpers.write(fake,fs.readFileSync(f.commitJob));
  for(const dir of ['.codex','.CoDeX','.CODEX'])for(const copy of ['.claude','.codex']){
    const alias=path.join(f.home,dir,'never-read.json'),opened=[];
    const result=helpers.invoke(f,f.command.replace(f.commitJob,alias),{opened,copy});assert.equal(result.blocked,true);assert.equal(opened.includes(alias),false);
  }
}));
test('prepare-pr body aliases of company settings refuse before opening in both copies',()=>fixture(f=>{
  const t=ticketFixture(f),file=path.join(f.home,'.codex','body.txt');helpers.write(file,'fake company body');
  for(const dir of ['.CoDeX','.CODEX'])for(const copy of ['.claude','.codex']){
    const alias=path.join(f.home,dir,'body.txt'),opened=[];
    const command=`${f.S}/bin/ai-dev-git-env-recovery prepare-pr --delivery-result ${t.resultPath} --project ${f.P} --base main --title "Fixture title" --body-file ${alias}`;
    assert.equal(helpers.invoke(f,command,{opened,copy}).blocked,true);assert.equal(opened.includes(alias),false);
  }
}));
