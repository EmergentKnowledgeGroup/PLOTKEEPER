import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from plotkeeper.cli import main
from plotkeeper import doctor


class DoctorTests(unittest.TestCase):
    def test_doctor_does_not_initialize_private_runtime(self):
        with mock.patch('plotkeeper.cli.ensure_connector') as connector, \
                mock.patch('plotkeeper.cli.PlotkeeperService') as service, \
                contextlib.redirect_stdout(io.StringIO()):
            main(['doctor'])
        connector.assert_not_called()
        service.assert_not_called()

    def test_mismatched_and_extra_package_files_are_reported(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / 'plotkeeper').mkdir()
            (base / 'plotkeeper' / 'old.py').write_text('old', encoding='utf-8')
            result = doctor.diagnose(base)
            self.assertFalse(result['ok'])
            self.assertIn('package_content_mismatch', result['issues'])
            self.assertIn('old.py', result['different_files'])
            self.assertIn('review_runner.py', result['different_files'])
            self.assertTrue((base / 'plotkeeper' / 'old.py').exists())
