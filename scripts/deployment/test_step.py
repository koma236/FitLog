"""Remote event oracle: emitted by the remote process, never by the collector."""
import contextlib
import io
import json
import unittest

from test_contract import fixture

from operations.deployment_step import main


class StepTests(unittest.TestCase):
    def arguments(self, step='migrate'):
        data = fixture()
        return ['--step', step, '--run-id', data['run_id'], '--expected-host',
                data['resources']['database_host'], '--environment', data['environment']]

    def test_success_event_is_remote_and_suppresses_child_output(self):
        out, err = io.StringIO(), io.StringIO()
        def runner(step, context):
            print('SECRET-CHILD-OUTPUT')
            self.assertEqual(step, 'migrate')
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(self.arguments(), runner=runner)
        self.assertEqual(code, 0)
        event = json.loads(out.getvalue())
        self.assertEqual(event, {'event': 'deployment_step_completed', 'step': 'migrate',
                                 'run_id': fixture()['run_id']})
        self.assertEqual(err.getvalue(), '')

    def test_failure_and_systemexit_cannot_emit_success_or_secret(self):
        for error in (RuntimeError('PRIVATE-EXCEPTION'), SystemExit(1)):
            def runner(step, context, failure=error):
                print('PRIVATE-OUTPUT')
                raise failure
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                self.assertEqual(main(self.arguments(), runner=runner), 2)
            self.assertEqual(out.getvalue(), '')
            self.assertEqual(json.loads(err.getvalue()), {'event': 'deployment_step_failed'})

    def test_unknown_step_does_not_call_runner_or_echo_arguments(self):
        calls = []
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = main(self.arguments('PRIVATE-UNKNOWN'), runner=lambda *args: calls.append(args))
        self.assertEqual(code, 2)
        self.assertEqual(calls, [])
        self.assertNotIn('PRIVATE', err.getvalue())
