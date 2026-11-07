import type { FullResult, Reporter, TestCase, TestResult } from '@playwright/test/reporter'
import { writeFileSync } from 'node:fs'
import path from 'node:path'
import { artifact } from './environment.js'

/** Deliberately ignore raw errors, stdout, stderr, step payloads and attachments. */
export default class SafeReporter implements Reporter {
  private failed = false
  private rows: { status: string; duration_ms: number }[] = []
  onTestEnd(_test: TestCase, result: TestResult) {
    this.rows.push({ status: result.status, duration_ms: result.duration })
  }
  onError() { this.failed = true }
  onStdOut() {}
  onStdErr() {}
  onEnd(result: FullResult) {
    writeFileSync(path.join(artifact, 'runner.json'), JSON.stringify({
      status: result.status, worker_error: this.failed, tests: this.rows,
    }, null, 2))
    process.stdout.write(JSON.stringify({ status: result.status, worker_error: this.failed }) + '\n')
  }
}
