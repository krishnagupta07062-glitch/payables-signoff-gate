# Cross-team issues

Append only. Each entry: the file, the owner, the failing test or command, and the exact error.

## core

- **14:10, for Lavya and Ayush:** use `gate/keys.py` for invoice keys, invoice-number normalisation, financial year, account hashes and idempotency keys. Duplicate checks (Lavya) and payouts (Ayush) must agree byte for byte. `history_for()` rows should carry `invoice_key` exactly as `keys.invoice_key()` makes it. The prototype `norm_inv` has a bug: it maps I to 1 before stripping the "INV" prefix.

## checks

## pay
