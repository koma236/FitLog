'use strict';
// Read-only X2 classifier. The caller binds base/head to the PR and quality flag;
// this CLI never authorizes, merges, contacts GitHub, or changes Git state.
const {execFileSync} = require('node:child_process');
const MANIFEST = '.ai-dev-helm.json';
let cwd;
function git(...args) {
  return execFileSync('git', args, {
    cwd, encoding:'utf8', timeout:10000, maxBuffer:16*1024*1024,
    stdio:['ignore','pipe','pipe']
  });
}
function glob(pattern) {
  let source='';
  for(let i=0;i<pattern.length;i++) {
    const char=pattern[i];
    if(char==='*' && pattern[i+1]==='*') {
      i++;
      if(pattern[i+1]==='/') {i++; source+='(?:.*/)?';} else source+='.*';
    } else if(char==='*') source+='[^/]*';
    else if(char==='?') source+='[^/]';
    else source+=char.replace(/[.+^${}()|[\]\\]/g,'\\$&');
  }
  return new RegExp(`^${source}${pattern.endsWith('/') ? '.*' : ''}$`,'is');
}
const object = value => value !== null && typeof value==='object' && !Array.isArray(value);
function declarations(oid) {
  // ls-tree distinguishes a missing manifest from failed object reads.
  const entry=git('ls-tree','-z',oid,'--',MANIFEST);
  if(!entry) return [];
  if(!/^100(?:644|755) blob /.test(entry)) throw new Error(`${oid}: ${MANIFEST} must be a regular file`);
  const text=git('show',`${oid}:${MANIFEST}`);
  if(Buffer.byteLength(text)>1024*1024) throw new Error(`${oid}: manifest is over 1 MB`);
  const doc=JSON.parse(text.replace(/^\uFEFF/,''));
  if(!object(doc) || (doc.gate!==undefined && !object(doc.gate))) throw new Error(`${oid}: invalid manifest object/gate`);
  const patterns=doc.gate?.controlPlane;
  if(patterns===undefined) return [];
  if(!Array.isArray(patterns) || patterns.some(p=>typeof p!=='string' || !/^[^\\\0/][^\\\0]{0,1023}$/.test(p))) {
    throw new Error(`${oid}: gate.controlPlane must contain relative path patterns`);
  }
  return patterns.map(glob);
}
function main(args) {
  const options={};
  for(let i=0;i<args.length;i+=2) {
    if(!['--base','--head'].includes(args[i]) || options[args[i]]!==undefined || !/^(?:[a-f0-9]{40}|[a-f0-9]{64})$/i.test(args[i+1] || '')) {
      throw new Error('Usage: node scripts/check-pr-stop.cjs --base <full commit OID> --head <full commit OID>');
    }
    options[args[i]]=args[i+1];
  }
  const base=options['--base'], head=options['--head'];
  if(!base || !head) throw new Error('Both --base and --head commit OIDs are required');
  cwd=git('rev-parse','--show-toplevel').trim();
  for(const oid of [base,head]) if(git('cat-file','-t',oid).trim()!=='commit') throw new Error(`${oid} is not a commit`);
  const patterns=[...declarations(base),...declarations(head)];
  const changed=git('diff','--no-ext-diff','--no-textconv','--no-relative','--ignore-submodules=none','--name-only','-z','--no-renames',`${base}...${head}`).split('\0').filter(Boolean);
  const paths=changed.filter(file=>file.toLowerCase()===MANIFEST || /^\.github\/(?:workflows|ci)\//i.test(file) || patterns.some(p=>p.test(file)));
  process.stdout.write(JSON.stringify({base,head,stop:paths.length>0,paths})+'\n');
  process.exitCode=paths.length ? 2 : 0;
}
try {main(process.argv.slice(2));}
catch(error) {
  process.stdout.write(JSON.stringify({error:error.message})+'\n');
  process.exitCode=1;
}
