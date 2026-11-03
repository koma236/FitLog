'use strict';
// Oracle: approved retirement plan and quality-gate's existing trunk contract.
// Commands below are stdin data to the hook, never Git delivery operations.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const cp = require('node:child_process');
const root = path.resolve(__dirname, '..');
const hooks = ['.claude/hooks/quality-gate.cjs', '.codex/hooks/quality-gate.cjs'];
const env = { ...process.env, GIT_CONFIG_GLOBAL: os.devNull, GIT_CONFIG_NOSYSTEM: '1', GIT_TERMINAL_PROMPT: '0' };
for (const k of ['GIT_DIR','GIT_WORK_TREE','GIT_INDEX_FILE','GIT_COMMON_DIR','GIT_OBJECT_DIRECTORY','GIT_ALTERNATE_OBJECT_DIRECTORIES']) delete env[k];
function fixture() {
  const cwd = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'fitlog-normal-gate-')));
  const git = (...args) => cp.execFileSync('git', ['-c','user.name=Fixture','-c','user.email=fixture@example.invalid',...args], { cwd, env, encoding:'utf8', stdio:['ignore','pipe','pipe'] }).trim();
  git('init','-q','-b','main');
  fs.writeFileSync(path.join(cwd,'app.txt'),'base\n');
  git('add','.'); git('commit','-qm','base');
  git('remote','add','origin','https://github.com/koma236/FitLog.git');
  const base=git('rev-parse','HEAD');
  git('update-ref','refs/remotes/origin/main',base);
  git('checkout','-qb','feature/fixture');
  fs.writeFileSync(path.join(cwd,'app.txt'),'feature\n');
  git('commit','-qam','feature');
  const head=git('rev-parse','HEAD');
  return {cwd,git,base,head,close:()=>fs.rmSync(cwd,{recursive:true,force:true})};
}
function judge(hook,f,command,options={}) {
  const payload = {tool_name:'Bash',cwd:f.cwd,tool_input:{command}};
  const r=cp.spawnSync(process.execPath,[path.join(root,hook)],{cwd:f.cwd,env,input:JSON.stringify({...payload,...options}),encoding:'utf8',timeout:25000});
  assert.equal(r.error,undefined); assert.equal(r.status,0,r.stderr);
  return r.stdout.trim() ? JSON.parse(r.stdout).decision : 'allow';
}
test('both hook copies are identical and obsolete registrations are absent',()=>{
  assert.deepEqual(fs.readFileSync(path.join(root,hooks[0])),fs.readFileSync(path.join(root,hooks[1])));
  for(const p of ['.ai-dev/v9-git-entrypoints.json','.ai-dev/v9-env-recovery.json','bin/ai-dev-git-env-recovery','scripts/v9_git_environment_recovery.py']) assert.equal(fs.existsSync(path.join(root,p)),false,p);
});
for(const hook of hooks) {
  test(`${hook}: normal feature operations and PR body file are permitted`,()=>{
    const f=fixture();try {
      for(const command of ['git status --short','git add -- app.txt','git commit -F /tmp/message.txt','git push origin HEAD:refs/heads/feature/fixture','gh pr create --body-file /tmp/body.md','/Users/saki/.local/bin/gh-koma236 pr create --body-file /tmp/body.md']) assert.equal(judge(hook,f,command),'allow',command);
    }finally{f.close();}
  });
  test(`${hook}: trunk, force and indirect operations remain blocked`,()=>{
    const f=fixture();try {
      for(const command of ['git push origin main','git push origin HEAD:main','git push --force origin main','git push origin +HEAD:main','git push --mirror origin','git branch -f main HEAD','git fetch origin feature/fixture:main','bash -c "git push origin main"','gh pr merge 1','/Users/saki/.local/bin/gh-koma236 pr merge 1','/Users/saki/.local/bin/gh-koma236 api repos/koma236/FitLog/pulls/1/merge']) assert.equal(judge(hook,f,command),'block',command);
      f.git('checkout','-q','main');
      assert.equal(judge(hook,f,'git merge feature/fixture'),'block');
      assert.equal(judge(hook,f,'git rebase feature/fixture'),'block');
    }finally{f.close();}
  });
  test(`${hook}: quality evidence is bound to the incoming commit`,()=>{
    const f=fixture();try {
      f.git('checkout','-q','main');
      const flag=path.join(f.cwd,'.quality-check-passed');
      fs.writeFileSync(flag,JSON.stringify({branch:'feature/fixture',commit:f.base}));
      assert.equal(judge(hook,f,'git merge feature/fixture'),'block');
      fs.writeFileSync(flag,JSON.stringify({branch:'feature/fixture',commit:f.head}));
      assert.equal(judge(hook,f,'git merge feature/fixture'),'allow');
      assert.equal(judge(hook,f,'git push --force origin main'),'block');
    }finally{f.close();}
  });
  test(`${hook}: shell inputs fail closed and old delivery syntax has no exception`,()=>{
    const f=fixture();try {
      assert.equal(judge(hook,f,'',{tool_input:{}}),'block');
      for(const command of ['AI_DEV_HARNESS_HOME=/retired /retired/bin/ai-dev v9 prepare-git --action push --project /target --task OLD --remote origin --branch feature/fixture','AI_DEV_HARNESS_HOME=/retired /retired/bin/ai-dev v9 git-action /retired/push-0123456789.json --project /target']) assert.equal(judge(hook,f,command),'block',command);
    }finally{f.close();}
  });
}
