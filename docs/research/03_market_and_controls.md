# Research 3: Market, Controls, Competitors for the "Sign-Off Gate for Payables"

Compiled 2026-11-22. About 30 sources read; all URLs below were fetched or seen in search results during this session.
Labels used:
- **[V]** verified: I read the number in the primary source or the publisher's own page.
- **[S]** secondary: a reputable outlet or a vendor quoting a primary source that I did not open.
- **[E]** estimate or vendor or market-research projection: use with care.
- **[D]** our own design choice, not a sourced industry figure.

---

## 0. TL;DR for the pitch (best numbers)

| # | Claim | Number | Source | Label |
|---|---|---|---|---|
| 1 | BEC losses reported to FBI IC3, 2025 | **US$3.05B** (US$3,046,598,558), 24,768 complaints. About 2.5% of complaints but about 15% of losses. Up 10% from US$2.77B in 2024 | Stingrai summary of the FBI IC3 2025 report, pp. 25-26: https://stingrai.io/blog/business-email-compromise-statistics-2026 (Oct 1, 2026). The FBI press release confirms the ~$21B total: https://www.fbi.gov/news/press-releases/cryptocurrency-and-ai-scams-bilk-americans-of-billions (Apr 6, 2026) | [S] for the BEC line, [V] for the total |
| 2 | Share of organisations hit by BEC (attempted or actual) | **74% in 2025**, up from 63% in 2024. Fraudsters "primarily impersonate vendors or executives to request changes to payment instructions" | AFP 2026 Payments Fraud & Control Survey, key highlights (n=465, Apr 2026): https://truist.com/content/dam/truist-bank/us/en/documents/info/cci/2026-afp-payments-fraud-control-survey-report-key-highlights.pdf | [V] |
| 3 | Vendor-imposter fraud | **45% of organisations in 2024**, up from 34% in 2023. Invoice fraud rose from 14% to 24% | AFP 2025 survey highlights (n=521): http://truist.com/content/dam/truist-bank/us/en/documents/info/cci/2025-afp-payments-fraud-control-survey-report-key-highlights.pdf | [V] |
| 4 | Best-rated anti-BEC control | Callback to an authorised contact **using a number from official records, not the email**: 94% have implemented it and **63% rate it "very effective"**, the highest of any control | AFP 2026, p.12 | [V] |
| 5 | India: largest single SME-style BEC case found | **₹6.49 crore**, Pune, 27 Mar 2025. Fraudsters changed **one letter** of the vendor's email and the bank account number. The bank called to verify and the director told it to proceed | TOI, Apr 25 2025: https://timesofindia.indiatimes.com/city/pune/pune-company-loses-rs-6-5-crore-to-man-in-the-middle-cyber-attack/articleshow/120595690.cms | [V] |
| 6 | India: the same attack this week | **₹1.5 crore**, Hyderabad semiconductor firm. Lookalike supplier domain (an extra "i"), a "2% discount" lure, and a new account at a Polish bank. Paid Oct 7 2026 | TOI, Nov 18 2026: https://timesofindia.indiatimes.com/city/hyderabad/email-spoofing-costs-hyderabad-based-semiconductor-firm-1-5-crore/amp_articleshow/135969506.cms | [V] |
| 7 | Indian regulator warning, 2 days ago | CERT-In **CIAD-2026-0062 (Critical, Nov 20 2026)**: attackers alter "business records or approval relationships that determine payments" and then use legitimate payment processes. CERT-In requires "independent verification for high-risk changes ... payment instructions, beneficiaries" | https://cert-in.org.in/s2cMainServlet?VLCODE=CIAD-2026-0062&pageid=PUBVLNOTES02 | [V] |
| 8 | Duplicate-payment leakage | **0.1-0.5% of AP spend** lost to duplicates. Recovery firms claw back only 40-60% and charge 25-40% contingency | Cadel (vendor) benchmark: https://cadel.ai/us/blog/duplicate-invoice-detection (Jun 15 2026). IOFM is cited elsewhere at 0.5-1% for mid/large firms (fiscaltec, 2024) | [E] |
| 9 | Cost of the human service being replaced | **US$9.84 per invoice** on average, **8.2 days** cycle time, **18.4% exception rate** (Ardent 2025). The 2026 figures are $9.90 average vs **$2.67 best-in-class** | Ardent Partners: https://payablesplace.ardentpartners.com/2026/01/state-of-epayables-part-nine-ap-benchmarks-and-best-in-class-performance ; Medius summary of Ardent 2026 | [V] for 2025, [S] for 2026 |
| 10 | AI is now attacking AP agents directly | Sublime found an invoice-fraud campaign on **Oct 22 2026** that hid prompt-injection text in invisible Unicode tag characters, aimed at AI email agents. The goal was to get the agent to route a roughly $88k fake invoice into AP | https://sublime.security/blog/invoice-fraud-campaign-adds-prompt-injection-aimed-at-email-ai-agents (Oct 26 2026) | [V] |

Bonus numbers:
- **Arup**: HK$200M (about US$25.6M) lost after a deepfake CFO video call (CNN, May 16 2024) [V-headline].
- **FBI IC3 2025**: first-ever AI section, **22,364 complaints, about $893M** [V, FBI press release].
- **AFP 2026**: deepfake attempts hit 7% of organisations, and only 17% of organisations use AI to fight payments fraud [V].
- **AFP 2026**: "For every 100 attempts by a fraudster, 20 are successful." 20% of victims recovered nothing [V].

---

## 1. Size of the problem

### 1.1 Global and US

**FBI IC3**
- 2024 report (released Apr 23 2025):
  - Total losses were $16.6B.
  - BEC losses were **$2,770,151,146**, the #2 crime by loss after investment fraud.
  - BEC was the 7th most-reported crime, with 21,442 complaints.
  - Sources: https://www.fbi.gov/news/press-releases/fbi-releases-annual-internet-crime-report ; https://nacha.org/news/fbis-ic3-finds-almost-85-billion-lost-business-email-compromise-last-three-years ; https://ecompnow.com/fbi-releases-2024-internet-crime-report [V/S]
- 2025 report (released Apr 6 2026):
  - 1,008,597 complaints, with total losses of nearly $21B ($20.877B per McDonald Hopkins).
  - First AI section: 22,364 complaints, about $893M. Source: https://www.fbi.gov/news/press-releases/cryptocurrency-and-ai-scams-bilk-americans-of-billions [V]
  - BEC losses were $3,046,598,558 across 24,768 complaints.
  - Wire or ACH made up 86% of BEC payment methods.
  - The FBI Recovery Asset Team froze 58% of $1.16B chased, down from 82% in 2020. This is the speed argument for blocking *before* the money moves.
  - BEC source: Stingrai's compilation of IC3 2025 pp. 25-26, https://stingrai.io/blog/business-email-compromise-statistics-2026 [S]
  - Forbes reports more than $30M in 2025 BEC losses that involved AI: https://forbes.com/sites/timkeary/2026/04/07/fbi-reports-208-billion-lost-to-cybercrime-as-hackers-turn-to-ai [S]
