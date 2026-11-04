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
// Oracle: Issue #36's approved design §1: route every collaboration prefix
// to the hook; review-budget itself decides which requests consume a seat.
for (const event of ['PreToolUse', 'PostToolUse']) {
  test(`review-budget registration: ${event} covers native and collaboration tools`, () => {
    const config = JSON.parse(fs.readFileSync(path.join(root, '.codex/hooks.json'), 'utf8'));
    const registrations = config.hooks[event].filter(entry =>
      entry.hooks.some(hook => hook.command.includes('review-budget.cjs')));
    assert.equal(registrations.length, 1);
    const matcher = new RegExp(registrations[0].matcher);
    for (const tool of ['Agent', 'Task', 'spawn_agent', 'followup_task', 'send_message', 'send_input', 'resume_agent',
      'collaborationspawn_agent', 'collaborationfollowup_task', 'collaborationsend_message',
      'collaborationsend_input', 'collaborationresume_agent', 'collaborationlist_agents',
      'collaborationwait_agent', 'collaborationinterrupt_agent', 'collaborationspawn_agent_suffix']) {
      assert.equal(matcher.test(tool), true, tool);
    }
    for (const tool of ['Bash', 'exec_command', 'prefixspawn_agent', 'spawn_agent_suffix', 'prefixcollaborationspawn_agent']) {
      assert.equal(matcher.test(tool), false, tool);
    }
  });
}
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
test('review-budget: non-candidate collaboration tools do not consume or track reviews', () => {
  const f = fixture();
  try {
    const script = path.join(root, '.codex/hooks/review-budget.cjs');
    const status = () => {
      const r = cp.spawnSync(process.execPath, [script, 'status'], { cwd:f.cwd, env, encoding:'utf8' });
      assert.equal(r.status, 0, r.stderr);
      return JSON.parse(r.stdout);
    };
    const before = status();
    for (const event of ['PreToolUse', 'PostToolUse']) {
      for (const tool of ['collaborationlist_agents', 'collaborationwait_agent', 'collaborationinterrupt_agent', 'collaborationspawn_agent_suffix']) {
        const r = cp.spawnSync(process.execPath, [script], {
          cwd:f.cwd, env, encoding:'utf8', input:JSON.stringify({
            hook_event_name:event, tool_name:tool, cwd:f.cwd,
            tool_input:{task_name:'document-reviewer', message:'HELM_REVIEW:00000000000000000000000000000000:document-reviewer'},
            tool_response:{agent_id:'must-not-be-tracked'}
          })
        });
        assert.equal(r.status, 0, r.stderr);
        assert.equal(r.stdout, '', `${event} ${tool}`);
        assert.equal(r.stderr, '', `${event} ${tool}`);
      }
    }
    assert.deepEqual(status(), before);
  } finally { f.close(); }
});
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
  test(`${hook}: the AI merge procedure in personal-workflow.md is gated by the flag`,()=>{
    const f=fixture();try {
      const merge=`gh pr merge 1 --merge --match-head-commit ${f.head}`;
      for(const command of ['gh api user --jq .login','gh repo view --json nameWithOwner','gh pr view 1 --json state,baseRefName,baseRefOid,headRefName,headRefOid',`node scripts/check-pr-stop.cjs --base ${f.base} --head ${f.head}`]) assert.equal(judge(hook,f,command),'allow',command);
      assert.equal(judge(hook,f,merge),'block');
      const flag=path.join(f.cwd,'.quality-check-passed');
      fs.writeFileSync(flag,JSON.stringify({branch:'feature/fixture',commit:f.base}));
      assert.equal(judge(hook,f,merge),'block');
      fs.writeFileSync(flag,JSON.stringify({branch:'feature/fixture',commit:f.head}));
      assert.equal(judge(hook,f,merge),'allow');
    }finally{f.close();}
  });
  test(`${hook}: harness-only diffs need the flag under the declared controlPlane`,()=>{
    const declared=fs.readFileSync(path.join(root,'.ai-dev-helm.json'));
    for(const file of ['CLAUDE.md','AGENTS.md','backend/CLAUDE.md','docs/AGENTS.md','.cursorrules','.cursor/x.md','.claude/x.md','.codex/x.md','skills/project/x/SKILL.md','.github/review-docs.md','documents/development/coding-rules/x.md']) {
      const f=fixture();try {
        f.git('checkout','-q','main');
        fs.writeFileSync(path.join(f.cwd,'.ai-dev-helm.json'),declared);
        fs.writeFileSync(path.join(f.cwd,'.gitignore'),'.quality-check-passed\n');
        f.git('add','.'); f.git('commit','-qm','manifest');
        f.git('update-ref','refs/remotes/origin/main',f.git('rev-parse','HEAD'));
        f.git('checkout','-qb','harness/only');
        fs.mkdirSync(path.dirname(path.join(f.cwd,file)),{recursive:true});
        fs.writeFileSync(path.join(f.cwd,file),'changed\n');
        f.git('add','.'); f.git('commit','-qm','harness');
        assert.equal(judge(hook,f,'gh pr merge 1 --merge'),'block',file);
        fs.writeFileSync(path.join(f.cwd,'.quality-check-passed'),JSON.stringify({branch:'harness/only',commit:f.git('rev-parse','HEAD')}));
        assert.equal(judge(hook,f,'gh pr merge 1 --merge'),'allow',file);
      }finally{f.close();}
    }
  });
  test(`${hook}: declared API writes are denied even with quality evidence, reads remain allowed`, () => {
    const f = fixture();
    try {
      fs.writeFileSync(path.join(f.cwd,'.ai-dev-helm.json'), fs.readFileSync(path.join(root,'.ai-dev-helm.json')));
      f.git('add','.ai-dev-helm.json'); f.git('commit','-qm','declare denied API commands');
      const denied = [
        'gh api graphql -f query="mutation { mergePullRequest(input: {pullRequestId: id}) { clientMutationId } }"',
        '/Users/saki/.local/bin/gh-koma236 api graphql --raw-field=query=mergePullRequest',
        "gh api --hostname github.com 'graphql' -F 'query=mutation { mergePullRequest }'",
        'gh api graphql \\\n -f query=mergePullRequest',
        'gh api repos/koma236/FitLog/rulesets/1 -X PUT --input /tmp/rules.json',
        'gh api -XDELETE repos/koma236/FitLog/rulesets/1',
        'gh api repos/koma236/FitLog/rulesets/1 -X=DELETE',
        'gh api -X=PUT repos/koma236/FitLog/rulesets/1',
        'gh api -X=PATCH repos/koma236/FitLog/rulesets/1',
        'gh api -X=POST repos/koma236/FitLog/rulesets',
        'gh api --method=PATCH /repos/koma236/FitLog/rulesets/1',
        "gh api '--method' 'DELETE' 'repos/koma236/FitLog/rulesets/1'",
        '/Users/saki/.local/bin/gh-koma236 api repos/koma236/FitLog/rulesets/1 --method DELETE',
        'GH API REPOS/koma236/FitLog/RULESETS/1 -X PUT',
        'gh api repos/{owner}/{repo}/rulesets -X POST --input /tmp/rules.json',
        'gh api repos/koma236/FitLog/rulesets -f name=changed',
        'gh api -F enforcement=disabled repos/koma236/FitLog/rulesets/1',
        'gh api repos/koma236/FitLog/rulesets/1 --field=enforcement=disabled',
        'gh api repos/koma236/FitLog/rulesets/1 --raw-field enforcement=disabled',
        'gh api repos/koma236/FitLog/rulesets/1 --input=/tmp/rules.json',
        'gh api repos/koma236/FitLog/rulesets/1 -X GET -f name=query'
      ];
      const reads = [
        'gh api user --jq .login',
        'gh api repos/koma236/FitLog/rulesets',
        'gh api repos/koma236/FitLog/rulesets/1 -X GET',
        'gh api --method=GET /repos/koma236/FitLog/rulesets/1',
        'gh api graphql -f query="query { viewer { login } }"',
        'gh api repos/koma236/FitLog/issues -f title=fixture'
      ];
      for (const withFlag of [false, true]) {
        if (withFlag) fs.writeFileSync(path.join(f.cwd,'.quality-check-passed'),JSON.stringify({branch:'feature/fixture',commit:f.git('rev-parse','HEAD')}));
        for (const command of denied) assert.equal(judge(hook,f,command),'block',command);
        for (const command of reads) assert.equal(judge(hook,f,command),'allow',command);
      }
    } finally { f.close(); }
  });
  test(`${hook}: without the declaration a root rule diff is exempt, so the declaration is what closes it`,()=>{
    const f=fixture();try {
      f.git('checkout','-q','main');
      f.git('checkout','-qb','harness/only');
      fs.writeFileSync(path.join(f.cwd,'CLAUDE.md'),'changed\n');
      f.git('add','.'); f.git('commit','-qm','harness');
      assert.equal(judge(hook,f,'gh pr merge 1 --merge'),'allow');
    }finally{f.close();}
  });
  test(`${hook}: shell inputs fail closed and old delivery syntax has no exception`,()=>{
    const f=fixture();try {
      assert.equal(judge(hook,f,'',{tool_input:{}}),'block');
      for(const command of ['AI_DEV_HARNESS_HOME=/retired /retired/bin/ai-dev v9 prepare-git --action push --project /target --task OLD --remote origin --branch feature/fixture','AI_DEV_HARNESS_HOME=/retired /retired/bin/ai-dev v9 git-action /retired/push-0123456789.json --project /target']) assert.equal(judge(hook,f,command),'block',command);
    }finally{f.close();}
  });
}
