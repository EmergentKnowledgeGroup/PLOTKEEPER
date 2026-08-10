import copy
import importlib.util
import unittest
from pathlib import Path

PATH = Path(__file__).parents[1] / "scripts" / "verify_public_release.py"
SPEC = importlib.util.spec_from_file_location("release_verifier", PATH)
VERIFIER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(VERIFIER)


class ReleaseVerifierTests(unittest.TestCase):
    candidate = "a" * 40
    diff_hash = "d" * 64

    def documents(self):
        contract = {
            "contract_hash": "", "baseline": {"sha": "b" * 40},
            "allowed": {"paths": ["scripts/", ".github/"]}, "forbidden": {"paths": ["plotkeeper/"]},
            "acceptance_cases": [{"id": "AC-1"}], "proof_requirements": [{"id": "PR-1"}],
            "review_requirements": [{"id": "RR-1"}], "release_requirements": [{"id": "RL-1"}],
        }
        contract["contract_hash"] = VERIFIER.canonical_hash(contract, "contract_hash")
        target = {"environment": "public GitHub", "artifact_digest": f"git:{self.candidate}", "traffic_or_execution_path": "https://github.com/o/r"}
        reviewer = {"identity": "independent", "review_run_id": "r", "independent": True, "implemented_candidate": False, "delegated_candidate": False, "approved_candidate": False}
        binding = {"contract_hash": contract["contract_hash"], "baseline_sha": "b" * 40, "candidate_sha": self.candidate, "target_fingerprint": "f" * 64}
        def receipt(phase, predecessors=()):
            item = {
                "review_receipt_hash": "", "contract_hash": contract["contract_hash"], "phase": phase,
                "baseline_sha": "b" * 40, "candidate_sha": self.candidate, "actual_diff_sha256": self.diff_hash,
                "target": target, "reviewer": reviewer,
                "source_evidence": [{"path": kind, "sha256": "e" * 64, "kind": kind, "binding": binding} for kind in ("user-goal", "contract", "diff", "test", "review", "deploy")],
                "obligation_results": [{"kind": kind, "id": id_, "status": "MET", "source_sha256": "e" * 64, "observation": "verified"} for kind, id_ in (("acceptance", "AC-1"), ("proof", "PR-1"), ("review", "RR-1"), ("release", "RL-1"))],
                "delegation": {"declaration": "NO_CHILDREN", "children": []},
                "predecessor_receipt_hashes": list(predecessors), "verdict": "PASS", "created_at_utc": "2026-08-10T00:00:00Z", "findings": []
            }
            item["review_receipt_hash"] = VERIFIER.canonical_hash(item, "review_receipt_hash")
            return item
        validated = receipt("VALIDATED")
        merge = receipt("MERGE_READY", [validated["review_receipt_hash"]])
        deploy = receipt("DEPLOY_READY", [validated["review_receipt_hash"], merge["review_receipt_hash"]])
        return contract, {"deploy": deploy, "predecessors": [validated, merge]}

    def verify(self, contract, bundle, paths=None):
        return VERIFIER.verify(contract, bundle, self.candidate, paths or ["scripts/x.py", ".github/workflows/x.yml"], self.diff_hash)

    def test_complete_release_chain_passes(self):
        contract, bundle = self.documents()
        self.assertEqual(self.verify(contract, bundle), [])

    def test_minimal_fabricated_receipt_fails(self):
        contract, _ = self.documents()
        errors = self.verify(contract, {"deploy": {"phase": "DEPLOY_READY", "verdict": "PASS"}, "predecessors": []})
        self.assertGreaterEqual(len(errors), 8)

    def test_mismatched_candidate_and_forbidden_path_fail(self):
        contract, bundle = self.documents()
        errors = VERIFIER.verify(contract, bundle, "c" * 40, ["plotkeeper/service.py"], self.diff_hash)
        self.assertIn("deploy-ready candidate mismatch", errors)
        self.assertTrue(any("outside contract" in error for error in errors))

    def test_tampered_receipt_and_broken_chain_fail(self):
        contract, bundle = self.documents()
        broken = copy.deepcopy(bundle)
        broken["deploy"]["verdict"] = "FAIL"
        broken["deploy"]["predecessor_receipt_hashes"] = []
        errors = self.verify(contract, broken)
        self.assertIn("deploy-ready receipt hash mismatch", errors)
        self.assertIn("receipt is not DEPLOY_READY PASS", errors)
        self.assertIn("deploy predecessor hash chain mismatch", errors)

    def test_missing_authority_obligation_and_delegation_fail(self):
        contract, bundle = self.documents()
        broken = copy.deepcopy(bundle)
        broken["deploy"]["source_evidence"] = []
        broken["deploy"]["obligation_results"] = []
        broken["deploy"]["delegation"] = {}
        errors = self.verify(contract, broken)
        self.assertIn("deploy-ready required source evidence is incomplete", errors)
        self.assertIn("deploy-ready required obligations are not all MET", errors)
        self.assertIn("deploy-ready delegation declaration missing", errors)

    def test_incomplete_predecessor_and_skipped_chain_fail(self):
        contract, bundle = self.documents()
        broken = copy.deepcopy(bundle)
        validated = broken["predecessors"][0]
        validated["reviewer"]["independent"] = False
        validated["source_evidence"] = []
        validated["obligation_results"] = []
        validated["delegation"] = {}
        validated["review_receipt_hash"] = VERIFIER.canonical_hash(validated, "review_receipt_hash")
        merge = broken["predecessors"][1]
        merge["predecessor_receipt_hashes"] = []
        merge["review_receipt_hash"] = VERIFIER.canonical_hash(merge, "review_receipt_hash")
        broken["deploy"]["predecessor_receipt_hashes"] = [validated["review_receipt_hash"], merge["review_receipt_hash"]]
        broken["deploy"]["review_receipt_hash"] = VERIFIER.canonical_hash(broken["deploy"], "review_receipt_hash")
        errors = self.verify(contract, broken)
        self.assertIn("validated reviewer is not independent", errors)
        self.assertIn("validated required source evidence is incomplete", errors)
        self.assertIn("validated required obligations are not all MET", errors)
        self.assertIn("validated delegation declaration missing", errors)
        self.assertIn("merge-ready predecessor hash chain mismatch", errors)


if __name__ == "__main__":
    unittest.main()
