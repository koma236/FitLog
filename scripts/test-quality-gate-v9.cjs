// Independent oracles: docs/personal-workflow-change-design.md WF-AC5 and the
// pinned public producer fixture. No real personal state or Git delivery.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const cp = require('node:child_process');
const { EventEmitter } = require('node:events');
const sourcePath = process.env.FITLOG_GATE_TEST_SOURCE || path.join(__dirname, '../.claude/hooks/quality-gate.cjs');
const source = fs.readFileSync(sourcePath);
const originalBytes = fs.readFileSync(path.join(__dirname, 'fixtures/v9-push-proposal.json'));
const provenance = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/v9-push-provenance.json')));
const original = JSON.parse(originalBytes);
const hash = (x) => crypto.createHash('sha256').update(x).digest('hex');
const canonical = (obj) => JSON.stringify(obj, (_key, value) => value && !Array.isArray(value) && typeof value === 'object' ? Object.fromEntries(Object.keys(value).sort().map(k => [k, value[k]])) : value);
function proposalDigest(value) { const base = { ...value }; delete base.proposal_digest; return hash(canonical(base)); }
const gitEnv = { ...process.env, GIT_CONFIG_GLOBAL: os.devNull, GIT_CONFIG_NOSYSTEM: '1', GIT_TERMINAL_PROMPT: '0' };
for (const key of ['GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR', 'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES']) delete gitEnv[key];
function git(cwd, ...args) {
  return cp.execFileSync('git', ['-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', ...args], { cwd, env: gitEnv, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
}
function write(file, data, mode = 0o600) {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  fs.writeFileSync(file, data, { mode });
}
function fixture() {
  const base = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'fl-v9-gate-')));
  const home = path.join(base, 'home');
  fs.mkdirSync(home, { mode: 0o700 });
  const R = path.join(home, 'runtime');
  fs.mkdirSync(R);
  git(R, 'init', '-q', '-b', 'fixture-runtime');
  write(path.join(R, 'bin/ai-dev'), '#!/bin/sh\nexit 0\n', 0o700);
  write(path.join(R, 'scripts/v9/cli.py'), '# disposable code identity\n');
  write(path.join(R, '.gitignore'), '__pycache__/\n');
  git(R, 'add', '.'); git(R, 'commit', '-qm', 'runtime fixture');
  const main = path.join(base, 'repo'); fs.mkdirSync(main);
  git(main, 'init', '-q', '-b', 'main');
  write(path.join(main, 'product.js'), 'initial\n');
  git(main, 'add', '.'); git(main, 'commit', '-qm', 'base');
  const S = path.join(base, 'session');
  git(main, 'worktree', 'add', '-q', '-b', 'feature/test', S);
  const config = { schema_version: 1, repository: 'koma236/FitLog', account: 'koma236', harness_root: R, harness_commit: git(R, 'rev-parse', 'HEAD') };
  for (const dir of ['.claude', '.codex']) write(path.join(S, dir, 'hooks/quality-gate.cjs'), source);
  write(path.join(S, '.ai-dev/v9-git-entrypoints.json'), JSON.stringify(config));
  write(path.join(S, 'product.js'), 'feature\n');
  git(S, 'add', '.'); git(S, 'commit', '-qm', 'session fixture');
  const P = path.join(base, 'target');
  git(main, 'worktree', 'add', '-q', '-b', 'feature/main-nav', P, 'feature/test');
  const task = 'FIXTURE-1';
  function job(project = P) {
    const value = structuredClone(original);
    value.project = fs.realpathSync(project); value.task = task;
    Object.assign(value.proposal, { account: 'koma236', repository: 'koma236/FitLog', fetch_url: 'https://github.com/koma236/FitLog.git', push_url: 'https://github.com/koma236/FitLog.git', branch: git(project, 'branch', '--show-current'), commit: git(project, 'rev-parse', 'HEAD') });
    value.proposal.refspec = `HEAD:refs/heads/${value.proposal.branch}`;
    value.personal_environment.account = 'koma236';
    value.personal_environment.gh_config_dir = path.join(home, 'gh-fixture');
    value.personal_environment.git_config_file = path.join(home, 'git-fixture');
    value.personal_environment.configs.forEach((c, i) => { c.path = path.join(home, `config-${i}`); });
    value.proposal_digest = proposalDigest(value);
    const file = path.join(home, '.ai-dev-harness/v9/git', hash(value.project), hash(task), `push-${value.proposal_digest}.json`);
    write(file, JSON.stringify(value));
    return { file, value };
  }
  const J = job();
  return { base, home, R, S, P, main, config, task, J, job,
    A: (project = P, branch = git(project, 'branch', '--show-current')) => `AI_DEV_HARNESS_HOME=${R} ${R}/bin/ai-dev v9 prepare-git --action push --project ${project} --task ${task} --remote origin --branch ${branch}`,
    B: (file = J.file, project = P) => `AI_DEV_HARNESS_HOME=${R} ${R}/bin/ai-dev v9 git-action ${file} --project ${project}`,
    cleanup: () => fs.rmSync(base, { recursive: true, force: true }),
  };
}
// Only this test vm substitutes OS identity/ancestor facts. Actual file/job,
// Git metadata and classifier behavior remain real; production has no switch.
function invoke(f, command, options = {}) {
  const stdin = new EventEmitter();
  let out = '', err = '';
  const calls = [];
  const ancestors = new Set();
  for (let p = path.dirname(f.home); ; p = path.dirname(p)) { ancestors.add(p); if (p === path.dirname(p)) break; }
  const fakeFs = Object.create(fs);
  fakeFs.lstatSync = (file, ...args) => {
    const info = fs.lstatSync(file, ...args);
    if (options.wrongOwner === String(file)) return new Proxy(info, { get(target, name) { if (name === 'uid') return process.getuid() + 1; const value = target[name]; return typeof value === 'function' ? value.bind(target) : value; } });
    if (!ancestors.has(String(file))) return info;
    return new Proxy(info, { get(target, name) { if (name === 'uid') return 0; if (name === 'mode') return (target.mode & ~0o777) | 0o755; const value = target[name]; return typeof value === 'function' ? value.bind(target) : value; } });
  };
  const fakeOs = Object.create(os);
  fakeOs.homedir = () => options.wrongHome ? f.base : f.home;
  fakeOs.userInfo = () => ({ ...os.userInfo(), homedir: f.home });
  const fakeCp = Object.create(cp);
  fakeCp.execFileSync = (program, args, opts) => {
    calls.push({ program, args, opts });
    if (options.gitError) throw new Error('fixture Git failure');
    const result = cp.execFileSync(program, args, opts);
    if (options.blobFault && args.includes('cat-file')) {
      if (options.blobFault === 'header') return Buffer.from('not a blob\n');
      if (options.blobFault === 'size') return Buffer.from('0'.repeat(40)+' blob 1048577\n');
      if (options.blobFault === 'truncated') return result.subarray(0, result.length-1);
      return Buffer.concat([result, Buffer.from('unexpected')]);
    }
    return result;
  };
  const module = { exports: {} };
  const load = (name) => ({ fs: fakeFs, 'node:fs': fakeFs, os: fakeOs, 'node:os': fakeOs, child_process: fakeCp, 'node:child_process': fakeCp })[name] || require(name);
  load.main = module;
  const env = { ...gitEnv, ...options.env };
  delete env.CLAUDE_PROJECT_DIR;
  if (options.claudeRoot) env.CLAUDE_PROJECT_DIR = options.claudeRoot;
  const fakeProcess = { ...process, env, stdin, cwd: () => f.S, getuid: () => process.getuid(), stdout: { write: (s) => { out += s; } }, stderr: { write: (s) => { err += s; } } };
  const filename = path.join(f.S, options.copy || '.codex', 'hooks/quality-gate.cjs');
  const fakeConsole = { log: (...args) => { out += args.join(' ') + '\n'; }, error: (...args) => { err += args.join(' ') + '\n'; } };
  vm.runInNewContext(fs.readFileSync(filename, 'utf8'), { require: load, module, exports: module.exports, __filename: filename, __dirname: path.dirname(filename), process: fakeProcess, Buffer, console: fakeConsole, setTimeout, clearTimeout }, { filename });
  const payload = { tool_name: options.tool || 'Bash', cwd: options.cwd || f.S, tool_input: { command } };
  stdin.emit('data', Buffer.from(JSON.stringify(payload))); stdin.emit('end');
  return { blocked: out.includes('"permissionDecision":"deny"'), out, err, calls };
}
function withFixture(fn) { const f = fixture(); try { fn(f); } finally { f.cleanup(); } }
test('producer fixture is authentic and independent canonical digest agrees', () => {
  assert.equal(hash(originalBytes), 'd0ba9c5c3f8f3c572b0ba5d643ca6a281416581003ffe01463c87a0edff53344');
  assert.equal(provenance.fixture_sha256, hash(originalBytes));
  assert.equal(proposalDigest(original), original.proposal_digest);
});
test('exact A/B and same-worktree A reach v9 without changing Git metadata', () => withFixture(f => {
  const files = [path.join(f.main, '.git/index'), path.join(f.S, '.git'), path.join(f.R, '.git/index'), f.J.file];
  const before = files.map(p => [hash(fs.readFileSync(p)), fs.statSync(p).mtimeMs]);
  const selfJob = f.job(f.S);
  for (const command of [f.A(), f.B(), f.A(f.S), f.B(selfJob.file, f.S)]) {
    const result = invoke(f, command);
    assert.equal(result.blocked, false, result.out + result.err);
    assert.ok(result.calls.length <= 8);
    for (const c of result.calls) { assert.equal(c.opts.env.GIT_OPTIONAL_LOCKS, '0'); assert.equal(c.opts.env.GIT_NO_REPLACE_OBJECTS,'1'); assert.ok(c.opts.timeout <= 2000); assert.equal(c.opts.env.GIT_NO_LAZY_FETCH, '1'); }
  }
  assert.deepEqual(files.map(p => [hash(fs.readFileSync(p)), fs.statSync(p).mtimeMs]), before);
}));
test('unsafe grammar, missing gate words and unsupported shell fail closed', () => withFixture(f => {
  const variants = [f.A().replace(`AI_DEV_HARNESS_HOME=${f.R} `, ''), f.A().replace(`${f.R}/bin/ai-dev`, 'ai-dev'), f.A().replace('push', 'unknown'), f.A() + ' --force', f.A() + ' && git status', f.A().replace('--action push', '--action push --action issue'), f.B(path.join(f.home, 'unknown.json')), 'ai-dev v9 prepare-git --help', 'rg "ai-dev v9 prepare-git" docs/'];
  for (const command of variants) assert.equal(invoke(f, command).blocked, true, command);
  for (const tool of ['PowerShell', 'unknown']) assert.equal(invoke(f, f.A(), { tool }).blocked, true);
}));
test('legacy feature/trunk/force/rewrite/nested/env behavior remains', () => withFixture(f => {
  const cases = [['git status --short', false], ['git push origin feature/test', false], ['git push origin main', true], ['git push --force origin main', true], ['git branch -f main HEAD', true], ['bash -c "git push origin main"', true], ['X=1 git push origin feature/test', true]];
  for (const [command, want] of cases) assert.equal(invoke(f, command).blocked, want, command);
  for (const action of ['issue', 'commit', 'pr']) assert.equal(invoke(f, `${f.R}/bin/ai-dev v9 prepare-git --action ${action} --project ${f.P} --task FIXTURE-1`).blocked, false);
}));
test('proposal identity, permissions, closed schema and symlinks refuse', () => withFixture(f => {
  for (const mutate of [j => { j.schema_version = 99; }, j => { j.extra = true; }, j => { j.proposal.commit = '0'.repeat(40); }, j => { j.proposal.branch = 'main'; }, j => { j.proposal.refspec = 'HEAD:refs/heads/main'; }, j => { j.proposal.repository = 'foreign/repo'; }, j => { j.project = f.S; }, j => { j.action = 'issue'; }]) {
    const value = structuredClone(f.J.value); mutate(value); fs.writeFileSync(f.J.file, JSON.stringify(value));
    assert.equal(invoke(f, f.B()).blocked, true);
  }
  fs.writeFileSync(f.J.file, JSON.stringify(f.J.value)); fs.chmodSync(f.J.file, 0o644);
  assert.equal(invoke(f, f.B()).blocked, true); fs.chmodSync(f.J.file, 0o600);
  const alias = path.join(f.home, 'alias.json'); fs.symlinkSync(f.J.file, alias);
  assert.equal(invoke(f, f.B(alias)).blocked, true);
  fs.writeFileSync(f.J.file, '{"schema_version":10,"schema_version":10}');
  assert.equal(invoke(f, f.B()).blocked, true);
}));
test('runtime purity, ownership mode and HOME mismatch refuse', () => withFixture(f => {
  const cache = path.join(f.R, 'scripts/v9/__pycache__/unexpected.pyc'); write(cache, 'cache');
  assert.equal(invoke(f, f.A()).blocked, true); fs.rmSync(path.dirname(cache), { recursive: true });
  fs.chmodSync(path.join(f.R, 'scripts/v9/cli.py'), 0o666);
  assert.equal(invoke(f, f.A()).blocked, true); fs.chmodSync(path.join(f.R, 'scripts/v9/cli.py'), 0o600);
  assert.equal(invoke(f, f.A(), { wrongHome: true }).blocked, true);
  assert.equal(invoke(f, f.A(), { gitError: true }).blocked, true);
}));
test('loaded S remains anchor: child cwd allowed, target/foreign/nested cwd refused', () => withFixture(f => {
  const child = path.join(f.S, 'child'); fs.mkdirSync(child);
  assert.equal(invoke(f, f.A(), { cwd: child }).blocked, false);
  for (const cwd of [f.P, f.base]) assert.equal(invoke(f, f.A(), { cwd }).blocked, true);
  git(child, 'init', '-q'); assert.equal(invoke(f, f.A(), { cwd: child }).blocked, true);
}));
test('uncommitted config/hook byte edits refuse, including BOM and invalid UTF8', () => withFixture(f => {
  const config = path.join(f.S, '.ai-dev/v9-git-entrypoints.json');
  fs.appendFileSync(config, '\n'); assert.equal(invoke(f, f.A()).blocked, true); fs.writeFileSync(config, JSON.stringify(f.config));
  const hook = path.join(f.S, '.claude/hooks/quality-gate.cjs');
  for (const bytes of [Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), source]), Buffer.concat([source, Buffer.from([0xff])]), Buffer.from(source.toString().replaceAll('\n', '\r\n'))]) {
    fs.writeFileSync(hook, bytes); assert.equal(invoke(f, f.A()).blocked, true);
  }
}));
test('native diagnostic is opt-in, private, exclusive, and leaves decision unchanged', () => withFixture(f => {
  const command = 'git status --short --untracked-files=no -- .fitlog-native-hook-probe';
  const dir = git(f.S, 'rev-parse', '--absolute-git-dir');
  const request = path.join(dir, 'v9-gate-probe.request.json'), result = path.join(dir, 'v9-gate-probe.result.json');
  assert.equal(invoke(f, command).blocked, false); assert.equal(fs.existsSync(result), false);
  const nonce = 'a'.repeat(32); write(request, JSON.stringify({ schema_version: 1, nonce }));
  assert.equal(invoke(f, 'git status --short').calls.length, 0);
  invoke(f, command); assert.equal(fs.existsSync(result), true);
  const bytes = fs.readFileSync(result), value = JSON.parse(bytes);
  assert.equal(value.nonce, nonce); assert.equal(value.tool_name, 'Bash'); assert.equal(value.script_sha256, hash(source));
  assert.equal(fs.statSync(result).mode & 0o777, 0o600);
  invoke(f, command); assert.deepEqual(fs.readFileSync(result), bytes);
  fs.unlinkSync(result); fs.unlinkSync(request);
  fs.symlinkSync(f.J.file, request); invoke(f, command); assert.equal(fs.existsSync(result), false);
}));
test('JSON parse errors never disclose private input and digest fields require strings', () => withFixture(f => {
  const secret = 'PRIVATE_FIXTURE_SENTINEL_791';
  fs.writeFileSync(f.J.file, `{"${secret}`);
  const bad = invoke(f, f.B());
  assert.equal(bad.blocked, true); assert.equal((bad.out + bad.err).includes(secret), false);
  for (const key of ['proposal_digest', 'binding_digest']) {
    const value = structuredClone(f.J.value); value[key] = [value[key]];
    fs.writeFileSync(f.J.file, JSON.stringify(value));
    assert.equal(invoke(f, f.B()).blocked, true, key);
  }
}));
test('missing registration retains legacy behavior; malformed present registration never grants an exception', () => withFixture(f => {
  const config = path.join(f.S, '.ai-dev/v9-git-entrypoints.json');
  fs.unlinkSync(config);
  assert.equal(invoke(f, f.A()).blocked, true);
  assert.equal(invoke(f, f.B(path.join(f.home, 'unknown.json'))).blocked, false);
  for (const text of ['{}', JSON.stringify(f.config).replace('"schema_version":1', '"schema_version":1,"schema_version":1'), JSON.stringify({ ...f.config, extra: true })]) {
    fs.writeFileSync(config, text); assert.equal(invoke(f, f.A()).blocked, true);
  }
}));
test('Git repo-selection variables are isolated and preexisting index.lock survives', () => withFixture(f => {
  const dir = git(f.P, 'rev-parse', '--absolute-git-dir');
  const lock = path.join(dir, 'index.lock'); write(lock, 'other operation');
  const before = fs.statSync(lock).mtimeMs;
  const result = invoke(f, f.A(), { env: { GIT_DIR: path.join(f.R, '.git'), GIT_WORK_TREE: f.R, GIT_INDEX_FILE: lock, GIT_COMMON_DIR: path.join(f.R, '.git') } });
  assert.equal(result.blocked, false, result.out);
  assert.equal(fs.readFileSync(lock, 'utf8'), 'other operation'); assert.equal(fs.statSync(lock).mtimeMs, before);
  for (const c of result.calls) for (const key of ['GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR']) assert.equal(c.opts.env[key], undefined);
}));
test('foreign clone, detached and exact case-insensitive trunk names refuse', () => withFixture(f => {
  assert.equal(invoke(f, f.A(f.main, 'main')).blocked, true);
  git(f.P, 'switch', '--detach', '-q'); assert.equal(invoke(f, f.A(f.P, 'feature/main-nav')).blocked, true);
  git(f.P, 'switch', '-c', 'MASTER', '-q'); assert.equal(invoke(f, f.A(f.P, 'MASTER')).blocked, true);
  const foreign = path.join(f.base, 'foreign'); git(f.base, 'clone', '-q', '--no-hardlinks', f.main, foreign);
  git(foreign, 'switch', '-c', 'feature/foreign', '-q');
  assert.equal(invoke(f, f.A(foreign, 'feature/foreign')).blocked, true);
}));
test('non-push path gate words fail closed; symlink parent alias of P stays canonical', () => withFixture(f => {
  assert.equal(invoke(f, `${f.R}/bin/ai-dev v9 prepare-git --action commit --project ${f.P}/push-test --task FIXTURE-1`).blocked, true);
  if (f.P.startsWith('/private/var/')) {
    const alias = f.P.replace('/private/var/', '/var/');
    assert.equal(invoke(f, f.A(alias)).blocked, false);
  }
}));
test('diagnostic rejects public marker, ignores common Git dir and never overwrites a result', () => withFixture(f => {
  const command = 'git status --short --untracked-files=no -- .fitlog-native-hook-probe';
  const dir = git(f.S, 'rev-parse', '--absolute-git-dir');
  const request = path.join(dir, 'v9-gate-probe.request.json'), result = path.join(dir, 'v9-gate-probe.result.json');
  write(request, JSON.stringify({ schema_version: 1, nonce: 'b'.repeat(32) }), 0o644);
  invoke(f, command); assert.equal(fs.existsSync(result), false);
  const commonRequest = path.join(f.main, '.git/v9-gate-probe.request.json');
  write(commonRequest, JSON.stringify({ schema_version: 1, nonce: 'c'.repeat(32) }));
  invoke(f, command, { cwd: f.main }); assert.equal(fs.existsSync(path.join(f.main, '.git/v9-gate-probe.result.json')), false);
}));
test('runtime owner, unsafe ancestor, changed commit and entry bounds refuse', () => withFixture(f => {
  assert.equal(invoke(f, f.A(), { wrongOwner: path.join(f.R, 'scripts/v9/cli.py') }).blocked, true);
  fs.chmodSync(f.home, 0o777); assert.equal(invoke(f, f.A()).blocked, true); fs.chmodSync(f.home, 0o700);
  git(f.R, 'commit', '--allow-empty', '-qm', 'changed runtime'); assert.equal(invoke(f, f.A()).blocked, true);
  // Restore the fixture's pinned identity by a normal detached checkout; no
  // real task refs/state exist in this disposable repository.
  git(f.R, 'switch', '--detach', f.config.harness_commit, '-q');
  for (let n = 0; n < 4096; n++) write(path.join(f.R, 'scripts', `entry-${n}`), 'fixture');
  assert.equal(invoke(f, f.A()).blocked, true);
}));
test('oversized and otherwise-valid duplicate-field jobs refuse', () => withFixture(f => {
  fs.writeFileSync(f.J.file, Buffer.alloc(1024 * 1024 + 1, 0x20));
  assert.equal(invoke(f, f.B()).blocked, true);
  fs.writeFileSync(f.J.file, JSON.stringify(f.J.value).replace('"action":"push"', '"action":"push","action":"push"'));
  assert.equal(invoke(f, f.B()).blocked, true);
}));
test('whole quoted assignment is an executable, while quoting only its value is valid', () => withFixture(f => {
  const prefix = `AI_DEV_HARNESS_HOME=${f.R}`;
  assert.equal(invoke(f, f.A().replace(prefix, `"${prefix}"`)).blocked, true);
  assert.equal(invoke(f, f.A().replace(prefix, `AI_DEV_HARNESS_HOME="${f.R}"`)).blocked, false);
}));
for (const flag of ['--assume-unchanged', '--skip-worktree']) {
  test(`runtime bytes hidden by ${flag} are refused`, () => withFixture(f => {
    git(f.R, 'update-index', flag, 'scripts/v9/cli.py');
    fs.writeFileSync(path.join(f.R, 'scripts/v9/cli.py'), '# unreviewed changed runtime\n');
    assert.equal(invoke(f, f.A()).blocked, true);
  }));
}
test('runtime inspection never runs clean filters or trusts their normalized output', () => withFixture(f => {
  const marker = path.join(f.base, 'filter-marker');
  const filter = path.join(f.base, 'fixture-clean.cjs');
  const pristine = fs.readFileSync(path.join(f.R, 'scripts/v9/cli.py'), 'utf8');
  write(filter, `require('node:fs').writeFileSync(${JSON.stringify(marker)},'marker');process.stdin.resume();process.stdin.on('end',()=>process.stdout.write(${JSON.stringify(pristine)}));`);
  write(path.join(f.R, '.git/info/attributes'), ['scripts/v9/cli.py filter=fixture', ''].join(String.fromCharCode(10)));
  git(f.R, 'config', 'filter.fixture.clean', `${process.execPath} ${filter}`);
  assert.equal(git(f.R, 'check-attr', 'filter', '--', 'scripts/v9/cli.py'), 'scripts/v9/cli.py: filter: fixture');
  const target=path.join(f.R,'scripts/v9/cli.py');
  fs.writeFileSync(target,pristine.replace('disposable','unreviewed'));
  fs.utimesSync(target,new Date(0),new Date(0));
  // Prove the fixture really invokes a clean filter. Its status text is not
  // the content oracle; the hook must compare raw bytes and cause no effect.
  git(f.R, 'status', '--porcelain=v1', '--untracked-files=all', '--ignored', '--', 'bin', 'scripts');
  assert.equal(fs.existsSync(marker), true, 'fixture must exercise a real clean filter');
  fs.unlinkSync(marker);
  fs.writeFileSync(target,pristine.replace('disposable','unreviewed'));
  fs.utimesSync(target,new Date(1000),new Date(1000));
  const result = invoke(f, f.A());
  assert.equal(fs.existsSync(marker), false, 'inspection executed a clean filter');
  assert.equal(result.blocked, true);
}));
test('terminal project symlink is refused even with trailing slash or dot', () => withFixture(f => {
  const alias = path.join(f.base, 'project-link'); fs.symlinkSync(f.P, alias, 'dir');
  for (const project of [alias, alias+'/', alias+'/.']) assert.equal(invoke(f, f.A(project, 'feature/main-nav')).blocked, true, project);
}));
test('runtime index and physical file modes must match the pinned tree', () => withFixture(f => {
  const file=path.join(f.R,'scripts/v9/cli.py'), pristine=fs.readFileSync(file);
  fs.writeFileSync(file,'staged different runtime'); git(f.R,'add','scripts/v9/cli.py');
  fs.writeFileSync(file,pristine); assert.equal(invoke(f,f.A()).blocked,true);
}));
test('binary committed-blob framing fails closed on malformed, oversized, truncated or trailing data', () => withFixture(f => {
  for (const blobFault of ['header','size','truncated','trailing']) assert.equal(invoke(f,f.A(),{blobFault}).blocked,true,blobFault);
}));
test('an exhausted optional Git timeout does not fall back to a five-second call', () => {
  let calls=0;
  const fakeCp={execFileSync(){ calls++; return ''; }};
  const module={exports:{}};
  const load=name => ['child_process','node:child_process'].includes(name) ? fakeCp : require(name);
  const context=vm.createContext({require:load,module,exports:module.exports,__filename:sourcePath,__dirname:path.dirname(sourcePath),process,Buffer,console});
  vm.runInContext(source.toString('utf8'),context);
  const run=vm.runInContext('runGit',context);
  assert.equal(run(['rev-parse','HEAD'],__dirname,{timeout:0}).ok,false);
  assert.equal(calls,0);
});
test('replacement runtime commit cannot change the pinned content oracle', () => withFixture(f => {
  const pinned=f.config.harness_commit;
  fs.writeFileSync(path.join(f.R,'scripts/v9/cli.py'),'# replacement runtime code');
  git(f.R,'add','scripts/v9/cli.py'); git(f.R,'commit','-qm','replacement fixture');
  const replacement=git(f.R,'rev-parse','HEAD');
  git(f.R,'switch','--detach',pinned,'-q');
  git(f.R,'checkout',replacement,'--','bin','scripts');
  git(f.R,'replace',pinned,replacement);
  assert.equal(git(f.R,'rev-parse','HEAD'),pinned);
  assert.equal(invoke(f,f.A()).blocked,true);
  assert.equal(invoke(f,f.B()).blocked,true);
}));
test('replacement session config blob cannot conceal an uncommitted edit', () => withFixture(f => {
  const rel='.ai-dev/v9-git-entrypoints.json';
  const pinned=git(f.S,'rev-parse','HEAD:'+rel);
  fs.appendFileSync(path.join(f.S,rel),String.fromCharCode(10));
  const changed=git(f.S,'hash-object','-w',rel);
  git(f.S,'replace',pinned,changed);
  assert.equal(invoke(f,f.A()).blocked,true);
  assert.equal(invoke(f,f.B()).blocked,true);
}));
