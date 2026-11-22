# Cross-team issues

Append only. Each entry: the file, the owner, the failing test or command, and the exact error.

## core

- **14:10, for Lavya and Ayush:** use `gate/keys.py` for invoice keys, invoice-number normalisation, financial year, account hashes and idempotency keys. Duplicate checks (Lavya) and payouts (Ayush) must agree byte for byte. `history_for()` rows should carry `invoice_key` exactly as `keys.invoice_key()` makes it. The prototype `norm_inv` has a bug: it maps I to 1 before stripping the "INV" prefix.

## checks

- **15:00, from Lavya (checks), for Krishna: please make lookalike domains ESCALATE, not BLOCK.** Today `gate/policy.py:109` maps `sender_domain_lookalike` CONTRADICTED to **B2 (BLOCK)**, and `tests/core/test_policy.py:61` asserts it. The lookalike check also flags weaker signals (a domain that contains the vendor's name, or the same name under another ending, e.g. a real partner at `acmecorp.com`), so a block there can stop a genuine vendor. Proposed change: keep `domain_age_days` CONTRADICTED in B2 (new or unregistered domain = BLOCK), and move `sender_domain_lookalike` CONTRADICTED to an escalate rule (e.g. a new E10 "Sender domain imitates the vendor's domain"), keeping its note. Cases 3 and 8 still BLOCK, because their mock_checks also have `domain_age_days` CONTRADICTED (`acmeleathers.in`). The checks side needs no change: the check keeps returning CONTRADICTED with `closest`, `distance` and `reason`.

- **14:40, from Lavya (checks), for Krishna:** `fixtures/vendors.json` vendors (V-ACME `acmeleather.in`, V-KTW `kanpurtannery.co.in`) have `crustdata_company_id: null`, and Crustdata has no record for those domains (research 05 §4.3: `acmeleather.in → []`). With live verifiers (`MOCK=0`), `sender_domain_matches_vendor`, `requester_current_role` and `requester_departed` can only return UNVERIFIABLE, so case 1 escalates (E6) instead of ALLOW, and cases 3, 4 and 8 lose their Crustdata evidence. Offline (`MOCK=1`) is unaffected. The live demo needs real vendors with a `crustdata_company_id` in `fixtures/private/`. Every non-network check already matches each case's `mock_checks`.

## pay
