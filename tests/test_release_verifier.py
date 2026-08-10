import importlib.util
import unittest
from pathlib import Path

PATH = Path(__file__).parents[1] / "scripts" / "verify_public_release.py"
SPEC = importlib.util.spec_from_file_location("release_verifier", PATH)
VERIFIER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(VERIFIER)


class ReleaseVerifierTests(unittest.TestCase):
    def documents(self):
        contract = {
            "contract_hash": "", "allowed": {"paths": ["scripts/", ".github/"]},
            "forbidden": {"paths": ["plotkeeper/"]}
        }
        contract["contract_hash"] = VERIFIER.canonical_hash(contract, "contract_hash")
        receipt = {
            "review_receipt_hash": "", "contract_hash": contract["contract_hash"],
            "candidate_sha": "a" * 40, "phase": "DEPLOY_READY", "verdict": "PASS",
            "reviewer": {"independent": True, "implemented_candidate": False}
        }
        receipt["review_receipt_hash"] = VERIFIER.canonical_hash(receipt, "review_receipt_hash")
        return contract, receipt

    def test_exact_release_passes(self):
        contract, receipt = self.documents()
        self.assertEqual(VERIFIER.verify(contract, receipt, "a" * 40, ["scripts/x.py", ".github/workflows/x.yml"]), [])

    def test_mismatched_candidate_and_forbidden_path_fail(self):
        contract, receipt = self.documents()
        errors = VERIFIER.verify(contract, receipt, "b" * 40, ["plotkeeper/service.py"])
        self.assertIn("receipt candidate mismatch", errors)
        self.assertTrue(any("outside contract" in error for error in errors))

    def test_tampered_receipt_fails(self):
        contract, receipt = self.documents()
        receipt["verdict"] = "FAIL"
        errors = VERIFIER.verify(contract, receipt, "a" * 40, [])
        self.assertIn("review receipt hash mismatch", errors)
        self.assertIn("receipt is not DEPLOY_READY PASS", errors)


if __name__ == "__main__":
    unittest.main()
