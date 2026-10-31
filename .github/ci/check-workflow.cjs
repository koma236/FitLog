'use strict'
const assert = require('node:assert/strict')
const same = (actual, expected, label) => assert.deepEqual(actual, expected, label)
const keys = (value, expected, label) => same(Object.keys(value).sort(), [...expected].sort(), label)
const command = 'bash .github/ci/required-status.sh "$BACKEND_RESULT" "$FRONTEND_RESULT"'
module.exports = function validate(document, config) {
  keys(document, ['name', 'on', 'permissions', 'concurrency', 'jobs'], 'no workflow execution overrides')
  same(document.name, 'CI', 'stable workflow name')
  same(document.on, { pull_request: { branches: ['main'] }, push: { branches: ['main'] } }, 'run every PR and main push')
  same(document.permissions, { contents: 'read' }, 'minimum token permissions')
  same(document.concurrency, {
    group: '${{ github.workflow }}-${{ github.event_name }}-${{ github.event.pull_request.number || github.run_id }}',
    'cancel-in-progress': "${{ github.event_name == 'pull_request' }}",
  }, 'only superseded PRs may cancel')
  same(Object.keys(document.jobs).sort(), ['backend', 'ci-required', 'frontend'], 'required jobs')
  const gate = document.jobs['ci-required']
  keys(gate, ['if', 'needs', 'runs-on', 'timeout-minutes', 'steps'], 'no aggregate job execution overrides')
  same(gate.if, 'always()', 'aggregate after failed, cancelled, or skipped dependencies')
  same(gate.needs, ['backend', 'frontend'], 'both job results are necessary')
  same(gate.steps.length, 2, 'checkout followed by the aggregate script')
  keys(gate.steps[1], ['name', 'env', 'run'], 'aggregate must execute unconditionally with the default shell')
  same(gate.steps[1].run, command, 'run the tested predicate')
  same(gate.steps[1].env, {
    BACKEND_RESULT: '${{ needs.backend.result }}',
    FRONTEND_RESULT: '${{ needs.frontend.result }}',
  }, 'pass actual job results, never fabricated success')
  for (const [name, job] of Object.entries(document.jobs)) {
    same(job['runs-on'], 'ubuntu-24.04', 'explicit hosted runner')
    same(job['timeout-minutes'], name === 'ci-required' ? 2 : 20, 'bounded execution')
    assert.equal(job['continue-on-error'], undefined)
    assert.equal(job.permissions, undefined, 'no elevated per-job token')
    if (name !== 'ci-required') {
      keys(job, ['runs-on', 'timeout-minutes', 'env', 'steps'], 'no check job execution overrides')
      same(job.env, { COMPOSE_PROJECT_NAME: `fitlog-ci-\${{ github.run_id }}-\${{ github.run_attempt }}-${name}` }, 'ephemeral project')
      same(job.steps.at(-1), { name: 'Cleanup', if: 'always()', run: 'docker compose down --volumes --remove-orphans' }, 'always clean only the isolated project')
    }
    for (const step of job.steps) {
      assert.equal(step['continue-on-error'], undefined, 'never ignore failure')
      if (step.uses) {
        keys(step, ['uses', 'with'], 'checkout has no execution overrides')
        assert.match(step.uses, /^actions\/checkout@[a-f0-9]{40}$/, 'immutable official checkout')
        same(step.with, { 'persist-credentials': false }, 'discard checkout credentials')
      } else {
        const expected = name === 'ci-required' ? ['name', 'env', 'run']
          : step === job.steps.at(-1) ? ['name', 'if', 'run'] : ['name', 'run']
        keys(step, expected, 'only the final cleanup may have a condition')
        assert.equal(typeof step.run, 'string')
        assert(!/\|\||continue-on-error|--service-ports|\bretry\b|exit\s+0\b/.test(step.run), 'no green-on-error or published dev ports')
      }
      assert(!JSON.stringify(step).includes('secrets.'), 'no workflow secrets')
    }
  }
  // The harness writes single-line TOML inline tables with quoted keys and JSON values.
  // Refuse unfamiliar formatting rather than silently omitting a new check.
  const match = config.match(/^checks = (\[.*\])$/m)
  assert(match, 'read the authoritative check argv arrays')
  // Convert only unquoted assignment separators; leave argv string contents intact.
  // This deliberately rejects other TOML spellings instead of silently losing checks.
  let quoted = false
  let escaped = false
  const json = [...match[1]].map(char => {
    if (quoted) {
      if (escaped) escaped = false
      else if (char === '\\') escaped = true
      else if (char === '"') quoted = false
      return char
    }
    if (char === '"') quoted = true
    return char === '=' ? ':' : char
  }).join('')
  const checks = JSON.parse(json)
  const expectedIds = ['compose-build', 'backend-lint', 'backend-types', 'django-check', 'backend-migrate', 'migration-drift', 'backend-tests', 'frontend-lint', 'frontend-types', 'frontend-tests', 'frontend-build']
  same(checks.map(check => check.id), expectedIds, 'all eleven local checks must remain represented')
  const commands = name => document.jobs[name].steps.filter(step => step.run).map(step => step.run.trim())
  const allowed = {
    backend: ['docker compose version', 'docker compose build backend', 'docker compose up --detach --wait postgres', 'docker compose down --volumes --remove-orphans'],
    frontend: ['docker compose version', 'docker compose build frontend', 'bash .github/ci/test-required-status.sh', 'docker build --file .github/ci/Dockerfile --build-arg FRONTEND_IMAGE=fitlog-dev-frontend --tag fitlog-ci-tools .', 'docker run --rm fitlog-ci-tools node /ci/test-workflow.cjs', 'docker compose down --volumes --remove-orphans'],
  }
  for (const check of checks) {
    same(check.argv.slice(0, 6), ['docker', 'compose', '--project-name', 'fitlog-dev', '-f', 'compose.yaml'])
    same(check.cwd, '.')
    same(check.env, {}, 'new check-specific environment must be explicitly mapped')
    if (check.id === 'compose-build') {
      same(check.argv.slice(6), ['build', 'backend', 'frontend'])
      assert(commands('backend').includes('docker compose build backend'))
      assert(commands('frontend').includes('docker compose build frontend'))
    } else {
      const name = check.id.startsWith('frontend-') ? 'frontend' : 'backend'
      const run = 'docker compose ' + check.argv.slice(6).join(' ')
      assert(commands(name).includes(run), `missing ${check.id}`)
      allowed[name].push(run)
    }
  }
  for (const name of ['backend', 'frontend']) {
    same([...commands(name)].sort(), allowed[name].sort(), 'run every check and CI self-test exactly once; no extra shell commands')
  }
  const backend = commands('backend')
  const ready = backend.indexOf('docker compose up --detach --wait postgres')
  const migrate = backend.findIndex(text => text.includes('manage.py migrate --noinput'))
  assert(ready >= 0 && ready < migrate, 'healthy PostgreSQL before migration')
  assert(backend.findIndex(text => text.includes('manage.py migrate --noinput')) < backend.findIndex(text => text.includes('pytest -q')), 'empty database migrated before tests')
  return true
}