- IC3 PSA I-091124-PSA put global exposed BEC losses at **$55.5B** from Oct 2013 to Dec 2023 (305,033 incidents), as cited by Stingrai [S].

**AFP Payments Fraud & Control Survey**
- 2026 edition (2025 data, n=465 US treasury practitioners). Source: https://truist.com/content/dam/truist-bank/us/en/documents/info/cci/2026-afp-payments-fraud-control-survey-report-key-highlights.pdf [V]
  - 76% of organisations had attempted or actual payments fraud: 81% of firms with revenue of $1B or more, and 67% of firms under $1B.
  - BEC affected 74% of organisations.
  - 39% still receive genuine emails that fraudsters intercepted.
  - Sources of fraud among victims: BEC or fraudulent email 70%, manipulated ACH/wire instructions 33%, invoice fraud 26%, deepfake attempts 7%.
  - Firms under $1B revenue: 48% of those hit suffered a loss, and 24% recovered nothing.
  - Only 17% use AI against payments fraud.
  - A verbatim respondent story matches our product exactly: "A scammer took over the email box of one of our key vendors ... bogus invoices were processed in the normal way with all approval steps. At the same time, the fraudster requested bank account information be changed which was entered into the system before Treasury could confirm the same."
  - A second story shows the classic failure: "AP called the number on the email to confirm the banking details."
- 2025 edition (2024 data, n=521). Source: http://truist.com/content/dam/truist-bank/us/en/documents/info/cci/2025-afp-payments-fraud-control-survey-report-key-highlights.pdf [V]
  - 79% of organisations experienced fraud.
  - BEC hit 63%.
  - **Vendor imposter fraud hit 45%, up from 34%.**
  - Invoice fraud hit 24%, up from 14%.
  - Among BEC types, vendor impersonation was cited by 60% and "classic" exec impersonation fell from 57% to 49%.
  - Wire transfers were used in 63% of BEC cases.
  - More than half of practitioners say **AP is the department most vulnerable to email fraud**.

**Other vendor and industry data**
- Trustmi 2026 Benchmark (260 B2B incidents in 2025): 59% of attacks layer two or more tactics, and 39% of attacks included invoices, W-9s or bank details. Trustmi projects socially engineered fraud above $40B a year by 2027. https://trustmi.ai/2026-benchmark-payment-security-report/ [E, vendor]
- Eftsure / ACCC (Australia):
  - Payment-redirection (BEC) losses were A$166.8M in 2025, up 9.3%.
  - Eftsure has flagged A$11B+ of potentially fraudulent payments.
  - INTERPOL (cited by Eftsure) says AI-enabled fraud is 4.5x more profitable than non-AI fraud.
  - Source: https://eftsure.com/en-au/statistics/payment-fraud-index [S]
- Coalition 2026 claims (via Stingrai): BEC plus funds-transfer fraud made up 58% of cyber-insurance claims, and 39% of funds-transfer-fraud events had no confirmed email compromise [S].
- Abnormal Security: 83% of large enterprises experienced a vendor email compromise (VEC) attack in 2024, and 44% of VEC messages that get read are replied to or forwarded. https://files.abnormalsecurity.com/production/files/CISO-Guide-to-VEC.pdf ; https://files.abnormalsecurity.com/production/files/Legacy-SEGs-Can%E2%80%99t-Stop-Vendor-Email-Compromise.pdf [E, vendor]
- Medius Financial Census 2026 (n=2,386): 87% of finance professionals have ignored a small claim they believed was fraudulent. https://medius.com/financial-census [E, vendor survey]

**ACFE Occupational Fraud**
- 2024 report: billing schemes were 22% of cases with a $100k median loss. The typical organisation loses 5% of revenue. 32% of frauds trace to lack of internal controls and 19% to override of controls. https://www.acfe.com/en-us/-/media/files/acfe/pdfs/rttn/2024/2024-report-to-the-nations.pdf (summarised at luceo.legal and grfcpa) [S]
- 2026 report: billing schemes were 21% of cases, with a **median duration of 14 months** before detection. Schemes caught within 6 months had a $40k median loss; those lasting 7-12 months had $100k. https://acfe.com/-/media/files/acfe/pdfs/rttn/2026/2026-report-to-the-nations.pdf (from the search snippet, plus ethicontrol.com) [S]

