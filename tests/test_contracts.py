import importlib

from gate.contracts import PaymentAction, action_hash, canonical_json, Verdict


def test_all_modules_import():
    for m in ["gate.contracts", "gate.runbudget", "gate.extractor", "gate.policy", "gate.pipeline",
              "gate.verifiers", "gate.verifiers.crustdata_client", "gate.store", "gate.ledger",
              "gate.executor", "gate.payments.razorpayx"]:
        importlib.import_module(m)


def test_action_hash_stable_and_sensitive():
    a = PaymentAction("V1", "29ABCDE1234F1Z5|42|2026-27", 1234500, "h", "6789", "HDFC0000001", "k")
    b = PaymentAction("V1", "29ABCDE1234F1Z5|42|2026-27", 1234500, "h", "6789", "HDFC0000001", "k")
    assert action_hash(a) == action_hash(b)
    b.amount_paise += 1
    assert action_hash(a) != action_hash(b)


def test_canonical_json_enums():
    assert canonical_json({"v": Verdict.ALLOW}) == '{"v":"ALLOW"}'
