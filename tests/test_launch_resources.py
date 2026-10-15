import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from plotkeeper import review_runner
from plotkeeper.ledger import Ledger
from plotkeeper.models import RunState
from plotkeeper.service import PlotkeeperService


class LaunchResourceTests(unittest.TestCase):
    def test_unused_output_goes_to_null_not_pipe_or_spool(self):
        # Representative output exceeds OS pipe capacity on both streams.
        code = "import os; [(os.write(1,b'x'*65536),os.write(2,b'y'*65536)) for _ in range(128)]"
        started = []
        real_popen = subprocess.Popen
        with mock.patch.object(review_runner, 'scoped_review_args', side_effect=lambda x: x), \
                mock.patch.object(review_runner.subprocess, 'Popen', wraps=real_popen) as popen:
            result = review_runner.run_review([sys.executable, '-c', code], cwd=os.getcwd(),
                                             on_started=lambda p: started.append(p.pid))
        self.assertEqual(result.returncode, 0)
        self.assertIsNone(result.stdout)
        self.assertIsNone(result.stderr)
        self.assertEqual(len(started), 1)
        self.assertEqual(popen.call_args.kwargs['stdout'], subprocess.DEVNULL)
        self.assertEqual(popen.call_args.kwargs['stderr'], subprocess.DEVNULL)

    def test_failed_callback_reaps_exact_child(self):
        children = []
        def reject(child):
            children.append(child)
            raise RuntimeError('test callback')
        with mock.patch.object(review_runner, 'scoped_review_args', side_effect=lambda x: x):
            with self.assertRaises(RuntimeError):
                review_runner.run_review([sys.executable, '-c', 'import time; time.sleep(60)'],
                                         cwd=os.getcwd(), on_started=reject)
        self.assertIsNotNone(children[0].poll())

    def test_optional_localtools_does_not_break_public_installs(self):
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(review_runner, 'LAZY_MCP_ROOT', Path(td) / 'absent'), \
                mock.patch.dict(os.environ, {}, clear=True):
            args = ['codex.exe', 'exec', 'test']
            self.assertEqual(review_runner.scoped_review_args(args), args)
            with self.assertRaises(review_runner.ReviewToolsUnavailable):
                review_runner.scoped_review_args(args, lazy_root=Path(td) / 'explicit')

    def test_cross_connection_single_flight_and_explicit_retry(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            service = PlotkeeperService(ledger_path=base / 'ledger.sqlite', sessions_root=base / 'sessions',
                                        codex_state_path=base / 'absent.sqlite')
            peer = Ledger(base / 'ledger.sqlite')
            try:
                run = service.ledger.enroll('root', str(base), service.dashboard_url)
                service.ledger.mark_review_required(run.run_id)
                token, error = service.ledger.claim_launch(run.run_id, 'review', owner_pid=os.getpid(),
                                                           owner_created=service._own_process_identity())
                self.assertIsNone(error)
                other, error = peer.claim_launch(run.run_id, 'review', owner_pid=os.getpid(), owner_created=None)
                self.assertIsNone(other)
                self.assertIsNotNone(error)
                service.ledger.finish_launch(token, returncode=23, diagnostic='review_process_exit')
                self.assertEqual(service.ledger.get(run.run_id).state, RunState.REVIEW_REQUIRED)
                self.assertFalse(service.inject_review(run.run_id, runner=lambda *_a, **_k: 0)['ok'])
                self.assertTrue(service.retry_review(run.run_id, runner=lambda *_a, **_k: 0)['ok'])
            finally:
                peer.close_db()
                service.close_db()
