'use strict';
// Oracle: approved docs/gate-followup-36-design.md §3, not the CLI's matcher.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const cp = require('node:child_process');
const script = path.join(__dirname, 'check-pr-stop.cjs');
const manifest = '.ai-dev-helm.json';
const declared = JSON.parse(fs.readFileSync(path.join(__dirname, '..', manifest), 'utf8'));
const env = {...process.env, GIT_CONFIG_GLOBAL:os.devNull, GIT_CONFIG_NOSYSTEM:'1', GIT_TERMINAL_PROMPT:'0'};
for (const k of ['GIT_DIR','GIT_WORK_TREE','GIT_INDEX_FILE','GIT_COMMON_DIR','GIT_OBJECT_DIRECTORY','GIT_ALTERNATE_OBJECT_DIRECTORIES']) delete env[k];
function fixture(config = declared) {
  const cwd = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'fitlog-stop-')));
  const git = (...args) => cp.execFileSync('git', ['-c','user.name=Fixture','-c','user.email=fixture@example.invalid',...args], {cwd,env,encoding:'utf8',stdio:['ignore','pipe','pipe']}).trim();
  const write = (file, data='fixture\n') => {
    fs.mkdirSync(path.dirname(path.join(cwd,file)), {recursive:true});
    fs.writeFileSync(path.join(cwd,file), data);
  };
  const commit = () => {git('add','.'); git('commit','-qm','fixture'); return git('rev-parse','HEAD');};
  git('init','-q','-b','main');
  write('app.txt');
  if (config !== null) write(manifest, JSON.stringify(config));
  const base = commit();
  git('checkout','-qb','feature/fixture');
  return {cwd,git,write,commit,base,close:()=>fs.rmSync(cwd,{recursive:true,force:true})};
}
function run(f, base=f.base, head=f.git('rev-parse','HEAD'), extra=[]) {
  const r = cp.spawnSync(process.execPath,[script,'--base',base,'--head',head,...extra], {cwd:f.cwd,env,encoding:'utf8',timeout:20000});
  assert.equal(r.error, undefined);
  assert.equal(r.stderr, '', r.stderr);
  return {code:r.status, data:JSON.parse(r.stdout)};
}
function expectPaths(f, paths) {
  const r = run(f);
  assert.equal(r.code, paths.length ? 2 : 0);
  assert.equal(r.data.stop, paths.length > 0);
  assert.deepEqual(r.data.paths.sort(), [...paths].sort());
}
for (const file of ['.github/workflows/ci.yml','.github/ci/check.sh','.ai-dev-helm.json',
  'AGENTS.md','backend/AGENTS.md','CLAUDE.md','backend/CLAUDE.md','.cursorrules',
  '.claude/hooks/a.cjs','.claude/hooks/quality-gate.cjs','.codex/hooks/quality-gate.cjs',
  '.codex/hooks.json','.cursor/rules/a.mdc','skills/project/a.md',
  '.github/review-docs.md','documents/development/coding-rules/a.md','scripts/check-pr-stop.cjs',
  'scripts/run-checks.py','.ai-dev/project.toml']) {
  test(`stop on ${file}`, () => {
    const f=fixture(); try {
      f.write(file, file===manifest ? JSON.stringify({...declared, projectName:'changed'}) : 'changed\n');
      f.commit(); expectPaths(f,[file]);
    } finally {f.close();}
  });
}
test('ordinary paths and near misses proceed', () => {
  const f=fixture(); try {
    for (const file of ['app.txt','docs/readme.md','.github/workflows-copy/a.yml','src/NOT_AGENTS.md','.github/review-docs.txt']) f.write(file,'changed\n');
    f.commit(); expectPaths(f,[]);
  } finally {f.close();}
});
test('glob semantics: zero-depth **/, single segment *, single character ?, trailing slash and case', () => {
  const f=fixture({gate:{controlPlane:['**/RULE.md','one/*/x?.md','directory/']}});
  try {
    const yes=['RULE.md','deep/rule.MD','one/a/x1.md','directory/日本語 space\nfile.md'];
    const no=['NOT_RULE.md','one/a/b/x1.md','one/a/x12.md','directory-copy/x.md'];
    for(const file of [...yes,...no]) f.write(file);
    f.commit(); expectPaths(f,yes);
  } finally {f.close();}
});
test('rename out of CI includes the original path; rename into CI includes destination', () => {
  const f=fixture(); try {
    f.write('.github/workflows/old.yml'); f.write('ordinary.txt');
    const base=f.commit();
    f.git('mv','.github/workflows/old.yml','moved.txt');
    f.git('mv','ordinary.txt','.github/workflows/new.yml');
    const head=f.commit();
    const r=run(f,base,head);
    assert.equal(r.code,2);
    assert.deepEqual(r.data.paths.sort(),['.github/workflows/new.yml','.github/workflows/old.yml']);
  } finally {f.close();}
});
test('deleted control-plane files stay visible', () => {
  const f=fixture(); try {
    f.write('.cursor/rules/old.mdc'); const base=f.commit();
    fs.unlinkSync(path.join(f.cwd,'.cursor/rules/old.mdc')); const head=f.commit();
    assert.deepEqual(run(f,base,head).data.paths,['.cursor/rules/old.mdc']);
  } finally {f.close();}
});
test('base declaration remains active when head removes it', () => {
  const f=fixture({gate:{controlPlane:['custom/**']}}); try {
    f.write(manifest,JSON.stringify({gate:{}})); f.write('custom/rule.txt'); f.commit();
    expectPaths(f,[manifest,'custom/rule.txt']);
  } finally {f.close();}
});
test('head declaration is active even when absent from base', () => {
  const f=fixture(null); try {
    f.write(manifest,JSON.stringify({gate:{controlPlane:['custom/**']}})); f.write('custom/rule.txt'); f.commit();
    expectPaths(f,[manifest,'custom/rule.txt']);
  } finally {f.close();}
});
test('missing manifests are compatible with older commits', () => {
  const f=fixture(null); try {f.write('app.txt','changed'); f.commit(); expectPaths(f,[]);} finally {f.close();}
});
for (const value of ['{', 'null', JSON.stringify({gate:{controlPlane:'**'}}), JSON.stringify({gate:{controlPlane:[1]}}), JSON.stringify({gate:[]})]) {
  test(`invalid manifest fails closed: ${value}`, () => {
    const f=fixture(); try {
      f.write(manifest,value); f.commit(); const r=run(f);
      assert.equal(r.code,1); assert.equal(typeof r.data.error,'string');
    } finally {f.close();}
  });
}
test('invalid base manifest also fails closed', () => {
  const f=fixture(); try {
    f.write(manifest,'{'); const base=f.commit();
    f.write(manifest,JSON.stringify(declared)); const head=f.commit();
    assert.equal(run(f,base,head).code,1);
  } finally {f.close();}
});
test('invalid/missing OIDs and options fail closed', () => {
  const f=fixture(); try {
    for (const base of ['main','--help','0'.repeat(40)]) assert.equal(run(f,base).code,1);
    assert.equal(run(f,f.base,f.base,['--extra']).code,1);
    const r=cp.spawnSync(process.execPath,[script],{cwd:f.cwd,env,encoding:'utf8'});
    assert.equal(r.status,1); assert.equal(typeof JSON.parse(r.stdout).error,'string');
  } finally {f.close();}
});
test('unrelated histories fail closed', () => {
  const f=fixture(); try {
    f.git('checkout','--orphan','unrelated'); f.git('rm','-rf','.');
    f.write('another.txt'); const head=f.commit();
    assert.equal(run(f,f.base,head).code,1);
  } finally {f.close();}
});
test('diff uses the merge base, not changes exclusive to a newer main', () => {
  const f=fixture(); try {
    f.write('feature.txt'); const head=f.commit();
    f.git('checkout','main'); f.write('.github/workflows/main-only.yml'); const base=f.commit();
    const r=run(f,base,head); assert.equal(r.code,0); assert.deepEqual(r.data.paths,[]);
  } finally {f.close();}
});
test('gitlink changes remain visible when local Git config ignores submodules', () => {
  const f=fixture(); try {
    f.git('update-index','--add','--cacheinfo',`160000,${f.base},skills/shared`);
    f.git('commit','-qm','base gitlink'); const base=f.git('rev-parse','HEAD');
    f.git('update-index','--cacheinfo',`160000,${base},skills/shared`);
    f.git('commit','-qm','updated gitlink'); const head=f.git('rev-parse','HEAD');
    f.git('config','diff.ignoreSubmodules','all');
    const r=run(f,base,head);
    assert.equal(r.code,2);
    assert.deepEqual(r.data.paths,['skills/shared']);
  } finally {f.close();}
});
