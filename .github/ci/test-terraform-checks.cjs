'use strict'
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { spawnSync } = require('node:child_process')
const { test } = require('node:test')

// Fixed oracle from the approved design; the executables are the external boundary.
const expected = [
  ['terraform', '-chdir=terraform', 'fmt', '-check', '-recursive'],
  ['terraform', '-chdir=terraform', 'init', '-backend=false', '-input=false', '-lockfile=readonly'],
  ['terraform', '-chdir=terraform', 'validate'],
  ['python3', '-B', '-m', 'unittest', 'discover', '-s', 'terraform/tests', '-p', 'test_*.py'],
  ['terraform', '-chdir=terraform', 'test', '-no-color'],
  ['node', '--test', 'terraform/functions/client-ip.test.cjs'],
]
for (const startup of ['early-exit', 'exported-function']) {
for (const failAt of [-1, 0, 1, 2, 3, 4, 5]) {
  test(`${startup}: ${failAt < 0 ? 'all checks execute and clean up' : `stage ${failAt} failure propagates and cleans up`}`, () => {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'fitlog ci '))
    try {
      const root = path.join(directory, 'repo with spaces')
      const bin = path.join(directory, 'bin')
      const log = path.join(directory, 'calls.jsonl')
      fs.mkdirSync(path.join(root, '.github/ci'), { recursive: true })
      fs.mkdirSync(bin)
      assert(fs.existsSync(path.join(__dirname, 'terraform-checks.sh')), 'common Terraform entrypoint must exist')
      fs.copyFileSync(path.join(__dirname, 'terraform-checks.sh'), path.join(root, '.github/ci/terraform-checks.sh'))
      for (const name of ['terraform', 'python3', 'node']) {
        const stub = `#!${process.execPath}
const fs = require('node:fs');
const log = ${JSON.stringify(log)};
const calls = fs.existsSync(log) ? fs.readFileSync(log, 'utf8').trim().split('\\n').length : 0;
fs.appendFileSync(log, JSON.stringify({argv: [${JSON.stringify(name)}, ...process.argv.slice(2)], cwd: process.cwd(), env: process.env}) + '\\n');
process.exit(calls === ${failAt} ? 37 : 0);
`
        fs.writeFileSync(path.join(bin, name), stub, { mode: 0o755 })
      }
      const marker = path.join(directory, 'startup.sh')
      fs.writeFileSync(marker, startup === 'early-exit' ? 'printf startup-was-executed >&2; exit 0\n' : 'export FITLOG_STARTUP_MARKER=unwanted\n')
      const result = spawnSync('/bin/bash', ['-p', path.join(root, '.github/ci/terraform-checks.sh')], {
        cwd: directory, encoding: 'utf8', timeout: 10000,
        env: { ...process.env, PATH: `${bin}:${process.env.PATH}`, HOME: directory,
          AWS_ACCESS_KEY_ID: 'DUMMY', AWS_SECRET_ACCESS_KEY: 'DUMMY', AWS_PROFILE: 'dummy',
          AWS_WEB_IDENTITY_TOKEN_FILE: marker, AWS_ROLE_ARN: 'dummy',
          AWS_CONTAINER_CREDENTIALS_FULL_URI: 'http://invalid.test',
          TF_VAR_expected_account_id: 'dummy', TF_CLI_ARGS: '-invalid',
          TF_CLI_CONFIG_FILE: marker, BASH_ENV: marker, CHECKPOINT_DISABLE: '0',
          ...(startup === 'exported-function' ? { 'BASH_FUNC_cd%%': '() { printf imported-function-was-executed >&2; exit 0; }' } : {}) },
      })
      assert.equal(result.error, undefined)
      assert.equal(result.status, failAt < 0 ? 0 : 37, result.stderr)
      assert.equal(result.stderr, '', 'startup file and exported functions must not execute')
      assert(fs.existsSync(log), 'the CLI verification stages must execute despite hostile startup environment')
      const calls = fs.readFileSync(log, 'utf8').trim().split('\n').map(JSON.parse)
      assert.deepEqual(calls.map(call => call.argv), expected.slice(0, failAt < 0 ? 6 : failAt + 1))
      const taskHome = calls[0].env.HOME
      assert.notEqual(taskHome, directory)
      assert.equal(fs.existsSync(taskHome), false, 'private temporary HOME removed')
      assert.equal(fs.existsSync(marker), true, 'caller resources preserved')
      for (const call of calls) {
        assert.equal(call.cwd, fs.realpathSync(root))
        assert.equal(call.env.HOME, taskHome)
        assert.equal(call.env.PATH, `${bin}:${process.env.PATH}`)
        for (const [key, value] of Object.entries({ CHECKPOINT_DISABLE: '1', TF_CLI_CONFIG_FILE: '/dev/null',
          TF_IN_AUTOMATION: '1', AWS_EC2_METADATA_DISABLED: 'true',
          AWS_SHARED_CREDENTIALS_FILE: '/dev/null', AWS_CONFIG_FILE: '/dev/null' })) {
          assert.equal(call.env[key], value, key)
        }
        const allowed = ['HOME', 'PATH', 'CHECKPOINT_DISABLE', 'TF_CLI_CONFIG_FILE', 'TF_IN_AUTOMATION',
          'AWS_EC2_METADATA_DISABLED', 'AWS_SHARED_CREDENTIALS_FILE', 'AWS_CONFIG_FILE',
          'PWD', 'SHLVL', '_', // bash's own process metadata
          ...(process.platform === 'darwin' ? ['__CF_USER_TEXT_ENCODING'] : [])] // added by Node/CoreFoundation even under env -i
        assert.deepEqual(Object.keys(call.env).filter(key => !allowed.includes(key)), [])
      }
    } finally {
      fs.rmSync(directory, { recursive: true, force: true })
    }
  })
}
}
