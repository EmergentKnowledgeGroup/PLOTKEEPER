import copy
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

PATH = Path(__file__).parents[1] / "scripts" / "verify_public_release.py"
SPEC = importlib.util.spec_from_file_location("release_verifier", PATH)
VERIFIER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(VERIFIER)


class ReleaseVerifierTests(unittest.TestCase):
    def test_release_authorization_and_pointer_shape_fail_closed(self):
        for value in (None, "", "   ", 1, "RL-NONE", " RL-NONE ", " RL-DEPLOY"):
            self.assertFalse(VERIFIER._release_authorized({"release_requirements": [{"id": value, "phase": "DEPLOY_READY"}]}))
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pointer = root / "pointer.json"
            pointer.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "JSON object"):
                VERIFIER.designated_release_contract(root, "pointer.json")

    def test_repository_release_pointer_matches_live_designated_contract(self):
        root = Path(__file__).resolve().parents[1]
        pointer = json.loads((root / "runtime/goal-contracts/RELEASE_CONTRACT.json").read_text(encoding="utf-8"))
        contract = json.loads((root / pointer["contract_path"]).read_text(encoding="utf-8"))
        self.assertEqual(pointer["contract_sha256"], VERIFIER.canonical_json_hash(contract))

    candidate = "a" * 40
    diff_hash = "d" * 64
    review_key = "test-review-key"
    evidence_policy = {
        "user-goal": "runtime/goal-contracts/active.json", "contract": "runtime/goal-contracts/active.json",
        "diff": "scripts/verify_public_release.py", "test": "tests/test_release_verifier.py",
        "review": "scripts/verify_public_release.py", "deploy": ".github/workflows/release-verifier.yml",
    }

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
        binding = {"contract_hash": contract["contract_hash"], "baseline_sha": "b" * 40, "candidate_sha": self.candidate, "target_fingerprint": VERIFIER.target_fingerprint(target)}
        def receipt(phase, predecessors=()):
            item = {
                "review_receipt_hash": "", "contract_hash": contract["contract_hash"], "phase": phase,
                "baseline_sha": "b" * 40, "candidate_sha": self.candidate, "actual_diff_sha256": self.diff_hash,
                "target": target, "reviewer": reviewer,
                "source_evidence": [{"path": self.evidence_policy[kind], "sha256": "e" * 64, "kind": kind, "binding": binding} for kind in ("user-goal", "contract", "diff", "test", "review", "deploy")],
                "obligation_results": [{"kind": kind, "id": id_, "status": "MET", "source_sha256": "e" * 64, "observation": "verified"} for kind, id_ in (("acceptance", "AC-1"), ("proof", "PR-1"), ("review", "RR-1"), ("release", "RL-1"))],
                "delegation": {"declaration": "NO_CHILDREN", "children": []},
                "predecessor_receipt_hashes": list(predecessors), "verdict": "PASS", "created_at_utc": {"VALIDATED": "2026-08-10T00:00:00Z", "MERGE_READY": "2026-08-10T00:01:00Z", "DEPLOY_READY": "2026-08-10T00:02:00Z"}[phase], "findings": []
            }
            item["review_receipt_hash"] = VERIFIER.canonical_hash(item, "review_receipt_hash")
            return item
        validated = receipt("VALIDATED")
        merge = receipt("MERGE_READY", [validated["review_receipt_hash"]])
        deploy = receipt("DEPLOY_READY", [validated["review_receipt_hash"], merge["review_receipt_hash"]])
        documents = [validated, merge, deploy]
        signatures = {item["review_receipt_hash"]: VERIFIER.receipt_signature(item, self.review_key) for item in documents}
        return contract, {"deploy": deploy, "predecessors": [validated, merge], "signatures": signatures}

    def verify(self, contract, bundle, paths=None):
        evidence_hashes = {path: "e" * 64 for path in set(self.evidence_policy.values())}
        return VERIFIER.verify(contract, bundle, self.candidate, paths or ["scripts/x.py", ".github/workflows/x.yml"], self.diff_hash, self.review_key, evidence_hashes, self.evidence_policy)

    def test_complete_release_chain_passes(self):
        contract, bundle = self.documents()
        self.assertEqual(self.verify(contract, bundle), [])

    def test_minimal_fabricated_receipt_fails(self):
        contract, _ = self.documents()
        errors = self.verify(contract, {"deploy": {"phase": "DEPLOY_READY", "verdict": "PASS"}, "predecessors": []})
        self.assertGreaterEqual(len(errors), 8)

    def test_mismatched_candidate_and_forbidden_path_fail(self):
        contract, bundle = self.documents()
        errors = VERIFIER.verify(contract, bundle, "c" * 40, ["plotkeeper/service.py"], self.diff_hash, self.review_key,
                                 {path: "e" * 64 for path in set(self.evidence_policy.values())}, self.evidence_policy)
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

    def test_wrong_signature_and_nonexistent_evidence_fail(self):
        contract, bundle = self.documents()
        bundle["signatures"] = {key: "0" * 64 for key in bundle["signatures"]}
        errors = VERIFIER.verify(contract, bundle, self.candidate, ["scripts/x.py"], self.diff_hash,
                                 self.review_key, {}, self.evidence_policy)
        self.assertTrue(any("review signature mismatch" in error for error in errors))
        self.assertTrue(any("source evidence binding mismatch" in error for error in errors))

    def test_extra_kind_cannot_hide_missing_required_kind_or_semantic_path(self):
        contract, bundle = self.documents()
        deploy = bundle["deploy"]
        deploy["source_evidence"] = [item for item in deploy["source_evidence"] if item["kind"] != "test"]
        bogus = copy.deepcopy(deploy["source_evidence"][0])
        bogus["kind"] = "bogus"
        deploy["source_evidence"].append(bogus)
        deploy["review_receipt_hash"] = VERIFIER.canonical_hash(deploy, "review_receipt_hash")
        bundle["signatures"][deploy["review_receipt_hash"]] = VERIFIER.receipt_signature(deploy, self.review_key)
        errors = self.verify(contract, bundle)
        self.assertIn("deploy-ready required source evidence is incomplete", errors)
        self.assertIn("deploy-ready source evidence binding mismatch", errors)

    def test_fabricated_target_fingerprint_fails(self):
        contract, bundle = self.documents()
        deploy = bundle["deploy"]
        deploy["source_evidence"][0]["binding"]["target_fingerprint"] = "0" * 64
        deploy["review_receipt_hash"] = VERIFIER.canonical_hash(deploy, "review_receipt_hash")
        bundle["signatures"][deploy["review_receipt_hash"]] = VERIFIER.receipt_signature(deploy, self.review_key)
        self.assertIn("deploy-ready source evidence binding mismatch", self.verify(contract, bundle))

    def test_receipt_replay_before_candidate_fails(self):
        contract, bundle = self.documents()
        errors = VERIFIER.verify(contract, bundle, self.candidate, ["scripts/x.py"], self.diff_hash, self.review_key,
                                 {path: "e" * 64 for path in set(self.evidence_policy.values())}, self.evidence_policy,
                                 candidate_timestamp=2_000_000_000)
        self.assertTrue(any("receipt predates candidate" in error for error in errors))

    def test_validated_predecessor_needs_only_phase_relevant_obligations(self):
        contract, bundle = self.documents()
        validated = bundle["predecessors"][0]
        validated["obligation_results"] = [item for item in validated["obligation_results"] if item["id"] in {"AC-1", "PR-1", "PR-2"}]
        validated["review_receipt_hash"] = VERIFIER.canonical_hash(validated, "review_receipt_hash")
        merge = bundle["predecessors"][1]
        merge["predecessor_receipt_hashes"] = [validated["review_receipt_hash"]]
        merge["review_receipt_hash"] = VERIFIER.canonical_hash(merge, "review_receipt_hash")
        deploy = bundle["deploy"]
        deploy["predecessor_receipt_hashes"] = [validated["review_receipt_hash"], merge["review_receipt_hash"]]
        deploy["review_receipt_hash"] = VERIFIER.canonical_hash(deploy, "review_receipt_hash")
        documents = [validated, merge, deploy]
        bundle["signatures"] = {item["review_receipt_hash"]: VERIFIER.receipt_signature(item, self.review_key) for item in documents}
        self.assertEqual(self.verify(contract, bundle), [])

    def test_merge_ready_excludes_deploy_only_obligations(self):
        contract, bundle = self.documents()
        validated, merge = bundle["predecessors"]
        merge["obligation_results"] = [item for item in merge["obligation_results"] if item["id"] in {"AC-1", "PR-1", "PR-2"}]
        merge["review_receipt_hash"] = VERIFIER.canonical_hash(merge, "review_receipt_hash")
        deploy = bundle["deploy"]
        deploy["predecessor_receipt_hashes"] = [validated["review_receipt_hash"], merge["review_receipt_hash"]]
        deploy["review_receipt_hash"] = VERIFIER.canonical_hash(deploy, "review_receipt_hash")
        bundle["signatures"] = {item["review_receipt_hash"]: VERIFIER.receipt_signature(item, self.review_key) for item in (validated, merge, deploy)}
        self.assertEqual(self.verify(contract, bundle), [])

    def test_deploy_ready_excludes_attested_only_release_obligations(self):
        contract, bundle = self.documents()
        contract["release_requirements"].append({"id": "RL-2", "phase": "ATTESTED"})
        contract["contract_hash"] = VERIFIER.canonical_hash(contract, "contract_hash")
        for receipt in (*bundle["predecessors"], bundle["deploy"]):
            for evidence in receipt["source_evidence"]:
                evidence["binding"]["contract_hash"] = contract["contract_hash"]
            receipt["contract_hash"] = contract["contract_hash"]
            receipt["review_receipt_hash"] = VERIFIER.canonical_hash(receipt, "review_receipt_hash")
        validated, merge = bundle["predecessors"]
        merge["predecessor_receipt_hashes"] = [validated["review_receipt_hash"]]
        merge["review_receipt_hash"] = VERIFIER.canonical_hash(merge, "review_receipt_hash")
        deploy = bundle["deploy"]
        deploy["predecessor_receipt_hashes"] = [validated["review_receipt_hash"], merge["review_receipt_hash"]]
        deploy["review_receipt_hash"] = VERIFIER.canonical_hash(deploy, "review_receipt_hash")
        bundle["signatures"] = {
            item["review_receipt_hash"]: VERIFIER.receipt_signature(item, self.review_key)
            for item in (validated, merge, deploy)
        }
        self.assertFalse(any(item["id"] == "RL-2" for item in deploy["obligation_results"]))
        self.assertEqual(self.verify(contract, bundle), [])

    def test_deploy_ready_excludes_attested_only_acceptance_and_proof(self):
        contract, bundle = self.documents()
        contract["acceptance_cases"].append({"id": "AC-LIVE", "phase": "ATTESTED"})
        contract["proof_requirements"].append({"id": "PR-LIVE", "phase": "ATTESTED"})
        contract["contract_hash"] = VERIFIER.canonical_hash(contract, "contract_hash")
        for receipt in (*bundle["predecessors"], bundle["deploy"]):
            receipt["contract_hash"] = contract["contract_hash"]
            for evidence in receipt["source_evidence"]:
                evidence["binding"]["contract_hash"] = contract["contract_hash"]
            receipt["review_receipt_hash"] = VERIFIER.canonical_hash(receipt, "review_receipt_hash")
        validated, merge = bundle["predecessors"]
        merge["predecessor_receipt_hashes"] = [validated["review_receipt_hash"]]
        merge["review_receipt_hash"] = VERIFIER.canonical_hash(merge, "review_receipt_hash")
        deploy = bundle["deploy"]
        deploy["predecessor_receipt_hashes"] = [validated["review_receipt_hash"], merge["review_receipt_hash"]]
        deploy["review_receipt_hash"] = VERIFIER.canonical_hash(deploy, "review_receipt_hash")
        bundle["signatures"] = {
            item["review_receipt_hash"]: VERIFIER.receipt_signature(item, self.review_key)
            for item in (validated, merge, deploy)
        }
        self.assertEqual(self.verify(contract, bundle), [])

    def test_designated_pointer_is_stable_when_newer_nonrelease_contract_exists(self):
        base = Path(__file__).parents[1] / "runtime" / "qa"
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as folder:
            root = Path(folder)
            contracts = root / "runtime" / "goal-contracts"
            contracts.mkdir(parents=True)
            release = contracts / "release.json"
            release.write_text(json.dumps({
                "id": "release",
                "status": "ACTIVE",
                "contract_hash": "abc",
                "release_requirements": [{"id": "RL-DEPLOY", "phase": "DEPLOY_READY"}],
            }), encoding="utf-8")
            successor = contracts / "listener.json"
            successor.write_text(json.dumps({
                "id": "listener-ownership",
                "status": "ACTIVE",
                "contract_hash": "successor",
                "release_requirements": [{"id": "RL-NONE", "phase": "DEPLOY_READY"}],
            }), encoding="utf-8")
            os.utime(successor, (release.stat().st_atime + 100, release.stat().st_mtime + 100))
            pointer = {
                "schema_version": 1,
                "purpose": "PLOTKEEPER_PUBLIC_RELEASE",
                "contract_id": "release",
                "contract_path": "runtime/goal-contracts/release.json",
                "contract_sha256": VERIFIER.canonical_json_hash(json.loads(release.read_text(encoding="utf-8"))),
            }
            (contracts / "RELEASE_CONTRACT.json").write_text(json.dumps(pointer), encoding="utf-8")
            selected_path, selected = VERIFIER.designated_release_contract(root)
            self.assertEqual(selected_path, release.resolve())
            self.assertEqual(selected["id"], "release")

    def test_designated_pointer_rejects_nonrelease_and_tampered_targets(self):
        base = Path(__file__).parents[1] / "runtime" / "qa"
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as folder:
            root = Path(folder)
            contracts = root / "runtime" / "goal-contracts"
            contracts.mkdir(parents=True)
            target = contracts / "listener.json"
            target.write_text(json.dumps({
                "id": "listener-ownership",
                "status": "ACTIVE",
                "contract_hash": "successor",
                "release_requirements": [{"id": "RL-NONE", "phase": "DEPLOY_READY"}],
            }), encoding="utf-8")
            pointer = {
                "schema_version": 1,
                "purpose": "PLOTKEEPER_PUBLIC_RELEASE",
                "contract_id": "listener-ownership",
                "contract_path": "runtime/goal-contracts/listener.json",
                "contract_sha256": VERIFIER.canonical_json_hash(json.loads(target.read_text(encoding="utf-8"))),
            }
            pointer_path = contracts / "RELEASE_CONTRACT.json"
            pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "ACTIVE release contract"):
                VERIFIER.designated_release_contract(root)
            pointer["contract_id"] = "release"
            pointer["contract_sha256"] = "0" * 64
            pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                VERIFIER.designated_release_contract(root)

    def test_lf_and_crlf_contract_bytes_have_same_verifier_hash(self):
        base = Path(__file__).parents[1] / "runtime" / "qa"
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as folder:
            root = Path(folder)
            contracts = root / "runtime" / "goal-contracts"
            contracts.mkdir(parents=True)
            document = {
                "id": "release",
                "status": "ACTIVE",
                "contract_hash": "abc",
                "release_requirements": [{"id": "RL-DEPLOY", "phase": "DEPLOY_READY"}],
            }
            contract_path = contracts / "release.json"
            text = json.dumps(document, indent=2)
            pointer = {
                "schema_version": 1,
                "purpose": "PLOTKEEPER_PUBLIC_RELEASE",
                "contract_id": "release",
                "contract_path": "runtime/goal-contracts/release.json",
                "contract_sha256": VERIFIER.canonical_json_hash(document),
            }
            (contracts / "RELEASE_CONTRACT.json").write_text(json.dumps(pointer), encoding="utf-8")
            contract_path.write_text(text, encoding="utf-8", newline="\n")
            lf_path, lf = VERIFIER.designated_release_contract(root)
            contract_path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
            crlf_path, crlf = VERIFIER.designated_release_contract(root)
            self.assertEqual(lf_path, crlf_path)
            self.assertEqual(lf["contract_hash"], crlf["contract_hash"])


if __name__ == "__main__":
    unittest.main()