### 1.2 Duplicate payments and AP error rates
- **APQC** tracks "percentage of disbursements that are duplicate or erroneous" as an Open Standards Benchmarking measure (Sep 2024): https://www.apqc.org/resource-library/resource-listing/percentage-duplicate-disbursements-processed. The value is paywalled [V-existence].
- **IOFM**: duplicate or erroneous payments are 0.5%-1% of total invoice payments at large and mid-sized firms (via fiscaltec, Mar 2024: https://fiscaltec.com/detecting-and-preventing-duplicate-payments-in-accounts-payable/). An IOFM benchmark says about 2.4% of supplier invoice payments need correction (https://www.iofm.com/ap/process-improvement/automation/how-to-prevent-mistakes-or-fix-them-after-they-happen) [S]
- Industry rule of thumb: duplicates hit **0.1-0.8% of invoices** (Peakflo, Dost) and cost **0.1-0.5% of AP spend** (Cadel) [E].
  - Cadel's claim: single-field (invoice-number-only) checks catch 1 of 6 common duplicate patterns.
  - Cadel's claim: post-payment recovery gets back 40-60%, and recovery-audit firms charge 25-40% of what they recover.
- **Ardent Partners, State of ePayables 2025** (n=204): https://payablesplace.ardentpartners.com/2026/01/state-of-epayables-part-nine-ap-benchmarks-and-best-in-class-performance [V]
  - $9.84 per invoice, 8.2 days, 18.4% exception rate.
  - 21.9% of staff time goes to supplier interaction.
  - Best-in-class firms are 79% cheaper and 79% faster.
- Ardent 2026 (via Medius and Docsumo): $9.90 average, $2.67 best-in-class, 19.9% exception rate (11.8% best-in-class) [S].

### 1.3 India-specific

**RBI Annual Report**
- Covers frauds of ₹1 lakh and above. Most of the value is in advances (loans), so these figures are not BEC-specific. Use them only as "fraud is rising in value."
- FY2024-25 (reported May 2025): 23,953 cases, **₹36,014 crore**, about 3x the prior year. Sources: https://www.business-standard.com/finance/news/bank-fraud-amount-triples-in-fy25-despite-drop-in-number-of-cases-rbi-125052900696_1.html ; https://indianexpress.com/article/business/bank-fraud-amount-jumps-by-three-times-to-rs-36014-crore-in-fy25-rbi-10036075 [S]
- FY2025-26 (RBI AR released May 29 2026): 10,114 cases, **₹48,021 crore**. FY25 was restated to 23,722 cases and ₹32,803 crore. Card/internet/digital payments frauds fell to 293 cases (₹29 cr) from 13,332 (₹517 cr). https://www.fortuneindia.com/personal-finance/banking/bank-frauds-drop-in-number-but-surge-to-48021-crore-in-value-in-2025-26-rbi-report/140369 (PTI) [S]

**I4C / MHA (Lok Sabha, Jul 22 2025)**
- Citizens lost **₹22,845.73 crore** to cyber fraud in 2024, against ₹7,465.18 crore in 2023, a 206% rise.
- 36.4 lakh financial frauds were reported on NCRP and CFCFRMS.
- Sources: https://www.business-standard.com/india-news/citizens-lost-over-22-845-crore-to-cyber-criminals-in-2024-govt-tells-ls-125072200883_1.html ; https://timesofindia.indiatimes.com/india/indias-cybercrime-reporting-systems-logged-36-lakh-fraud-cases-in-2024-rs-22845-cr-lost-over-10000-arrested/articleshow/122841677.cms [S]
- These figures are consumer-heavy and not BEC-specific.

**CERT-In advisories (all [V], read in full)**
- **CIAD-2026-0062, Nov 20 2026, Critical: "Abuse of Business Payment Workflows and Use of AI-Driven Agentic Offensive Frameworks across Sectors."**
  - CERT-In has seen unauthorised transactions at non-financial organisations, including "platforms responsible for vendor or partner payouts".
  - The method: "Alteration of business records or approval relationships that determine payments, followed by the use of legitimate payment processes."
  - The gap exploited: "Exploitation of gaps in independent verification, reconciliation and review of changes to business records."
  - The key line: *"A transaction may pass the usual application and approval checks even when the records used to initiate it have been changed without authorisation. Organisations need to verify the underlying business records and the authority for a payment, in addition to validating the payment request itself."*
  - Recommendation: "The verification source should not be capable of being altered through the same compromised provider environment."
  - Recommendation: "Multiple approvals within the same provider-controlled system may not provide sufficient protection if that environment is compromised."
  - Reporting duties: report to CERT-In within 6 hours, and to NCRP or helpline 1930.
  - Source: https://cert-in.org.in/s2cMainServlet?VLCODE=CIAD-2026-0062&pageid=PUBVLNOTES02 . Coverage: https://www.cnbctv18.com/technology/cert-in-warns-of-unauthorised-payment-transactions-ai-driven-cyberattacks-across-sectors-20038937.htm/amp
- **CIAD-2026-0046, Oct 9 2026: payment and disbursement API abuse at NBFCs, fintechs and payment service providers.** Recommended controls include:
  - "Implement maker-checker or second-level verification for all fund movement"
  - "Validate every payout against sanctioned/approved records; reject reference identifiers with no corresponding records"
  - "per-transaction and per-day cumulative ceilings"
  - "beneficiary validation (penny-drop, name-to-account matching) and velocity limits"
  - "new-beneficiary checks, with automated blocking or holding"
  - "near-real-time reconciliation"
  - "log retention of at least 180 days"
  - Source: https://www.cert-in.org.in/s2cMainServlet?pageid=PUBVLNOTES02&VLCODE=CIAD-2026-0046
- **CIAD-2026-0049, Oct 15 2026: "AI Agents as Attack Vectors."** Referenced inside 0062; not read in full [V-title].

**RBI rule that helps our gate**
- RBI circular RBI/2024-25/99 (Dec 30 2024) requires a **beneficiary bank account name look-up for RTGS/NEFT**, live by **April 1 2025**. Source: https://rbi.org.in/scripts/NotificationUser.aspx?Id=12759 [V]
- Banks must show the beneficiary's CBS name at beneficiary registration and at one-time transfers.
- If the name cannot be shown, "the remitter can proceed ... at her discretion." That leaves an opening, and our gate closes it by policy.
- Logs must be preserved, and the facility is free of charge.

**Indian BEC / vendor bank-change cases (news)**

| Date | Victim / place | Amount | Modus operandi | Outcome | Source | Label |
|---|---|---|---|---|---|---|
| Mar 27 2025 | IT + dry-fruit import firm, Pune | ₹6.49 cr (5 transactions) | One letter changed in the US exporter's email address and the account number. The bank called to verify and the director said proceed. The ledger showed only the first few letters of the name and account | About ₹3 cr not yet withdrawn when reported. FIR filed Apr 23 | TOI Apr 25 2025 (link above) | [V] |
| Aug 2025 | Firm, Pune | n/a | Fake domain in the vendor's name, vendor bank account changed | Cops recovered money | https://timesofindia.indiatimes.com/city/pune/cops-save-firms-money-lost-in-email-spoofing-fraud/articleshow/123312588.cms | [S-snippet] |
| Nov 3-4 2025 | Dr Reddy's paying Group Pharmaceuticals | ₹2.2 cr | Email trail hacked. Fake vendor emails with new bank details sent to the finance team | Frozen via 1930 in an MP account. "No financial loss" | https://timesofindia.indiatimes.com/city/bengaluru/pharma-firm-caught-in-rs-2-2-crore-cyber-fraud/articleshow/125229729.cms | [V] |
| Nov 2025 | Firm, Mangaluru (Equiflex impersonated) | ₹1 cr | Fake email ID payment request | FIR | https://timesofindia.indiatimes.com/city/mangaluru/over-rs-1-cr-lost-in-email-fraud-after-fake-payment-request/articleshow/125140028.cms | [S-snippet] |
| Sep 2026 | Firm, Vadodara | ₹20 lakh | Altered supplier email (trusea-ae.com), new account at First Abu Dhabi Bank | FIR | https://timesofindia.indiatimes.com/city/vadodara/firm-loses-rs-20l-lakh-in-fake-supplier-email-fraud/articleshow/133812824.cms | [S-snippet] |
| Sep 2-29 2026 | Lulu Group, Kochi | €150,500 (about ₹1.64 cr) | Lookalike emails of Italian partner IE Park SRL, fake invoices plus bank details | FIR under BNS/IT Act | https://economictimes.indiatimes.com/industry/banking/finance/lulu-group-loses-rs-1-64-crore-in-email-fraud-how-impersonators-used-italian-companys-identity-to-cheat-retail-giant/articleshow/135164359.cms | [V] |
| Oct 2026 | Engineering co., Patancheru (Hyderabad) | ₹35 lakh+ | Vendor email hacked, payment redirected | FIR | https://timesofindia.indiatimes.com/city/hyderabad/firm-loses-over-35l-in-email-hacking-fraud/articleshow/134841190.cms | [S-snippet] |
| Sep 28-Oct 7 2026 | Space-semiconductor firm, Hyderabad | ₹1.5 cr+ | Lookalike domain (double "i"), "2% discount" revised invoice, account at a Polish bank for a China-based supplier | FIR Nov 2026 | TOI Nov 18 2026 (link above) | [V] |
| Nov 2026 | Ahmedabad: 4 arrested | ₹6.55 lakh | Manipulated business emails plus forged bank documents, 7 mule accounts | Arrests | https://the420.in/ahmedabad-email-hacking-case-exposes-seven-bank-accounts-used-in-cyber-fraud/ | [S-snippet] |

Pattern in the Indian cases. Each item maps to a gate rule:
1. A lookalike sender domain with a single-character edit.
2. A new beneficiary account, often in a different country from the vendor.
3. A lure such as urgency, a discount, or "revised invoice."
4. A human "verification" that did not compare old and new account details.
5. Fast reporting to 1930 is what saved the money (Dr Reddy's).

### 1.4 Indian outsourced accounting / AP market (what we replace)
Market sizes:
- India accounting services: **USD 28.38B in 2025**, forecast USD 65.63B by 2034 (IMARC): https://www.imarcgroup.com/india-accounting-services-market [E]
- India F&A BPO: **US$3.19B in 2025**, forecast $8.53B by 2033, a 13.1% CAGR (Grand View): https://grandviewresearch.com/horizon/outlook/finance-and-accounting-business-process-outsourcing-market/india [E]
- An India "Account Payable market" estimate of US$115.5M in 2025 (MRFR) uses a very different scope. It is unreliable, so do not quote it [E].

Pricing:
- IncorpX lists AP services from **₹3,999/month for up to 50 invoices** (about ₹80 per invoice). Source: https://incorpx.io/accounts-payable-services-in-gurgaon. This is from the search snippet only; the page was bot-blocked [S-snippet].
- LinkedIn guides put India outsourced accounting at roughly ₹15,000-₹28,000/month for service SMEs [E, low quality].
- US offshore bookkeeping runs about $1,500-$2,500/month (1840 & Co). US AP outsourcing runs about $1.50-$3 per invoice (austinbookkeepinghub) [E].

Addressable base:
- Udyam MSME registrations reached about **9.78 crore** as of Oct 6 2026 (PIB): https://static.pib.gov.in/WriteReadData/specificdocs/documents/2026/oct/doc_10115_20261006_19035001.pdf [V-snippet]
- Registrations reportedly crossed 10 crore by Oct 30 2026 [S].

---

## 2. Standard AP controls, as policy rules

### 2.1 What practitioners say works (AFP 2026, p.12: effectiveness of BEC controls) [V]

| Control | Implemented | Very effective | Effective |
|---|---|---|---|
| Policies to verify changes to invoices, bank deposits, contact details | 96% | 58% | 33% |
| **Callback to authorised payee contact using a number from official records, not email** | 94% | **63%** | 31% |
| Senior management sign-off for transactions over a threshold | 94% | 52% | 32% |
| **Prohibit payment initiation based on emails / less-secure messaging** | 91% | 53% | 35% |
| Shared passcodes, not in email, for wires | 42% | 52% | 26% |
| End-user training | 96% | 42% | 42% |

AFP 2026 conclusion: "Organizations should set clear policies for standard payment turnaround times: time can work both for and against a fraudster. Allowing more time before making a payment can help prevent fraud, while immediate or emergency payments should be closely examined." This supports a cooling-off rule.

### 2.2 Bank-detail change SOP (practitioner consensus)
- **Stampli SOP:** https://www.stampli.com/resources/vendor-bank-change-callback-protocol/ (Jun 2026) [V]
  1. The request lands in "pending verification" and payments to that vendor **pause automatically**.
  2. Call back on the on-file number and confirm with a known contact.
  3. Record who verified, when, the number called, and who confirmed.
  4. A second person who did not process the change approves it.
  5. Only then does the new account become payable.
  - Also: portal-only changes are "the strongest single control".
  - A contact change at the same time as a bank change is a high-risk pattern. "Don't verify a new contact using only that new contact - that's circular."
  - Confirm to the known-good email and notify the old contact.
  - Audit evidence to keep: the original request, verifier, channel, number called, vendor-side confirmer, an approver distinct from the processor, and timestamps.
- **Wondergate playbook:** https://www.wondergate.io/blog/vendor-bank-account-change-controls-2026 [V]
  - First-payment hold ON for any new or changed account.
  - The hold clears only on three conditions: (1) a callback to the number on file, (2) beneficiary validation against verified records, and (3) maker-checker approval plus an elapsed cooling-off period.
  - Risk tiers: same country/entity, then new account/currency, then **new country or beneficiary-name mismatch, which means hold pending investigation**.
  - "Urgency changes the staffing priority, not the evidence standard."
  - Alert when **one vendor has multiple changes** or **multiple vendors change to the same account**.
  - The approval screen must show **old and new values side by side**.
  - Cites NIST SP 800-53 for separation of duties.
  - Suggests an SLA of about 1 business day rather than a fixed multi-day hold.
- **Cyberwalla call-script** example: "the first payment goes after [5] business days" after a verified change. https://cyberwalla.com/articles/vendorBankChangeVerification [S-snippet]
- **precisebankflow:** the number-choice order starts with "the number on file in the vendor master from before the request arrived". https://precisebankflow.com/blog/vendor-bank-account-change-verification [S-snippet]

### 2.3 Duplicate detection heuristics
Sources:
- Cadel: https://cadel.ai/us/blog/duplicate-invoice-detection [V]
- Medius: https://www.medius.com/blog/duplicate-invoices/ (Oct 30 2026) [V]

Tiers:
1. **Normalise first.** Strip separators, spaces and leading zeros, and ignore case, so that INV-0921 equals inv921. Map vendor-name variants to one vendor ID, and match on ID, not name.
2. **Exact match.** Vendor ID + normalised invoice number + amount.
3. **Fuzzy invoice number.** Same vendor + same amount + invoice number within a small edit distance (suffix "-R", a dropped zero, a dash).
4. **Same vendor + same amount within a date window** of typically **60-90 days**, which catches re-invoicing under a new number.
5. **Vendor entity hierarchy.** Parent and subsidiaries submitting the same invoice.
6. **Credit memo followed by re-invoice.** Pair them.
7. **PO number.** Matters when a vendor reuses invoice numbers.
8. **Single intake queue.** Email, portal and upload must share one history. Off-cycle manual payments and ERP migrations are blind spots.
9. **Score bands.** High score: auto-hold. Middle: human review. Low: pass. "Replacement invoices" (a late fee added or discount applied) need a human or policy decision.

### 2.4 India-specific verification hooks
- **Penny-drop / penniless name match (RazorpayX Fund Account Validation).** Source: https://razorpay.com/docs/api/x/composite-account-validation/bank-account [V]
  - Endpoint: `POST /v1/fund_accounts/validations`, with `validation_type` set to `pennydrop`, `penniless` or `optimized`.
  - Returns `account_status` (active or invalid), `registered_name`, and `name_match_score` from 0 to 100. 100 means identical, 0 means no match, anything between is partial.
  - `status` is created, completed or failed. A failure carries `source` (gateway, beneficiary_bank, business or internal) and a reason such as "retry after 30 min".
  - **Treat a failed validation as unverifiable, so the gate returns ESCALATE, never ALLOW.**
- **RBI name look-up for RTGS/NEFT** (above). This is the regulatory parallel to the name match.
- **GSTIN checks.**
  - Format is 15 characters: state code (2) + PAN (10) + entity number + "Z" + checksum.
  - Look up status (active, cancelled) and legal or trade name on the GST portal or a GSP API.
  - The GSTIN's PAN should match the vendor PAN on file.
- **E-invoicing (IRN).**
  - Mandatory for suppliers with aggregate annual turnover (AATO) of ₹5 crore or more.
  - From **Apr 1 2025**, suppliers with **AATO of ₹10 crore or more cannot report an e-invoice to the IRP more than 30 days after the invoice date**. Without an IRN, the document is not a valid tax invoice. Source: GSTN advisory https://einvoice1.gst.gov.in/Documents/advisory270325.pdf ; also https://tallysolutions.com/gst/e-invoicing-limit-india/ [S]
  - Gate rule: if the vendor's profile says e-invoicing applies and the invoice has no IRN or signed QR, ESCALATE (or mark ITC risk).
- **MSME 45-day rule.**
  - MSMED Act s.15 gives 15 days without a written agreement and up to 45 days with one.
  - Income Tax s.43B(h) disallows the deduction if payment to a micro or small vendor is late. Sources: https://taxguru.in/income-tax/finance-ministry-clarifies-section-43bh-45-day-msme-payment-rule.html ; https://kkscapital.com/blog/msme-payment-rule-section-43bh [S]
  - **Design implication:** holds and ESCALATE queues have a legal deadline. The gate must surface the "days to MSME deadline" so a human resolves the case in time. Blocking forever is not free.
- **Incident response.**
  - Report to helpline 1930 or cybercrime.gov.in immediately, and to CERT-In within 6 hours (CERT-In Directions, Apr 28 2022).
  - The Dr Reddy's case shows that a fast freeze recovers the funds.

### 2.5 PROPOSED POLICY RULES (encode deterministically)
Rule IDs are ours [D]; the rationale and sources are cited. Decision precedence: any BLOCK beats any ESCALATE, which beats ALLOW. Anything unverifiable becomes ESCALATE.

**Bank-detail change / vendor master**

| ID | Rule | Decision | Source basis |
|---|---|---|---|
| BC-1 | A bank-detail change requested via email or free text is never auto-applied. It creates a `PENDING_VERIFICATION` case and auto-holds all payments to that vendor | ESCALATE (hold) | Stampli SOP step 1; AFP "prohibit payment initiation based on emails" (91% implemented) |
| BC-2 | Verification must use a contact channel recorded **before** the request arrived (vendor-master snapshot). Any phone, email or link in the request is ignored for verification | Rule on evidence source | AFP 63% "very effective"; Stampli; precisebankflow; CERT-In 0062 "verification source should not be alterable through the same compromised environment" |
| BC-3 | Sender-domain check: sender domain is not the vendor's known domain and the edit distance is ≤2 (lookalike), or there is a new free-mail domain | BLOCK | Pune ₹6.49 cr (one letter); Hyderabad ₹1.5 cr (double "i"); Lulu |
| BC-4 | Penny-drop / name match. `account_status` must be active and `name_match_score` ≥ T_high (e.g. 90) against the vendor's legal name and GST legal name. T_low ≤ score < T_high: ESCALATE. Score < T_low (e.g. 60) or invalid: BLOCK. Validation failed or timed out: ESCALATE | ALLOW / ESCALATE / BLOCK | RazorpayX FAV; RBI name look-up; CERT-In 0046 "penny-drop, name-to-account matching". Thresholds are [D] |
| BC-5 | Bank country ≠ vendor country, or IFSC/bank changes to a foreign or unusual bank | ESCALATE (BLOCK if combined with BC-3) | Hyderabad (China supplier, Polish bank); Vadodara (UAE bank); Wondergate risk tier |
| BC-6 | Contact change and bank change together, or the requester is a new contact never seen before | ESCALATE; a new contact cannot self-verify | Stampli "circular" verification |
| BC-7 | The same beneficiary account appears on more than one vendor, or a vendor has more than 1 bank change in 90 days [D window] | BLOCK / ESCALATE | Wondergate alerts |
| BC-8 | Requester identity: the person named in the request must be verifiable as working at the vendor (Crustdata person/company lookup), and the company must exist with matching name and domain. Unverifiable | ESCALATE | Our differentiator. Supports the "authority for a payment" check in CERT-In 0062 |
| BC-9 | Maker-checker: the actor (agent or human) that applied the change cannot be the approver who activates it or releases the first payment | Enforced | Stampli; Wondergate; NIST SP 800-53; CERT-In 0046 "maker-checker ... for all fund movement" |
| BC-10 | First payment to a changed account is held for a cooling-off period (default 3 business days [D]; practitioners use 1-5) after verification completes, unless two human approvers release it. The hold must not exceed the MSME s.15 deadline; flag "days remaining" | ESCALATE until released | AFP 2026 turnaround-time advice; Cyberwalla 5 days; Wondergate SLA; MSMED s.15 |
| BC-11 | After any change, send a confirmation to the **old** known contact/email and log it | Side effect | Stampli |
| BC-12 | Urgency, discount, secrecy or "revised invoice" language never relaxes a rule. It adds risk-score weight and is logged | Weight only | Wondergate "urgency changes the staffing priority, not the evidence standard"; Hyderabad 2% discount; Sublime 10% discount |

**Invoice / payment**

| ID | Rule | Decision | Source basis |
|---|---|---|---|
| PY-1 | Every payment must reference an existing approved invoice record in our ledger. No record means no payment | BLOCK | CERT-In 0046 "reject reference identifiers with no corresponding records" |
| PY-2 | Idempotency: each invoice gets one payment intent key (vendor_id + normalised invoice no. + amount), and the key is sent to Razorpay/Stripe as the idempotency key. Retries after a crash reuse the key | Exactly-once | Hackathon theme "each invoice paid once, through crashes"; Stripe idempotency keys |
| PY-3 | Duplicate tiers (2.3): exact match, then BLOCK. Fuzzy invoice number (edit distance ≤2 after normalisation) + same vendor + same amount, then ESCALATE. Same vendor + same amount within 90 days, then ESCALATE. Credit-memo-then-reinvoice, then ESCALATE | BLOCK / ESCALATE | Cadel; Medius |
| PY-4 | 2-way / 3-way match. PO + GRN + invoice quantities and prices within tolerance (e.g. ±2% or ₹500 [D]); otherwise ESCALATE. Non-PO invoice above ₹X, then ESCALATE | ESCALATE | Standard P2P control; Finto/Mod AI list 3-way match as core |
| PY-5 | Amount thresholds: above a per-transaction limit, require human senior approval; per-day cumulative ceiling per vendor and in total; velocity limit on new beneficiaries | ESCALATE / BLOCK | AFP senior sign-off (94% implemented); CERT-In 0046 ceilings and velocity |
| PY-6 | Payee on the invoice ≠ payee on the vendor master: never pay to the invoice's bank details. Pay only to the verified master record and treat a mismatch as BC-1 | ESCALATE | Stampli "invoice-derived payment details differ" signal; Pune case |
| PY-7 | GSTIN must be active, its PAN must match the vendor PAN, and the legal name must fuzzy-match the vendor. If e-invoicing applies to the vendor, a valid IRN/QR must be present | ESCALATE | GST rules; GSTN 30-day advisory |
| PY-8 | Unverifiable is never ALLOW. Any check that errors, times out or returns ambiguous data yields ESCALATE, with the failed check named | ESCALATE | Gate design; Razorpay "failed" status |
| PY-9 | The approval UI must show old vs new bank account (full IFSC + account, not truncated) and the matched invoice pair side by side | UI requirement | Pune case: "the online ledger ... had only the first few letters of its name and the account number"; Wondergate |

**AI / agent safety**

| ID | Rule | Source basis |
|---|---|---|
| AI-1 | Sanitise inputs before the LLM sees them: strip hidden HTML (zero-size, white-on-white, aria-hidden spans) and Unicode Tag characters U+E0000-U+E007F. Log that hidden content was found as a risk signal (it means ESCALATE) | Sublime Oct 2026 campaign |
| AI-2 | The LLM only extracts claims into a typed schema. It never decides and never calls payment tools. Deterministic code applies policy to claims plus independently fetched facts | CERT-In 0049/0062 on agent misuse; Bean Counters quote: "No app is building the perfect AI agent process ... we've gotta make sure we've got checks in there too" (Eftsure blog) |
| AI-3 | Tone robustness: an extracted "urgency", "authority claim" or "discount" is a feature, never an override (see BC-12). Test with polite, urgent, threatening and executive-voice variants | AFP 2026; Eftsure survey: only 25% feel comfortable questioning a senior exec |

**Audit / replay**

| ID | Rule | Source basis |
|---|---|---|
| AU-1 | Append-only decision log per action. Each record holds: input hash, extracted claims, every external check (request, response, timestamp, source), policy version + rule IDs fired, decision, approver identity, payment idempotency key and provider ID | Stampli audit-evidence list; RBI name-lookup log requirement; CERT-In 0046 ≥180-day log retention |
| AU-2 | Replay: re-running the same log with the same policy version reproduces the same decision. Hash-chain the log entries | Hackathon brief "books an auditor can replay line by line" |
| AU-3 | Incident playbook: on BLOCK for suspected fraud, show the 1930 / NCRP / CERT-In 6-hour reporting steps | CERT-In 0062; Dr Reddy's recovery |

---

## 3. Competitors and products

### 3.1 Landscape (what they do)

| Category | Product | What it does | Pricing (public?) | Source |
|---|---|---|---|---|
| Payment-assurance / bank verification | **Eftsure** (AU/US/NZ, merged with Sis ID in France 2025) | Verifies supplier identity and bank account against a network of 6M-11M+ businesses. Supplier attestation plus **human phone callbacks**. Traffic-light alerts at payment time. Up to $1M guarantee. A$373B in payments protected a year. Suppliers not in the database take 1-3 weeks | Contact sales | https://eftsure.com/en-au/blog/products/best-ap-fraud-prevention-platforms-for-enterprise-teams ; https://relishiq.com/blog/supplier-bank-account-verification-tools/ |
| | **Trustpair** (France) | Data-source bank-account validation before each payment. 20+ ERP connectors. US automation about 80% vs 95%+ in the EU. Validates the account, not the supplier identity | Enterprise | relishiq; eftsure |
| | **Relish Data Assure** | Embedded in SAP/Coupa/Workday/Ariba. Bank, tax ID, sanctions. Fallbacks: bank docs, then open banking, then a call centre. Flags a bank country that differs from the supplier country | Enterprise | relishiq |
| | **PaymentWorks** | Payee identity network (US higher-ed and government), $2M indemnity | Enterprise | relishiq |
| | **apexanalytix** | Supplier master integrity, 280M records, recovery audit | Enterprise | relishiq |
| Behavioural overlay | **Trustmi** (NY/Tel Aviv, founded 2021) | Behavioural AI correlating email, vendor records, invoices and payments. Pre-release verdict. Nacha Preferred Partner. Claims $240B secured. Does not govern master data | Contact sales | https://trustmi.ai/2026-benchmark-payment-security-report/ ; https://nacha.org/news/trustmi-now-nacha-preferred-partner-risk-and-fraud-prevention-fraud-monitoring-and-account |
| Email security | **Abnormal (VendorBase)** | Federated vendor reputation. Raises vendor risk when a vendor mailbox is compromised | Enterprise | https://abnormal.ai/resources/data-sheets/vendorbase-security-email-supply-chain |
| | **Sublime Security** | Email security, including detection of prompt injection aimed at AI agents | Enterprise/free tier | sublime.security |
| | Proofpoint, Mimecast | Secure email gateways with BEC detection | Enterprise | (not fetched) |
| AP suites | **Medius** | AP automation plus a fraud and risk module, duplicate detection | Enterprise | medius.com |
| | **Tipalti** | End-to-end AP plus global payouts | From **$99/mo** (AP), $249/mo mass payments | https://tipalti.com/pricing/ ; bill.com blog |
| | **BILL** | SMB AP/AR | **$49 / $65 / $89 per user/mo**; ACH $0.59 | https://g2.com/products/bill-com/pricing ; layer3labs |
| | **Stampli** | AP with bank-change holds and signals | Quote | stampli.com |
| | Coupa, AppZen, Vic.ai, Ramp/Brex bill pay | P2P / AI audit / AI AP / card+bills | Mixed | (not fetched in detail) |
| India | **Peakflo** | AP automation. Vendor onboarding portal, **penny-drop verification (India only)**, GSTIN/PAN/MSME validation, AI-flagged bank detail changes, duplicate detection | Quote | https://help.peakflo.co/how-to-verify-vendor-bank-account-numbers ; https://peakflo.co/accounts-payable/vendor-onboarding-management |
| | **Zoho Books (India)** | Accounting from **₹749/org/month** (billed annually). Marketplace add-on "Indian Bank Verification for Zoho Books" (up to 1,000 checks/month). Note: "Vendor payments cannot be approved in Zoho Books" (it relies on bank approval workflows) | ₹749+/mo | https://zoho.com/in/books/pricing ; https://marketplace.zoho.com/app/books/bank-verification-for-zoho-books ; https://www.zoho.com/in/books/kb/payments/approving-vendor-payments.html |
| | **RazorpayX** | Payout rails plus Fund Account Validation (penny-drop/penniless, name_match_score) | Per-validation fee (not captured) | Razorpay docs |
| | Cashfree, Open Money, Volopay, Kapittx, Tally, Fyle | Payouts, AP and spend tools; Tally is the SME ledger | Mixed | (not fetched; Peakflo/Zoho/Razorpay are the verified examples) |
| Agentic AP (YC) | **Mod AI / Clerked** (Launch YC, Oct 14 2025) | AI agents running AP end-to-end: capture, GL coding at 97%+, 2/3-way match, "fraud detection" | n/a | https://www.ycombinator.com/launches/Obu-mod-ai-automating-accounts-payable-with-ai-agents |
| | **Finto** | "AI Accounting for Enterprises": checks vendor, tax, bank and compliance data, emails vendors, 3-way match | n/a | https://ycombinator.com/launches/Nxn-finto-ai-accounting-for-enterprises |
| | **Lighthouz AI** | AP/AR for freight brokers: duplicate and overbilling detection | n/a | https://ycombinator.com/launches/P41-lighthouz-ai-ai-to-automate-ap-and-ar-for-freight-brokers-and-3pls |
| | Saldor, FullSeam; Fazeshift, Alder, Rex (AR side) | Procurement+AP; F&A agents | n/a | YC launch pages (crawl dates Nov 2026) |

### 3.2 The gap our gate fills (hedged: "not publicly advertised" ≠ "doesn't exist")
1. **Indian SME price point plus an agentic workflow.**
   - Eftsure, Trustmi, Trustpair and Relish are enterprise, contact-sales products focused on the US, EU and ANZ.
   - Indian tools (Peakflo, Zoho add-on, RazorpayX) do penny-drop at onboarding. None of the public docs I read describe a **gate that intercepts an email-initiated bank-change request**, freezes payments, and walks it through a callback, a cooling-off period and maker-checker as one decision.
   - The Pune ₹6.49 cr victim's bank *did* call, and the human still said "proceed." The missing piece was a control that compares the new account against the master record and refuses.
2. **Verifying the requester, not only the account.**
   - Bank verification tools confirm "this account belongs to Vendor X Pvt Ltd". RelishIQ: "Account verification ... cannot prove that the authorized supplier contact requested the change"; Wondergate says the same.
   - Our check adds: does the person emailing exist, and do they work at Vendor X (Crustdata person/company lookup)? Is the sender domain the vendor's real domain (live web)? That is the "authority for a payment" CERT-In 0062 asks for.
3. **Replayable, deterministic audit log.**
   - Competitors advertise "audit trails". None I read advertise **replay**: re-running the logged inputs with a pinned policy version to reproduce the same decision, with hash-chained evidence.
   - That is the hackathon's exact ask ("books an auditor can replay line by line").
4. **Robustness to LLM manipulation.**
   - Agentic AP startups (Mod AI, Finto) put an LLM in the loop. In-the-wild prompt injection targeting AP agents is now documented (Sublime, Oct 2026), and CERT-In warned on Oct 15 and Nov 20 2026 about AI agents as attack vectors.
   - Our design keeps the LLM limited to claims extraction and lets deterministic code decide. That is a defensible differentiator.
5. **Exactly-once payments through crashes.**
   - Idempotency keys plus a ledger state machine. AP suites rarely market this. The theme demands it.
6. **An explicit "unverifiable means ESCALATE" contract with the MSME deadline surfaced.** This is India-specific.

### 3.3 Crustdata live competitor data (retrieved 2026-11-22)
Retrieval:
- Calls: `POST /company/enrich` with `{"domains":[...], "exact_match": true, "fields": ["basic_info","headcount","funding","locations"]}`. All 13 matched with confidence 1.0.
- The Crustdata IDs are saved so the team can re-query.
- Raw JSON is in `C:\Users\KRISHN~1\AppData\Local\Temp\claude\b77e92e8eba051cd\87a25b9a-52cf-454f-a2e7-9aac94327d7c\scratchpad\cd_out\`.
- Funding fields come from Crustdata's Crunchbase-derived data. Several look stale or incomplete (flagged in the table). Treat them as [S, Crustdata] and do not quote them without a cross-check.

Notes on columns:
- "India HC" sums Crustdata `headcount.by_region_absolute` entries that mention India or Indian cities. Region buckets can overlap, so this number is approximate.
- "Jobs since Jul 1 2026" is `total_count` from `/job/search` filtered on company_id and `metadata.date_added >= 2026-07-01`.

| Company (Crustdata ID) | Founded | HQ | Headcount (largest country) | HC growth YoY | Total funding (last round, date) | India HC (approx.) | Jobs since Jul 1 2026 | Hiring signal (sample of latest 8 postings) |
|---|---|---|---|---|---|---|---|---|
| Trustmi (1063180) | 2021 | New York | 63 (ISR) | +5.0% (6m: -3.1%) | $21.0M (Series A $17M, 2023-07-26; Cyberstarts, Zeev) | 0 | 2 | Fraud Data Analyst (Ukraine), Senior SDR (US). Small, stable team |
| Eftsure (824927) | 2014 | Dallas (AU origin) | 307 (AUS) | +18.1% | Crustdata shows $3.2M / Series B 2019, which is **stale or incomplete**. It also lists "acquired_by Level Equity" | 0 | 44 | AEs in Lyon (Benelux, SAP, Germany): Sis ID merger and Europe push. Sydney AE. Dallas SDR + General Counsel (US build-out) |
| Trustpair (675447) | 2017 | Paris | 127 (FRA) | **+23.3%** | $31.1M (Series B $19.7M, 2022-10-03). Crustdata lists acquired_by **Basware** (unverified) | 0 | 25 | US enterprise AEs/SDRs in New York, Head of Fraud Operations (Paris). US expansion |
| Abnormal AI (631899) | 2018 | Las Vegas | 1,620 (USA) | +16.3% | $534M (Series D $250M, 2024-08-06) | ~450 | **178** | EU SDRs (Dutch, German), enterprise sales Sweden. Scaling go-to-market |
| AppZen (642676) | 2012 | Santa Clara | 371 (**IND**) | -3.6% | $280.6M (Series D $180M, 2025-09-22) | ~553 | 30 | T&E spend-management PMs. Pune professional services and Oracle consultants. India is its delivery base |
| Medius (820650) | 2001 | Linköping, SE | 965 (USA) | +4.6% | PE-owned (August Equity, Marlin). Crustdata funding figure not meaningful | 0 | 34 | "Product Marketer - Accounts Payable Automation" (US), BDRs, Tunisia delivery |
| Tipalti (631330) | 2010 | San Mateo | 1,084 (ISR) | **-12.2%** | $915M (PE $200M; Crustdata date 2026-01-01 may be a placeholder) | 0 | 76 | Heavy **security** hiring (AppSec, Product Security, SecOps in Tel Aviv and London) |
| Stampli (632990) | 2015 | Mountain View | 311 (USA) | +9.1% | $145.7M (Series D $61M, 2023-10-03) | 0 | 45 | **"Head of AI-Native Engineering (Senior Director)"**, Senior Data Scientist (Tel Aviv), Directors of Partnerships |
| Vic.ai (633861) | 2017 | New York | 94 (USA) | -7.8% | $114.7M (Series C $52M, 2022-12-13) | 0 | 16 | Technical CS, Solutions Architects (US). Implementation-heavy |
| Peakflo, YC W22 (689949) | 2021 | San Francisco (India team) | 34 (IND) | +6.2% | $5.1M (Seed $4.1M, 2022-07-05) | ~48 | 5 | India-remote Enterprise Delivery Manager, interns |
| Volopay (6124282) | 2020 | Singapore | 126 (IND) | -4.5% | $31.3M (Series A $29M, 2022-02-28) | ~208 | 4 | All Bengaluru: AE, US-pod SDR, SEO. India-built, selling outward |
| Open Financial Technologies / Open Money (5934) | 2017 | Bengaluru | 393 (IND) | **-13.6%** | $190.8M (Series D $50M, 2022-05-02) | ~1,367 (overlapping buckets) | 0 | No postings indexed since Jul 2026 |
| Kapittx (1061629) | 2019 | Pune | 20 (IND) | +17.6% | $0.2M (pre-seed, 2022-06-14) | ~57 (overlap) | 0 | Positioned on **AR** automation and B2B payments, not AP fraud |

Takeaways for the pitch:
- The specialist payment-assurance players are small and enterprise-focused, with **zero India headcount**: Trustmi (63 people), Trustpair (127), Eftsure (307).
- Their hiring points to Europe and US expansion (Eftsure's Lyon AEs after the Sis ID merger; Trustpair's NYC AEs), not India.
- India-heavy AP and spend players are either shrinking or not hiring: Open Money at -13.6% with 0 recent postings, Volopay at -4.5%. Peakflo is tiny (34). None of them is a dedicated bank-change and payment-gate product.
- That leaves the **India SME payment-verification gate** uncontested in the live data.
- Incumbents are signalling AI and security investment: Stampli's "Head of AI-Native Engineering", and Tipalti's security hiring wave. This backs the trend that AP is becoming agentic and that the attack surface matters.

**Crustdata web search (`/web/search/live`, 1 credit per page, retrieved 2026-11-22)** corroborated:
- RBI FY26: ₹48,021 crore across 10,114 cases (ABP Live: https://www.abplive.com/news/banks-report-48021-crore-rupees-fraud-in-10114-cases-during-fy26-says-rbi-report-3137187 ; Business Standard Hindi: https://hindi.business-standard.com/finance/rbi-report-bank-fraud-amount-hits-3-year-high-as-cases-drop-id-527948/).
- CERT-In CIAD-2026-0062 (Nov 20 2026), with several posts. One snippet mentions "Reuters coverage", which I have not verified.
- Funding context: Visa agreed to buy BioCatch for $2.4B; Overwatch raised $15M (AI-fraud); Freehand raised $75M for supply-chain AI agents (Forbes, Jul 29 2026: https://www.forbes.com/sites/davidprosser/2026/07/29/freehand-raises-75-million-as-its-ai-agents-target-the-supply-chain/). These are headline-only [S].
- Two news-source queries returned 0 results at 0 credits. The Indian BEC web query surfaced only social posts, including an unverified "Mumbai company lost ₹10.4 crore" claim. TinyFish/TOI remains the better source for Indian cases.

**Crustdata credit log** (from the X-Credits-Used header):
- `/company/enrich`: 13 successful calls × 2 = **26.0**. Eight early calls returned HTTP 429 (rate limit of 5 rpm) and were retried with spacing. The helper showed a stale header value on the 429s, so I treat them as uncharged; verify on the dashboard.
- `/job/search`: 9 × 0.24 + 0.15 + 0.06 + 0.12 + 2 × 0 = **2.49**.
- `/web/search/live`: 4 × 1 + 2 × 0 = **4.0**.
- `/account/endpoints` (field discovery): free.
- **Total ≈ 32.5 credits** of the 80 budget. `/company/identify` was not needed because domains were known and enrich matched them with confidence 1.0.

---

## 4. AI-in-AP trends and AI-enabled payment fraud (2024-2026)

**Deepfakes**
- **Arup, Hong Kong (Jan 2024, named May 2024).** An employee joined a video call where the CFO and other colleagues were deepfakes, then made 15 transfers totalling HK$200M (about US$25.6M) to 5 accounts.
  - Sources: https://cnn.com/2024/05/16/tech/arup-deepfake-scam-loss-hong-kong-intl-hnk ; https://fortune.com/europe/2024/05/17/arup-deepfake-fraud-scam-victim-hong-kong-25-million-cfo [V-headline/snippet]
  - The lesson for our gate: a voice or video "approval" is not a verification channel. Only callbacks to records on file count, plus maker-checker.

**FBI IC3 2025**
- First AI section: 22,364 complaints, about $893M [V].
- More than $30M of 2025 BEC losses involved AI (Forbes) [S].

**AFP surveys**
- 2026: deepfake attempts at 7% of organisations, and 13% among large firms with 100+ accounts [V].
- 2025: 5% [V].
- 2026: only 17% use AI for fraud prevention [V].

**Prompt injection against AP agents**
- Sublime, Oct 22 2026. Invoice-fraud emails carried hidden instructions in 1px, white, aria-hidden spans and in Unicode Tag characters. The instructions told an email-reading AI agent to forward the invoice to an AP inbox.
- The emails also impersonated the target's CEO in a fake three-message thread, with a 10% discount expiring soon, on invoices of about $88k.
- Sublime found that models varied widely: some missed the hidden text, others flagged it.
- I am deliberately not reproducing the injected instruction text here [passage omitted].
- Source: https://sublime.security/blog/invoice-fraud-campaign-adds-prompt-injection-aimed-at-email-ai-agents [V]
- Related research on invoice-record injection: https://vernolabs.ai/research/wrong-tool-or-wrong-value-inside-two-kinds-of-prompt-injection ; https://tasksheriff.com/blog/prompt-injection-invoices-accounts-payable [S]

**CERT-In**
- CIAD-2026-0049 (Oct 15 2026): "AI Agents as Attack Vectors: Unauthorized Access by Agents under Evaluation and Misuse of Open-Source Agentic AI Tools" [V-title].
- CIAD-2026-0062 (Nov 20 2026): agentic offensive frameworks used alongside payment-workflow abuse [V].

**Other trend data**
- Microsoft counted about 10.7M BEC attacks in Q1 2026 (via Stingrai) [S].
- APWG/Fortra: the average requested BEC wire was $61,732 in Q2 2026, up 45% [S].
- Eftsure AU survey 2026: 90% think AI scams are harder to detect, only 25% feel comfortable questioning a senior executive's payment request, and 32% feel pressure to pay quickly [E, vendor survey].

**Agentic AP startups (YC)**
- Mod AI/Clerked, Finto, Lighthouz, Saldor and FullSeam.
- The category is moving from OCR + workflow to "AI clerk end-to-end," which increases the need for an independent gate before irreversible actions.

---

## 5. Caveats
- The IC3 2025 BEC line item ($3.05B) comes from Stingrai's page-cited summary. Pull it from the IC3 PDF (https://www.ic3.gov/AnnualReport/Reports) before putting it on a slide, if time permits.
- RBI fraud figures cover banks (mostly loan fraud) and are not corporate BEC. I4C figures are citizen cyber fraud. India has **no official corporate-BEC loss statistic** that I could find. Say this honestly in the pitch and lean on the news cases plus CERT-In 0062.
- Duplicate-payment rates are industry folklore with weak primary sourcing (APQC values are paywalled). Present them as "industry benchmarks 0.1-0.5% of spend [vendor-cited]".
- The market-size numbers (IMARC, Grand View) are paid-report estimates.
- The thresholds in section 2.5 marked [D] are our design choices, informed by practice. Present them as configurable policy, not as an industry standard.
