# How the Payables Sign-Off Gate is built

```mermaid
flowchart TD
    IN["Vendor email or invoice<br/>(untrusted text)"] --> SAN["Sanitize<br/>strip hidden HTML, zero-width and Unicode tag text"]
    VM[("Vendor master<br/>trusted record, loaded first")] --> EXT
    SAN --> EXT["Extract claims<br/>language model: Claude or Gemini<br/>typed JSON only, never a decision"]
    EXT --> XC["Second reading<br/>fixed patterns for IFSC, GSTIN,<br/>account and invoice numbers"]
    XC --> VER

    subgraph VER["Verify every claim (each fact keeps its source and date)"]
        CD["Crustdata<br/>company identify, search, enrich<br/>person search, web enrich and search"]
        IND["India checks<br/>GSTIN checksum and GST portal<br/>IFSC lookup, RDAP domain age, lookalike domains"]
        HIS["History<br/>duplicate and near-duplicate invoices<br/>account on master, shared accounts, PO match"]
    end

    VER --> POL["Decide in plain code<br/>17 ordered rules<br/>BLOCK over ESCALATE over ALLOW"]
    POL -->|BLOCK| STOP["Stopped, with the reason and sources"]
    POL -->|ESCALATE| HUM["Approval queue<br/>a person calls back and approves or rejects"]
    POL -->|ALLOW| EXE
    HUM -->|approved| EXE["Executor<br/>signed single-use receipt bound to the payment hash<br/>outbox row written before the call"]
    EXE --> PAY["RazorpayX payout, test mode<br/>idempotency key from the invoice itself"]
    PAY --> LED[("Hash-chained ledger<br/>every request, check, decision,<br/>approval, payout and call cost")]
    POL --> LED
    MCP["MCP server<br/>gate_evaluate (never pays), ledger_verify"] -.-> POL
```

## Where things live

| Part | Code | Runs on |
|---|---|---|
| Sanitize, extract, second reading | `gate/sanitize.py`, `gate/extractor.py`, `gate/llm_gemini.py`, `gate/crosscheck.py` | Python 3.14. Claude API or Gemini API (free tier) |
| Checks | `gate/verifiers/` (Crustdata, India, history) | Crustdata API, ifsc.razorpay.com, RDAP registries, GST portal |
| Policy | `gate/policy.py` | Plain Python, no model |
| State | `gate/store.py`, `gate/ledger.py` | SQLite in WAL mode (`runs/gate.sqlite`): vendors, requests, decisions, approvals, outbox, payouts, calls, ledger |
| Payments | `gate/executor.py`, `gate/payments/razorpayx.py` | RazorpayX Payouts API in test mode, or a mock provider with the same rules |
| Call costs | `gate/runbudget.py` | Every external call is logged with its credits and tokens, under a per-run ceiling |
| Screens | `app/approvals.py`, `streamlit_app.py` | Streamlit |
| Agent access | `mcp_server/server.py` | MCP (stdio) |

## Where Crustdata is called

| Question | Endpoint |
|---|---|
| Is the sender's domain this vendor's domain? | `/company/identify`, `/company/search` |
| Is the vendor still operating, and is there recent news? | `/company/enrich`, `/web/search/live`, `/web/enrich/live` |
| Does the requester work at the vendor today, in that role? Did they leave? | `/person/search`, filtered by the vendor's company id |
| Who holds that role now (for the callback)? | `/person/search` |

Calls are cached on disk, keyed by the request, so a repeated check costs nothing. Crustdata allows 5 searches a minute, which the client respects.
