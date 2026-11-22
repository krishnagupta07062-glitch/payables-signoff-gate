> Real people's names and profile URLs in this report are replaced with labels (Person A, B, ...). Company names are kept. Raw API responses are not in the repo.

# Research 5 — Crustdata API for the payables Sign-Off Gate

Date of research: 2026-11-22. API version `2025-11-01`, base `https://api.crustdata.com`, headers `Authorization: Bearer <key>`, `x-api-version: 2025-11-01`, `Content-Type: application/json`.
All real calls were made from a logging helper (`scratchpad/cdcall.py`). Every raw request and response is saved in `scratchpad/calls/<name>.json`, with status, `X-Credits-Used` and latency. The key is not in any file.

**Credits spent by this agent: 36.95** (the sum of `X-Credits-Used` over 50 billed calls; the budget was 300). The account balance fell from 15199.77 to 15089.94 during the session. Other agents share the key, and `/account/usage/summary` shows their calls too (for example 51 web searches). So the balance drop is larger than my spend.

---

## 0. TL;DR — verification recipe

| Gate question | Best call (cost) | What answers it | Fallback / "can't verify" rule |
|---|---|---|---|
| Q1a Is the vendor a real company in the index? | `POST /company/identify {"domains":[sender_domain]}` (0.2 if matched, **free if unmatched**) | `matches[].company_data.crustdata_company_id`, `basic_info.name`, `primary_domain`, `all_domains`, `employee_count_range`, `year_founded`, `company_type` | `matches: []` → "Vendor domain not in Crustdata: cannot verify". |
| Q1b Is the sender domain the vendor's real domain? | Same identify call, plus a local check | The input domain must be **in `basic_info.all_domains` or equal `primary_domain`** of the record that the invoice names. | `confidence_score` 1.0 is **not** proof. `superhouse.in` returned "Design Edge Media" at 1.0 with no superhouse domain at all. Reject a match unless the domain is in `all_domains`. |
| Q1c Is the vendor active / alive *today*? | `POST /company/search` with `metadata.updated_at` in fields (0.03/result) + `POST /web/enrich/live` on the domain (1/page) | `basic_info.status` (`active`/`deleted`), `metadata.updated_at`, `headcount.timeseries[-1].date`. Live fetch: `http_status`, page title/text | Real case: `wleltd.com` shows `status: active` and `updated_at 2026-11-13` in the index, but the live fetch shows **"wleltd.com has expired"**. Index "active" ≠ alive. Always live-check the domain. |
| Q2 Does the named sender work there now, in the claimed role, and since when? | `POST /person/search` with name `(.)` + `experience.employment_details.company_id = <vendor id>` (all roles), returning current+past (**0.23/result**) | `current[].title`, `current[].start_date`, `current[].crustdata_company_id`; `past[].title`, `past[].start_date`, `past[].end_date`; `metadata.updated_at` | `total_count: 0` → "No such person at vendor in index: cannot verify". The sender may also appear only in `past[]`; that is the departure flag. |
| Q2b Did they recently leave? (departed-employee vector) | Same search. To list all recent leavers: `all_of` group on `experience.employment_details.company_id` + `experience.employment_details.end_date => <date>` (0.23/result) | `past[]` entry at vendor with `end_date`; `current: []` or a different employer; `experience.recently_changed_jobs` (true if the role ended ≤90 days before index rebuild) | Real cases: Person A (Bata CFO 2021-01 → 2022-11, now Eicher). Person D (Bata Head Finance Shared Services, ended 2026-10, no current employer). Person B (Bata India interim CFO 2024-12, now at **parent** Bata Group). |
| Q2c Who is the real CFO, to compare? | `POST /company/enrich {"crustdata_company_ids":[id],"fields":["people"]}` (2) **or** person search current company_id + title (0.23/result) **or** `POST /agent/searches` (0.36 in test; 0 if no match) | `people.cxos[]` / `people.decision_makers[]`, each with `experience.employment_details.current[].employee_title/employee_start_date` and per-person `updated_at` | `people.cxos` contains **stale and self-claimed** entries: the ex-CEO Person E is still "current" with `updated_at` 2025-02-14, and a store manager is listed as "Chief Executive Officer". Use person search (fresher) and drop people whose `updated_at` is older than N days. |
| Q3 Recent news (acquisition, rebrand, bank change, fraud warning)? | `POST /company/enrich` fields `["news","funding"]` (2, indexed) + `POST /web/search/live {"sources":["news"]}` (1/page, live) | enrich `news[]`: `article_title`, `article_url`, `article_publish_date`, `publisher_domain`, `confidence_score`; `funding.acquisitions[]`, `funding.acquired_by[]`. Web search: `results[].title/url/snippet` + top-level `timestamp` (ms) | Web-search results have **no date field**. Dates appear only inside the snippet, and are localised to Hindi when `location:"IN"`. Enrich news has a real `article_publish_date`. For SMEs, `news: []` → "No news found" (not "no risk"). |
| Q4 Is the invoice name/address consistent with the canonical record? | identify by `names` (0.2) for name variants; enrich `locations` (2) | `basic_info.name`; `locations.street_address`, `headquarters`, `city`, `state`, `country` (ISO-3) | Name lookups always return up to 25 candidates (a fake "Acme Leather Exports Pvt Ltd" still returned 0.6 matches and was billed 0.2). Treat <0.8 as no match. Normalise "Ltd"→"Limited": "Bata India Ltd" scored 0.6, while "Bata India Limited" scored 1.0. SME addresses are often just "Gurgaon, Haryana, India" or a long string of geocoded localities. |
| Q4b One company under two names | Look up both `zomato.com` and `eternal.com`; search `basic_info.primary_domain in [...]` | Zomato (id 6162764) and Eternal (id 6775477) are **two separate records** with no link field. `all_domains` of acquired companies point to the acquirer (Urbanspoon, TongueStun, Cibando all list `zomato.com`) | The gate must keep its own alias table (rebrands, parent/subsidiary such as Bata India 573 vs Bata Group 1135086, city shards such as "Mirza International Limited, Kanpur, Up"). |
| Bank-change / fraud posts | `POST /social_post/search` (0.5/post; `limit:0` gives a free count) | `posts[].text`, `date_posted`, `share_url`, `actor.crustdata_entity_id` | `(.)` is fuzzy. "Bata" matched the Hindi word "bata" (tell). Use `[.]` and author filters. The newest Bata post in the index was 2026-09-02, so expect a lag of up to 45 days. |
| Hiring signal | `POST /job/search` filter `company.basic_info.company_id` (0.03/job, empty is free) | `job_details.title/url/source`, `metadata.date_added/date_updated` | Bata had 0 jobs since 2026-09-01; the latest was 2026-07-27. Weak signal for SMEs. |

**Cheapest full check per invoice (large vendor):** identify domain 0.2, then person search for the sender at the vendor 0.23, then enrich news+people 2, then one live web news search 1, then a live fetch of the vendor homepage 1. Total ≈ **4.4 credits**. A minimal check (identify + person search) is ≈ **0.45 credits**. Unmatched identify/enrich/person-enrich rows are free. Empty search/web/agent results are free.

---

## 1. Field → gate-check table (usable fields on this account)

Legend: CI = /company/identify, CE = /company/enrich, CS = /company/search, PS = /person/search, PE = /person/enrich, PI = /person/identify, JS = /job/search, SP = /social_post/search, WS = /web/search/live, WE = /web/enrich/live, AG = agent search.

| Gate check | Field(s) | Endpoint(s) | Notes / freshness |
|---|---|---|---|
| Vendor real (entity resolution) | `crustdata_company_id`, `basic_info.name`, `basic_info.profile_name`, `basic_info.professional_network_url`/`_id`, `basic_info.year_founded`, `basic_info.company_type`, `basic_info.description` | CI, CE, CS | CI is the cheapest (0.2). Use the id as the canonical record key. |
| Vendor active | `basic_info.status` (`active`/`deleted`) | CE, CS | Search also returns `metadata.updated_at` and `metadata.indexed_at` (CE returned these as **null** even when requested). |
| Vendor alive *today* | WE `http_status`, `title`, `content`, `timestamp` (s) | WE | Parked or expired domain = red flag. `success:true` even on 403, so check `http_status`. |
| Domain match | `basic_info.primary_domain`, `basic_info.all_domains`, `basic_info.website` | CI, CE, CS | `all_domains` is noisy (Bata Indonesia lists 9 unrelated domains). Match with an exact set check, not substrings. Person-side filter: `experience.employment_details.current.company_website_domain` / `company_domains`. |
| Domain lookalike | identify on the lookalike returns `matches: []` (free) | CI | `bata-india.co` and `acmeleather.in` → no match → "unknown domain". |
| Sender identity | `basic_profile.name`, `headline`, `current_title`, `normalized_title.matched_title`, `basic_profile.location`, `social_handles.professional_network_identifier.profile_url`, `crustdata_person_id` | PS, PE, PI | Name filter `(.)` is all-words fuzzy. Disambiguate by the employer id. |
| Sender current employer & role | `experience.employment_details.current[]`: `name`, `crustdata_company_id` (returned; filter alias `company_id`), `title`, `seniority_level`, `function_category`, `is_default`, `employment_type`, `company_website_domain` (PE), `company_status` | PS, PE | Multiple current roles are possible. Use `is_default`. Unlinked employers have `crustdata_company_id: 0` (PS) or `null` (PE). |
| Role start date / tenure | `current[].start_date`, `years_at_company_raw` | PS, PE | Month precision (`YYYY-MM-01`). |
| Recently departed | `past[]`: `name`, `crustdata_company_id`, `title`, `start_date`, `end_date`; `experience.recently_changed_jobs` (PS only) | PS, PE | `past.end_date` is **not filterable**. Use `experience.employment_details.end_date` inside an `all_of` group with `company_id`. |
| Record freshness | PS `metadata.updated_at`; PE/PI `updated_at`; CE `people.*[].updated_at`, `basic_profile.last_updated` (inside people); CS `metadata.updated_at`/`indexed_at`; JS `metadata.date_added`/`date_updated`; SP `date_posted`; WS `timestamp` (ms); WE `timestamp` (s); CE headcount `timeseries[].date`, revenue `timeseries[].date` | all | Index refresh is 1–30 days (posts 1–45). Per-section `*.last_updated` fields are **disabled** on this account. |
| Headcount vs invoice size | `headcount.total`, `headcount.timeseries`, `growth_percent.{mom,qoq,six_months,yoy,two_years}`, `by_role_absolute.Accounting`; `basic_info.employee_count_range`; `revenue.estimated.lower/upper_bound_usd` (+timeseries) | CE (headcount is free inside the 2 cr), CS (premium 0.2) | CS uses keys `1m/3m/6m/12m`. Ranges can be inconsistent: Zomato `headcount.total` 26474 vs range "1001-5000". Bata revenue band is "1e9–1e12 USD" (useless). SME: True Trident Leather shows headcount 1 and revenue band 1–2.5M USD. |
| Address consistency | `locations.street_address`, `headquarters`, `city`, `state`, `country` (ISO-3 in CE, full name in CS), `all_office_addresses` | CE, CS (not CI: disabled) | HQ only. Usually empty `all_office_addresses`. Eternal's record has all-null locations. |
| Contact channel cross-check | `basic_info.description` (often contains official support emails), `funding.contact_email`, `funding.phone_number`, `basic_info.contact_email/phone_number` | CE | Useful for "call back on the number on file". Eternal record `funding.contact_email = order@zomato.com`. |
| News / rebrand / leadership change | `news[].article_title/url/publish_date/publisher_domain/source/confidence_score` | CE | Bata: 100 articles, newest 2026-11-09 (CEO change, new marketing head). Eternal: 63, Zomato: 100. SMEs: 0. |
| Acquisition / parent | `funding.acquisitions[]` (`acquirer_*`, `acquiree_*`, `announced_on_date`), `funding.acquired_by[]`, `revenue.acquisition_status`, `revenue.public_markets.stock_symbols/ipo_date` | CE, CS | Zomato `acquired_by` shows Talabat 2019 (that is Zomato *selling* to Talabat, so the data is messy). |
| Funding / financial distress | `funding.total_investment_usd`, `last_fundraise_date`, `last_round_type`, `investors`, `milestones`; `headcount.growth_*` (shrinking), `followers.*` | CE, CS | No credit-rating or insolvency fields. Use news + web search for distress. |
| Hiring signals | JS `job_details.*`, `metadata.date_added`; CE `hiring.openings_count` (null in tests; `hiring.recent_openings` disabled) | JS | Large vendors only. |
| Social posts announcing changes | SP `text`, `date_posted`, `share_url`, `actor.*`, `mentions.company_id/person_id` | SP | CE/PE `social_posts` add-ons are **disabled**. |
| AI-assisted cross-check | AG `output.<entity>.rows[].values`, `rows[].constraints[].assessment/evidence`, `output.note`, `output.reason` (`no_match`) | AG | Gives evidence text. Not deterministic. Use it for a second opinion only. |
| Authenticity score | `assessment.authenticity.verdict/tier` | PE | **Disabled** (403 `Access denied to fields: assessment`). |

**Useless or low-value for the gate:** `dev_platform_profiles.*`, `research_profiles.*`, `education.*`, `skills.*`, `certifications/honors`, `seo.*`, `web_traffic.*`, `competitors.*`, `software_reviews.*`, `public_launches.*`, `market_intel.*`, `employee_reviews.*` (except as a weak "real company" signal), `followers.*` (except as a weak liveness signal), `taxonomy.*` (only to check that the industry fits the invoice line items), `logo_permalink`, `profile_picture_*`, `profile_ranking`, `fit`, `/person/identify` (by URL it adds nothing over enrich at the same 1 cr; **email lookup is disabled** on this account).

---

## 2. Docs notes (from docs.crustdata.com `.md` pages)

Fetched with curl from `https://docs.crustdata.com/<page>.md`. `llms.txt` indexes them all.

- **Freshness** (`general/data-updates`): indexed person and company profiles are refreshed every 1–30 days, posts every 1–45 days. "Each record carries an `updated_at`". Live endpoints (`/person/professional_network/enrich/live`, company live search) are enterprise-only and **not enabled** here. Watchers can keep 1–30-day freshness (5–150 cr per changed entity). `recently_changed_jobs` means the previous role ended within 90 days of the last index rebuild.
- **Company identify** (0.2 per *matched* identifier, unmatched free, ≤25 per request): send exactly one of `domains`, `names`, `professional_network_profile_urls`, `crustdata_company_ids`, plus optional `exact_match` (no observable effect in tests). The response is a top-level array `[{matched_on, match_type, matches:[{confidence_score, company_data:{crustdata_company_id, basic_info}}]}]`.
- **Company enrich** (2 per **matched record**): the same identifiers, plus `fields` (section groups: `basic_info, headcount, funding, locations, taxonomy, revenue, hiring, followers, seo, competitors, social_profiles, web_traffic, employee_reviews, people, news, software_reviews, public_launches, market_intel, technographics, social_posts, reviews`). The default is `basic_info` only. No match → `200` with `matches: []`. Handle `404` too.
- **Person search** (0.03 per result; **premium group `experience` +0.1 to filter and +0.1 to return**, so a typical sender check is 0.23/result). Body: `filters` (`{field,type,value}` or `{op:"and"|"or"|"all_of", conditions:[...]}`), `fields`, `sorts:[{field,order}]`, `limit` 1–1000 (default 20), `cursor` (from `next_cursor`), `post_processing.exclude_profiles/exclude_names`, `explain:true` (names the condition that emptied the result). Operators: `= != < =< > => in not_in is_null is_not_null has_all (.) (!) [.] geo_distance geo_exclude geo_polygon` (use `=>`/`=<`, never `>=`/`<=`). `all_of` makes every condition match the **same** array element (same role). Filter paths differ from returned paths: filter `current.company_id` but read `current.crustdata_company_id`; filter `current.company_website_domain` but read `current.company_website`. Seniority enum: `CXO`, `Vice President`, `Director`, ... ("CFO" is not a seniority).
- **Person enrich** (1 per matched profile; unmatched and `redacted` free; ≤25 URLs): `professional_network_profile_urls` + `fields`. `match_status` is `matched`/`not_found`/`redacted`. Default fields are `basic_profile` + `social_handles` only, so **request `experience` explicitly**.
- **Person identify** (1 per match): `professional_network_profile_urls` | `emails` | `research_profile_urls`. The docs warn that email matching falls back to *name-in-address at the domain owner* (confidence 0.5–1.0). That would "verify" a spoofed `firstname.lastname@realdomain`. Moot here: **`emails` is disabled on this account** (403).
- **Web search live** (1 per page; `page:N` costs N): `query` (≤5000 chars, supports `site:`), `sources` from `web, news, scholar-articles, scholar-articles-enriched, scholar-author, ai, social`, `location` (ISO-2), `site`, `start_date`/`end_date` (unix **seconds**), `human_mode`, `page` (1–15; >1 needs exactly one source). Response: `{success, query, timestamp (ms), results:[{source,title,url,snippet,position}], metadata:{total_results, failed_pages, empty_pages}}`. The `ai` source returns `content` + `references`.
- **Web enrich live** (`/web/enrich/live`, 1 per page, ≤10 URLs, 10 rpm): `urls`, `human_mode`. Response array `[{success, url, timestamp (s), title, content (full HTML), http_status}]`.
- **Agent search** (beta). The routes are `POST /agent/searches` (start, free, returns 202 + `search_id`), `GET /agent/searches/{id}` (poll; charged once at the end), `/events`, `/cancel`. Billed under the permission path **`/agent/query`** (base 0.012 + data_search 0.0005 + data_enrich 0.05 + contacts). `POST /agent/query` itself returns **404**. A start needs an 8-credit balance per unbilled search. No match / failed / cancelled = 0 credits.
- **Rate limits on this account:** 5 rpm for search/enrich/identify (headers `X-RateLimit-Limit/Remaining/Reset`), 10 rpm web, 100 rpm social/agent, 300 rpm autocomplete. Each response carries `X-Credits-Used` and `X-Request-Id`.
- Free account endpoints: `GET /account/endpoints?status=enabled` / `?path=...`, `GET /account/credits`, `GET /account/usage/summary?group_by=endpoint&start=...`, `GET /account/usage/events`.

---

## 3. Enabled vs disabled fields per endpoint (free `/account/endpoints` calls)

Raw: `scratchpad/calls/perm__*.json`. Summary:

### /company/identify — base 0.2, 5 rpm
- Enabled (21): `basic_info` (+ `.all_domains, .company_type, .crustdata_company_id, .description, .employee_count_range, .industries, .logo_permalink, .markets, .name, .primary_domain, .professional_network_id, .professional_network_url, .profile_name, .website, .year_founded`), `crustdata_company_id`, `social_profiles.professional_network(.id,.url)`
- **Disabled:** `headcount`, `headcount.total`, `locations`, `locations.country`, `locations.headquarters`

### /company/enrich — base 2.0, 5 rpm
- Enabled (556 paths) by group: basic_info(19, incl. `status`, `contact_email`, `phone_number`), competitors(6), employee_reviews(55), followers(9), funding(63, incl. `acquisitions.*`, `acquired_by`), headcount(19), hiring(9), indexed_at, locations(7), market_intel(47), metadata(4), news(8), people(196: `cxos`, `decision_makers`, `founders` with experience/education/social_handles/updated_at), public_launches(59), revenue(10), reviews(8), seo(12), social_profiles(5), software_reviews(6), taxonomy(7), updated_at, web_traffic(2)
- **Disabled:** `hiring.recent_openings.*` (9), `maps.*` (51), `social_posts.*` (53), `social_profiles.crunchbase(.url,.uuid)`, `technographics.*` (21)
- premium_fields: technographics=2.0, social_posts=5.0 (both disabled anyway)

### /company/search — base 0.03/result, 5 rpm
- Enabled (138): basic_info(16), followers(6), funding(9), headcount(13), hiring(34), locations(8), maps(11), metadata(4: `updated_at`, `indexed_at`, `growth_calculation_date`), revenue(9), social_profiles(5), software_reviews(6), taxonomy(16)
- Disabled: `social_profiles.crunchbase*`
- premium (filter and response, per result): taxonomy 0.1, followers 0.2, headcount 0.2, roles 0.2, funding 0.2, hiring 0.2, software_reviews 0.2, maps 0.2; technographics filter 1.0. **basic_info, locations and metadata are base price.**

### /company/search/autocomplete — free, 300 rpm (`suggestions[].value`)

### /person/search — base 0.03/result, 5 rpm
- Enabled (219): basic_profile(19), certifications(8), contact(4: `has_business_email`...), dev_platform_profiles(43), education(18), experience(63, incl. `recently_changed_jobs`, current/past `start_date`, `end_date`, `crustdata_company_id`, `title`, `seniority_level`, `company_status`...), metadata(2: `updated_at`), professional_network(6), profile_ranking(4), research_profiles(33), skills(2), social_handles(7), fit(1)
- **Disabled:** `basic_profile.first_name/last_name`, `contact.last_updated`, `education.last_updated`, `education.schools.last_updated`, `experience.employment_details.current.last_updated`, `experience.employment_details.past.last_updated`, `experience.last_updated`, `professional_network.last_updated`, `social_handles.professional_network_identifier.urn_url`, `years_of_experience(_raw)`
- premium (filter and response): experience 0.1, education 0.1, skills 0.1, honors 0.2, certifications 0.2, research_profiles 0.2, professional_network.{connections,followers,open_to_cards,languages} 0.2, summary 0.2 (response), dev_platform 0.8, repos 2.5

### /person/search/autocomplete — free, 300 rpm

### /person/enrich — base 1.0/profile, 5 rpm
- Enabled (285): basic_profile(23), contact(13: `business_emails`, `personal_emails`, `phone_numbers`, premium 1/2/2), dev_platform_profiles(73), education(18), experience(66: current/past with `start_date`, `end_date`, `crustdata_company_id`, `company_website_domain`, `company_status`...), honors(8), metadata(2), professional_network(17), profile_ranking(9), research_profiles(44), skills(2), social_handles(7), updated_at
- **Disabled:** `assessment.*` (authenticity verdict/tier), `basic_profile.last_updated`, `certifications.*`, `contact.last_updated`, `education(.schools).last_updated`, `experience.*.last_updated`, `experience.months/years_of_experience(_raw)`, `professional_network.{joined_date,last_updated,open_to_cards,profile_picture_url,verifications}`, `recently_changed_jobs`, `social_handles...urn_url`, `social_posts.*`
- premium_fields: contact.business_emails 1, personal_emails 2, phone_numbers 2, dev_platform_profiles 1, social_posts 5, research_profiles 2

### /person/identify — base 1.0/match, 5 rpm
- Enabled (18): basic_profile.*, crustdata_person_id, updated_at. **Identifier `emails` is disabled** (403 `emails is not enabled for your account on /person/identify`). Profile URLs work.

### /job/search — base 0.03/result, 5 rpm — enabled (59): company(36), content(2), crustdata_job_id, job_details(10), location(7), metadata(3: `date_added`, `date_updated`). Nothing disabled.

### /social_post/search — base 0.5/post, 100 rpm — enabled (120): actor(15), text, date_posted, share_url, hashtags, mentions(3), engagement(11), reactors(16), comments(26), reposter(15), metadata(4)... Nothing disabled. `limit:0` counts are free.

### /web/search/live — 1/page, 10 rpm — enabled: query, success, timestamp, results.{title,url,snippet,position}, metadata.{total_results,failed_pages,empty_pages}

### /web/enrich/live — 1/page, 10 rpm — enabled: url, success, timestamp, title, content

### /agent/query (= agent search) — base 0.012, 100 rpm — premium: data_search 0.0005, data_enrich 0.05, contact_business_email 0.25, contact_personal_email 0.5, contact_phone 0.5

Enabled endpoint list (`?status=enabled`): `/agent/query, /company/enrich, /company/identify, /company/search, /company/search/autocomplete, /job/search, /person/enrich, /person/identify, /person/search, /person/search/autocomplete, /social_post/search, /web/enrich/live, /web/search/live`.

---

## 4. Real calls — exact request bodies, trimmed responses, cost, latency

### 4.1 Company identify by domain — `cid_domains` (0.8 cr = 4 × 0.2, 3.5 s)
```json
POST /company/identify
{"domains":["bata.in","bata.com","zomato.com","eternal.com"]}
```
```
bata.in   → 1.0  id 573      "Bata India Limited"  primary bata.in  all_domains [bata.in, bata.com]  5001-10000  1931  Public Company  linkedin.com/company/bata-india
bata.com  → 1.0  id 1135086  "Bata Group" bata.com 10001+ ; 1.0 id 1335549 "Bata Italy" (all_domains includes bata.com);
            1.0  id 1959601  "Bata Indonesia" all_domains [mapalasilvagama.or.id, lucsoninfotech.com, redefinealgo.com, bata.com, ...junk]
zomato.com→ 1.0  id 6162764  "Zomato"  all_domains [urbanspoon.com, zomato.com]  1001-5000  2008
eternal.com→1.0  id 6775477  "Eternal" all_domains [eternal.com] 10001+ 2010
```
Headers: `X-RateLimit-Limit: 5, X-RateLimit-Remaining: 4, X-Credits-Used: 0.8, X-Request-Id: ...`

### 4.2 Company identify by name variants — `cid_names` (1.0 cr = 5 × 0.2, 25 candidates each)
```json
POST /company/identify
{"names":["Bata India Ltd","Bata India Limited","BATA INDIA","Zomato Limited","Eternal Ltd"]}
```
```
"Bata India Ltd"     → 0.6 id 573 Bata India Limited | 0.6 Bata Group | 0.6 "Bata India Limited Pune" (id 32129363, no domain) | 0.6 Bata Bangladesh
"Bata India Limited" → 1.0 id 573 | 0.8 "Bata India Limited Pune" | 0.6 Bata Group ...
"BATA INDIA"         → 0.8 id 573 | 0.8 Pune shard | 0.8 "Bata Store - India" (bata.eu)
"Zomato Limited"     → 0.6 id 6162764 Zomato | 0.6 "Zomato India" (Self-Employed) | 0.6 Hyperpure | 0.6 "Zomato Care"
"Eternal Ltd"        → 1.0 "ETERNAL LTD" eternalbeautyuk.com (WRONG company) | 0.8 Springs Eternal ...
```
**Answer to "do `Bata India Ltd` and `bata.in` resolve to the same id?"** Yes, both give 573, but the name variant only ties at 0.6 with 3 other companies. A name alone is not enough. Use the domain, or the domain plus the name.

### 4.3 SME / fake identify — `cid_sme_domains` (0.8), `cid_sme_names` (0.8), `cid_exact` (0.6)
```json
{"domains":["superhouse.in","mirza.co.in","faridagroup.com","wleltd.com","acmeleather.in","bata-india.co"]}
{"names":["Superhouse Limited","Mirza International Limited","Farida Shoes Pvt Ltd","Acme Leather Exports Pvt Ltd"]}
{"domains":["superhouse.in","faridagroup.com","bata.com"],"exact_match":true}
```
```
superhouse.in   → 1.0 "Design Edge Media (DEM)" designedge.media  (WRONG, conf 1.0!) ; 1.0 "superhouse group" (no domain); 1.0 "Superhouse Group (Leather Goods & Belts)" myself-only
mirza.co.in     → 1.0 id 3089 Mirza International Limited 5001-10000 1979   (correct)
faridagroup.com → 1.0 "Alfarida for Trading and Contracting" (probably wrong entity)
wleltd.com      → 1.0 id 5628 Worldwide Leather Exports Ltd 2-10
acmeleather.in  → []   (free)      bata-india.co → []   (free)
names: "Superhouse Limited" → 0.8 "Superhouse Leathers Limited" superhourseleather.com (typo-domain shard)...
       "Mirza International Limited" → 1.0 id 3089 | 0.8 "...,Newdelhi" | 0.8 "..., Kanpur , Up" (shards)
       "Acme Leather Exports Pvt Ltd" (fake) → 0.6 SAFA LEATHER EXPORTS ... (billed 0.2 anyway)
exact_match:true → identical results (no effect)
```

### 4.4 Company enrich (big vendor) — `cenrich_bata` (2 cr, 8.6 s)
```json
POST /company/enrich
{"crustdata_company_ids":[573],"fields":["basic_info","locations","news","people","revenue","headcount"]}
```
```
[{"matched_on":"573","match_type":"crustdata_company_id","matches":[{"company_data":{
  "basic_info":{"name":"Bata India Limited","primary_domain":"bata.in","all_domains":["bata.in","bata.com"],
     "website":"http://www.bata.in","professional_network_id":"571704",
     "description":"Got a query or request? Email us at in-customer.service@bata.com or call us on 72-899-00000 ..."},
  "locations":{"country":"IND","headquarters":"DLF QE, Haryāna, India",
     "street_address":"Bata House, 418/02, Sector 17, Gurgaon Mehrauli Road,, DLF QE, Haryāna","city":"DLF QE","state":"Haryāna","all_office_addresses":[]},
  "revenue":{"estimated":{"lower_bound_usd":1000000000,"upper_bound_usd":1000000000000,"timeseries":[{"date":"2025-08-01",...}]}},
  "headcount":{"total":5987,"largest_headcount_country":"IND","timeseries":[{"date":"2019-10-28","employee_count":2637},...],
     "growth_percent":{"mom":0.76,"qoq":1.87,"six_months":4.25,"yoy":8.36,"two_years":17.05},
     "by_role_absolute":{"Accounting":100,...},"by_region_absolute":{"Greater Delhi Area":1232,...}},
  "news":[ /* 100 items */ {"source":"google_news","article_url":"https://www.multibagg.ai/...","article_title":"Bata India keeps 2030 turnover target, seeks higher profits",
     "article_publisher_name":"Multibagg AI","article_publish_date":"2026-11-09","publisher_domain":"multibagg.ai","confidence_score":0.95}, ...],
  "people":{"decision_makers":[/*123*/],"founders":[],"cxos":[
     {"crustdata_person_id":862157,"basic_profile":{"name":"Person C","headline":"CFO at Bata India Limited","current_title":"Chief Financial Officer","last_updated":"2026-10-31T11:16:01.647Z"},
      "social_handles":{"professional_network_identifier":{"profile_url":"https://www.linkedin.com/in/[redacted]"}},
      "experience":{"employment_details":{"current":[{"employer_name":"Bata India Limited","employee_title":"Chief Financial Officer","employee_start_date":"2024-12-01T00:00:00.000Z","employee_end_date":null,"employer_company_id":...}],
                                          "past":[{"employer_name":"Marico Limited","employee_title":"Head Corporate Finance","employee_end_date":"2021-04-01T00:00:00.000Z"},...]}},
      "updated_at":"2026-10-31T11:16:01.647Z"},
     {"name":"Person F","current_title":"CEO & MD","start":"2026-08-01","updated_at":"2026-11-15"},
     {"name":"Person E","current_title":"CEO and  Managing Director","start":null,"updated_at":"2025-02-14"},   // STALE: ex-CEO
     {"name":"Person G","current_title":"Chief Executive Officer","updated_at":"2025-02-14"},                     // self-claimed (store manager)
     {"name":"Person H","current_title":"Chief Executive Officer","updated_at":"2026-06-15"}, ...]}}}]}]
```
The people sub-records use **different key names** from person search/enrich: `employee_title`, `employee_start_date`, `employee_end_date`, `employer_name`, `employer_company_id`, `employer_linkedin_id`. There is no company-level `updated_at` here.

### 4.5 Company enrich, rebrand pair — `cenrich_eternal_zomato` (4 cr = 2 × 2, 4.6 s)
```json
{"crustdata_company_ids":[6775477,6162764],"fields":["basic_info","locations","news","funding","revenue","hiring","followers","social_profiles","taxonomy","employee_reviews","updated_at","indexed_at","metadata"]}
```
```
Eternal (6775477): status active, Public Company, markets ["PRIVATE"], locations ALL NULL, funding total 0, funding.contact_email "order@zomato.com",
   followers 38,589 (yoy +467%), news 63 (newest 2026-10-22: "Eternal's Q2 Profit Nearly Doubles", "AdOnMo To Merge With Mygate, Eternal To Get 4.4% Stake"),
   metadata {"growth_calculation_date":null,"updated_at":null,"indexed_at":null}, hiring all null
Zomato (6162764): markets ["BSE"], HQ "Pioneer Square Sector 62, Golf Course Extension Road, ... Haryāna", funding total $4.36B, 25 rounds,
   last 2024-11-28 post_ipo_equity, acquisitions [...gastronauci.pl...], acquired_by [{"name":"Talabat","date":"2019-03-04"}] (backwards),
   news 100 (newest 2026-11-09), employee_reviews 3.5 (4165 reviews), twitter x.com/zomato
```
So the rebrand is two records: the new parent's record is thin and the old brand's record holds the data. The **link has to come from your own alias table** or from news.

### 4.6 Company enrich by **name** — `cenrich_byname` (**6 cr**, gotcha)
```json
{"names":["Bata India Ltd"],"fields":["basic_info"]}
```
This returned 3 matches (0.6 each: Bata India Limited, Bata Group, Bata India Limited Pune), and **each was billed 2 cr**. Always identify first (0.2), then enrich by `crustdata_company_ids`.

### 4.7 Company enrich, SMEs — `cenrich_smes` (4 cr, 1.7 s)
```json
{"crustdata_company_ids":[5628,25976],"fields":["basic_info","locations","headcount","people","news","revenue","funding"]}
```
```
Worldwide Leather Exports Ltd (wleltd.com): 2-10, status active, desc "…automotive company based out of Behrampur Road, Gurgaon",
   locations {city Gurgaon, state Haryana, street_address "Gurgaon, Haryana, India"}, headcount.total 6 (last ts 2026-09-07),
   people {decision_makers:0, cxos:0, founders:0}, news [], revenue 0.5–1M USD
True Trident Leather (truetridentleather.com): 11-50, Partnership, founded 2006, headcount.total 1, people.decision_makers [RAHUL KUMAR GAUTAM, Director, updated 2026-04-17],
   news [], funding.contact_email company@truetridentleather.com, HQ = long geocoded locality string in South Delhi
```

### 4.8 Company search (SME discovery and freshness) — `csearch_leather_sme` (0.09 = 3 × 0.03, 1.1 s)
```json
POST /company/search
{"filters":{"op":"and","conditions":[
   {"field":"locations.country","type":"=","value":"IND"},
   {"field":"basic_info.name","type":"(.)","value":"leather"},
   {"field":"basic_info.employee_count_range","type":"in","value":["2-10","11-50","51-200"]}]},
 "fields":["crustdata_company_id","basic_info.name","basic_info.primary_domain","basic_info.all_domains","basic_info.employee_count_range","basic_info.year_founded","basic_info.status","locations.headquarters","locations.street_address","metadata.updated_at","metadata.indexed_at"],
 "sorts":[{"field":"crustdata_company_id","order":"asc"}],"limit":3}
```
```
{"total_count":864,"next_cursor":"H4sI...","companies":[
 {"crustdata_company_id":1887,"metadata":{"updated_at":"2026-11-22T06:26:13Z","indexed_at":"2026-11-22T06:26:13Z"},"basic_info":{"name":"Haryana Leather Chemicals Ltd. - India","primary_domain":"leatherchem.com","status":"active","year_founded":1985,"employee_count_range":"51-200"},"locations":{"headquarters":"India"}},
 {"crustdata_company_id":5628,"metadata":{"updated_at":"2026-11-13T06:27:48Z"},"basic_info":{"name":"Worldwide Leather Exports Ltd","primary_domain":"wleltd.com","employee_count_range":"2-10"},"locations":{"headquarters":"Gurgaon, Haryana, India"}},
 {"crustdata_company_id":25976,"basic_info":{"name":"True Trident Leather",...}}]}
```
Gotcha: in search, the fields are `metadata.updated_at`/`metadata.indexed_at`. Top-level `updated_at` returns `400 Invalid fields ... Did you mean 'metadata.updated_at'`. A 400 is free and lists every `available_fields`.

`csearch_domain` (0.15 = 5 × 0.03): `{"filters":{"op":"or","conditions":[{"field":"basic_info.primary_domain","type":"in","value":["zomato.com","eternal.com"]},{"field":"basic_info.name","type":"in","value":["Eternal Limited","Eternal Ltd"]}]},...}` returned TongueStun, Cibando, Mekanist.net, Urbanspoon and Zomato. All have `zomato.com` in `all_domains`, so the filter matches across all_domains. Acquired brands carry the acquirer's domain.

### 4.9 Autocomplete (free)
```json
POST /company/search/autocomplete {"field":"basic_info.name","query":"bata ind","limit":8}
→ ["Bata India Limited","Bata Indonesia","Bata Industrials",...]
POST /person/search/autocomplete {"field":"experience.employment_details.current.title","query":"chief financial","limit":6}
→ ["Chief Financial Officer","Chief Financial Officer (CFO)","Chief Financial Officer & Company Secretary",...]
POST /person/search/autocomplete {"field":"experience.employment_details.current.company_name","query":"Bata India","limit":6}
→ ["Bata India Limited","Bata India Limited Pune"]
```

### 4.10 Person search — current CFO at vendor — `psearch_cfo_current` (0.23 = 1 result, 2.1 s)
```json
POST /person/search
{"filters":{"op":"and","conditions":[
   {"field":"experience.employment_details.current.company_id","type":"=","value":573},
   {"op":"or","conditions":[
      {"field":"experience.employment_details.current.title","type":"(.)","value":"Chief Financial Officer"},
      {"field":"experience.employment_details.current.title","type":"[.]","value":"CFO"}]}]},
 "fields":["basic_profile.name","basic_profile.current_title","basic_profile.location","social_handles.professional_network_identifier.profile_url","experience.employment_details.current","metadata.updated_at"],
 "limit":3}
```
```
{"total_count":1,"next_cursor":null,"profiles":[{"crustdata_person_id":862157,"metadata":{"updated_at":"2026-11-11T01:11:35+00:00"},
 "basic_profile":{"name":"Person C","current_title":"Chief Financial Officer","location":{"country":"India","raw":"India"}},
 "social_handles":{"professional_network_identifier":{"profile_url":"https://www.linkedin.com/in/[redacted]"}},
 "experience":{"employment_details":{"current":[{"name":"Bata India Limited","company_website":"http://www.bata.in","title":"Chief Financial Officer",
   "start_date":"2024-12-01T00:00:00","end_date":null,"is_default":true,"crustdata_company_id":573,"company_status":"active","seniority_level":"CXO",
   "function_category":"Finance","years_at_company_raw":1,"location":{"raw":"Gurugram, Haryana, India"},"company_headcount_latest":5987,"business_email_verified":false}]}}}]}
```

### 4.11 Person search — named sender at vendor, all roles (core gate call) — `psearch_name_at_vendor` (0.23, 1.2 s)
```json
{"filters":{"op":"and","conditions":[
   {"field":"basic_profile.name","type":"(.)","value":"Person A"},
   {"field":"experience.employment_details.company_id","type":"=","value":573}]},
 "fields":["basic_profile.name","basic_profile.current_title","social_handles.professional_network_identifier.profile_url",
   "experience.employment_details.current.name","experience.employment_details.current.title","experience.employment_details.current.start_date","experience.employment_details.current.crustdata_company_id",
   "experience.employment_details.past.name","experience.employment_details.past.title","experience.employment_details.past.start_date","experience.employment_details.past.end_date","experience.employment_details.past.crustdata_company_id",
   "metadata.updated_at"],"limit":3}
```
```
{"total_count":1,"profiles":[{"crustdata_person_id":454029149,"metadata":{"updated_at":"2026-11-12T02:19:52+00:00"},
 "basic_profile":{"name":"Person A","current_title":"Chief Financial Officer"},
 "experience":{"employment_details":{
   "current":[{"name":"Royal Enfield / Eicher Motors","title":"Chief Financial Officer","start_date":"2022-11-01T00:00:00","crustdata_company_id":0}],
   "past":[{"name":"Bata India Limited","title":"Chief Financial Officer","start_date":"2021-01-01T00:00:00","end_date":"2022-11-01T00:00:00","crustdata_company_id":573},
           {"name":"Puma India","title":"Executive Director & CFO","start_date":"2014-06-01","end_date":"2021-01-01","crustdata_company_id":0}, ...]}}}]}
```
→ Verdict logic: the vendor id 573 appears only in `past[]`, with `end_date` 2022-11. So **"former CFO, left 2022-11, now CFO at Eicher"** means **BLOCK / escalate**.

Same pattern, `psearch_durgesh` (0.23, with `"explain":true`). Person B: `past` = Bata India "Interim Chief Financial Officer" 2024-12→2024-12, "India Supply Chain Finance Controller" 2024-01→2024-11. `current` = **Bata Group** "Global Supply Chain Finance Controller" since 2025-01. Web news (4.16) still says "Bata India gains on appointing Person B as CFO" (2024-11-22). This is a good demo of "right for the day it is used": the 2024 news is true, but the fact no longer holds in 2026.

### 4.12 Person search — past CFOs and recent leavers
`psearch_cfo_past` (0.69 = 3 × 0.23; total_count 4):
```json
{"filters":{"op":"all_of","conditions":[{"op":"and","conditions":[
   {"field":"experience.employment_details.past.company_id","type":"=","value":573},
   {"field":"experience.employment_details.past.title","type":"(.)","value":"Chief Financial Officer"}]}]},
 "fields":["basic_profile.name","basic_profile.current_title","social_handles.professional_network_identifier.profile_url","experience.employment_details.past","experience.employment_details.current.name","experience.employment_details.current.title","experience.employment_details.current.start_date","metadata.updated_at"],"limit":3}
```
→ Person A; "Person I" (Bata "Chief Financial Officer & Finance Director" from 2015-07, later "Financial Advisor" 2021-07→2022-06, current: []); Person N. Note `(.)` fuzzy title matching lets in some loose matches.

`psearch_recent_leavers` (0.69; total_count 3). **`past.end_date` is not filterable** (400 lists the supported fields). Use the all-roles path inside `all_of`:
```json
{"filters":{"op":"all_of","conditions":[{"op":"and","conditions":[
   {"field":"experience.employment_details.company_id","type":"=","value":573},
   {"field":"experience.employment_details.end_date","type":"=>","value":"2026-05-01"},
   {"field":"experience.employment_details.function_category","type":"=","value":"Finance"}]}]},
 "fields":["basic_profile.name","basic_profile.current_title","experience.employment_details.current.name","experience.employment_details.current.start_date","experience.employment_details.past.name","experience.employment_details.past.title","experience.employment_details.past.end_date","experience.recently_changed_jobs","metadata.updated_at"],
 "sorts":[{"field":"metadata.updated_at","order":"desc"}],"limit":3}
```
```
Person D           | current: [] | Bata past: Head - Finance Shared Services, end 2026-10-01 | recently_changed_jobs: true | updated 2026-11-07
Person K        | current: [] | Bata past: Finance Intern, end 2026-06-01                 | false
Person L | current: Performing Arts Club BMU | Bata past: Finance Intern, end 2026-07-01 | false
```
This list can be cached per vendor as a "departed finance staff" watchlist.

`psearch_sme_staff` (0.46 = 2 × 0.23): `{"filters":{"field":"experience.employment_details.current.company_id","type":"in","value":[5628,25976]},...,"limit":3}` → only **2 people** across both SMEs (CS Person J, Company Secretary at Worldwide Leather since 2018-07; RAHUL KUMAR GAUTAM, Director at True Trident since 2019-04).

### 4.13 Person enrich — `penrich_vidhya` (1 cr, 2.1 s), `penrich_two` (2 cr for 2 matched + 1 not_found, 1.5 s)
```json
POST /person/enrich
{"professional_network_profile_urls":["https://www.linkedin.com/in/[redacted]"],"fields":["basic_profile","experience","metadata","updated_at","social_handles"]}
```
```
[{"matched_on":"https://www.linkedin.com/in/[redacted]","match_type":"professional_network_profile_url","match_status":"matched","matches":[{"confidence_score":1.0,"person_data":{
  "crustdata_person_id":454029149,"updated_at":"2026-11-12T02:19:52.605008Z",
  "basic_profile":{"name":"Person A","headline":"Chief Financial Officer  at Eicher Motors Limited","current_title":"Chief Financial Officer",
     "location":{"city":"Gurugram","state":"Haryana","country":"India"},"normalized_title":{"matched_title":"Chief Financial Officer","confident":true,...}},
  "experience":{"employment_details":{
     "current":[{"name":"Royal Enfield / Eicher Motors","title":"Chief Financial Officer","start_date":"2022-11-01T00:00:00+00:00","end_date":null,"crustdata_company_id":null,...}],
     "past":[{"name":"Bata India Limited","title":"Chief Financial Officer","start_date":"2021-01-01T00:00:00+00:00","end_date":"2022-11-01T00:00:00+00:00",
              "crustdata_company_id":573,"company_website_domain":"bata.in","company_status":"active",...}, ...]}}}}]}]
```
Role keys: `company_description, company_headcount_latest, company_headcount_range, company_industries, company_professional_network_industry, company_professional_network_profile_url, company_profile_picture_permalink, company_status, company_website, company_website_domain, crustdata_company_id, description, employment_type, end_date, function_category, is_default, location, name, position_id, professional_network_id, seniority_level, start_date, title, years_at_company, years_at_company_raw`.
`metadata` was **not returned** by enrich even when requested. Only top-level `updated_at` was.

`penrich_two` with dot-path fields (`experience.employment_details.past.end_date` etc.): Person D → `current: []`, past Bata 2024-11→2026-10. Priyanka → current Worldwide Leather (`company_website_domain` "wleltd.com") since 2018-07. A nonexistent URL → `match_status: "not_found"`, `matches: []`, not billed.

`penrich_disabled_field` (`"fields":["basic_profile.name","assessment"]`) → **403** `permission_error` "Access denied to fields: assessment" with `denied_fields`/`permitted_fields`. **0 credits.**

### 4.14 Person identify — `pidentify_emails` (403, 0 cr), `pidentify_url` (1 cr, 1.2 s)
```json
{"emails":["amit.aggarwal@bata.com","vidhya.srinivasan@bata.com","amit.aggarwal@bata-india.co","rahul.mehta@acmeleather.in"]}
→ 403 {"error":{"type":"permission_error","message":"emails is not enabled for your account on /person/identify. Reach out to support or sales to enable it."}}
{"professional_network_profile_urls":["https://www.linkedin.com/in/[redacted]"]}
→ matched 1.0, id 862157, "Person C", current_title "Chief Financial Officer", headline "CFO at Bata India Limited", updated_at "2026-11-12T12:08:48Z"
```

### 4.15 Job search — `jobsearch_bata` (0 cr: empty), `jobsearch_eternal` (0.06 = 2 × 0.03, 1.4 s)
```json
POST /job/search
{"filters":{"op":"and","conditions":[{"field":"company.basic_info.company_id","type":"=","value":573},{"field":"metadata.date_added","type":"=>","value":"2026-09-01"}]},"sorts":[{"field":"metadata.date_added","order":"desc"}],"limit":2}
→ {"job_listings":[],"next_cursor":null,"total_count":0}
{"filters":{"field":"company.basic_info.company_id","type":"in","value":[573,6162764,6775477]},"sorts":[{"field":"metadata.date_added","order":"desc"}],"limit":2}
→ total_count 119; [{"crustdata_job_id":5243294400249991,"job_details":{"title":"Field & Operations Manager (FOM) – Zomato","url":"https://in.indeed.com/viewjob?jk=...","source":"indeed","employment_type":"full_time"},
    "company":{"basic_info":{"crustdata_company_id":6162764,"name":"Zomato","primary_domain":"zomato.com"},"headcount":{"total":26474,"range":"1001-5000"},...},
    "location":{"raw":"Mumbai, Maharashtra","city":"Mumbai","state":"Maharashtra","country":"India","pincode":null},
    "metadata":{"date_added":"2026-11-11T09:51:51","date_updated":"2026-11-13T17:30:26"}},
   {"job_details":{"title":"Area Sales Manager","url":"https://www.linkedin.com/jobs/view/4442831397"},"company":{"basic_info":{"crustdata_company_id":573,"name":"Bata India Limited"}},"metadata":{"date_added":"2026-07-27T11:42:39"}}]
```
No Eternal (6775477) jobs; postings sit under the Zomato id.

### 4.16 Web search live
`websearch_bata_news` `{"query":"Bata India Limited","sources":["news"],"location":"IN","start_date":1790812800}` → `total_results: 0`, **0 cr** (location IN + start_date gave nothing).
`websearch_news_dated` `{"query":"Eternal Zomato","sources":["news"],"start_date":1790812800,"end_date":<now>}` → 10 results, 1 cr, 8.9 s. Date filtering works without `location`.
`websearch_bata_news2` `{"query":"Bata India news","sources":["news"]}` (1 cr, 7.2 s):
```
{"success":true,"query":"Bata India news","timestamp":1795333589884,"metadata":{"total_results":10,"failed_pages":[],"empty_pages":[]},
 "results":[{"position":1,"source":"news","title":"Bata India Shares Slid Even Though Profit Rose","snippet":"If you only glanced at Bata India's recent numbers...","url":"https://www.google.com/goto?url=CAES..."},
            {"position":3,"title":"Bata India Eyes Global Markets to Expand Footwear Exports","url":"https://apparelresources.com/business-news/retail/bata-india-eyes-global-markets-expand-footwear-exports/"}, ...]}
```
`websearch_bata_web_q` `{"query":"Bata India CFO appointed OR resigns 2026","sources":["web"],"location":"IN"}` (1 cr). Snippets carry **Hindi-localised dates**: "2 फ़र॰ 2021 — Bata India has recently appointed Person A as the CFO", "22 नव॰ 2024 — ... appointment of Person B as chief financial officer", "18 जून 2026 — ... Person M, Managing Director shall complete his full term". Many URLs are `google.com/goto?url=...` wrappers that must be resolved before citing.
`websearch_sme_web` `{"query":"\"Worldwide Leather Exports\" Gurgaon","sources":["web"],"location":"IN"}` (1 cr) → 3 irrelevant Facebook/Google results. No web footprint.
`websearch_ai` `{"query":"Has Bata India Limited issued any fraud warning about fake emails or bank account change requests to vendors or customers?","sources":["ai"]}` (1 cr, 7.7 s) → an "AI Overview" `content` ("There is no public record of Bata India Limited issuing an official fraud warning... verify via in-customer.service@bata.com or 72 899 00000...") with **`references: []`**. Not citeable. Do not use it as evidence.

### 4.17 Web enrich live — `webenrich_vendor` (2 cr, 5.6 s), `webenrich_human` (1 cr, 4.5 s)
```json
POST /web/enrich/live {"urls":["https://www.wleltd.com","https://www.bata.com/in/contact-us"]}
→ [{"success":true,"url":"https://www.wleltd.com","http_status":200,"timestamp":1795333622,"title":"wleltd.com","content":"<html>... wleltd.com has expired. Please click here for renew instructions ..."},
   {"success":true,"url":"https://www.bata.com/in/contact-us","http_status":403,"title":"Access Denied","content":"...edgesuite.net..."}]
POST /web/enrich/live {"urls":["https://www.bata.com/in/"],"human_mode":true}
→ http_status 403 "Access Denied" (Akamai), still billed 1
```

### 4.18 Social post search
`social_bata_company` (1 cr = 2 × 0.5, 1.3 s):
```json
{"filters":{"op":"and","conditions":[{"field":"actor.crustdata_entity_id","type":"=","value":573},{"field":"actor.actor_type","type":"=","value":"company"}]},
 "sorts":[{"field":"date_posted","order":"desc"}],"fields":["share_url","text","date_posted","post_type","actor"],"limit":2}
→ {"posts":[{"share_url":"https://www.linkedin.com/posts/bata-india_batabcp-...","text":"As part of Bata India’s CSR volunteering initiative ... Person F | ... | Person C | ...",
     "post_type":"original","date_posted":"2026-09-02T17:29:56Z","actor":{"actor_type":"company","crustdata_entity_id":573,"linkedin_id":"571704","name":"Bata India Limited","location":{"country":"IND",...}}}, ...]}
```
(The newest indexed Bata post is 2026-09-02, about 80 days old.)
`social_mentions_count` `{"filters":{"op":"and","conditions":[{"field":"mentions.company_id","type":"in","value":[573]},{"field":"date_posted","type":"=>","value":"2026-08-01"}]},"limit":0}` → `total_count: 59`, **0 cr**.
`social_bankchange_count` `{"filters":{"op":"and","conditions":[{"field":"text","type":"[.]","value":"bank account details"},{"field":"text","type":"(.)","value":"fraud"},{"field":"date_posted","type":"=>","value":"2026-06-01"}]},"limit":0}` → 158, 0 cr.
`social_fraud_kw` (`text [.] "Bata"` + `text (.) "fraud"`, limit 1, 0.5 cr) → a Hinglish loan-ad post ("Hum bata denge…"). The Hindi word "bata" (tell) collides with the brand, so pair it with `mentions.company_id` or an author filter.

### 4.19 Agent search (permission path `/agent/query`)
`POST /agent/query {"query":...}` → **404 Not Found** (rate-limit header 3 rpm).
`agentsearch_start` → `POST /agent/searches {"query":"Current Chief Financial Officer of Bata India Limited (domain bata.in), with the start date of their current role"}` → `202 {"search_id":"40652-c90a…","state":"running"}`, 0 cr. Poll `GET /agent/searches/{id}`. It succeeded in about 15 s:
```
{"state":"succeeded","created_at":"2026-11-22T07:47:23Z","output":{"note":null,"reason":null,"person":{
  "constraints":[{"id":"c1","text":"The person is currently the Chief Financial Officer of Bata India Limited.","importance":"hard"}],
  "columns":[{"key":"name","field":"basic_profile.name"},{"key":"profile_url",...},{"key":"role_start","label":"Current role start date","field":null},...],
  "rows":[{"id":862157,"values":{"name":"Person C","profile_url":"https://www.linkedin.com/in/[redacted]","role_start":"December 2024","basic_profile_headline":"CFO at Bata India Limited"},
           "constraints":[{"constraint_id":"c1","assessment":"satisfied","evidence":"Current employer records and headline explicitly identify him as CFO at Bata India Limited.","fields":["basic_profile.headline"]}]}]}},
 "credits_used":{"agent_cost":0.35,"search_cost":0.01,"enrich_cost":0.0,"contact_cost":0.0,"total_cost":0.36}}
```
`agentsearch2` `{"query":"Does a person named Rahul Mehta currently work as CFO at Worldwide Leather Exports Ltd (wleltd.com, Gurgaon)?"}` →
```
{"state":"succeeded","output":{"note":"We couldn’t verify that Rahul Mehta currently works as CFO at Worldwide Leather Exports Ltd. The Rahul Mehta profile we found with a current CFO role lists a different employer.","reason":"no_match","person":{"rows":[]}},"credits_used":{"total_cost":0}}
```
This is a ready-made "I can't verify" output, and it was **free**.

---

## 5. Gotchas (ranked by how badly they would hurt the gate)

1. **Domain identify confidence 1.0 can be the wrong company** (superhouse.in → Design Edge Media; faridagroup.com → a trading firm; bata.com → Bata Group, Italy and Indonesia). Accept only if the input domain ∈ `all_domains`. If several records match, prefer the one whose `primary_domain` equals the input. Then cross-check the invoice name.
2. **Name identify always returns candidates** (up to 25) and bills 0.2 even for fake companies. Use ≥0.8 plus a domain agreement. Normalise legal suffixes (Ltd/Limited/Pvt/Private) before calling.
3. **Enrich by name bills every match** (6 cr for one name). Identify, then enrich by id.
4. **`people.cxos` in company enrich is stale or self-claimed.** Filter by per-person `updated_at` and prefer a person search, which re-reads each profile.
5. **Parent vs subsidiary vs shards are separate ids** (Bata India 573, Bata Group 1135086, "Bata India Limited Pune" 32129363). A person who moved from the subsidiary to the parent (Person B) still "works at Bata". Gate on the exact vendor id, and flag the parent as "related entity, not the vendor".
6. **Rebrands are not merged** (Zomato 6162764 vs Eternal 6775477). Keep an alias table in the gate, and use news or `funding.contact_email` as hints.
7. **Index "active" ≠ alive.** wleltd.com is expired. Live-fetch the vendor domain (1 cr) and treat a parked or expired page as a hard warning. An expired domain can be re-registered by an attacker.
8. **Freshness fields are inconsistent.** Person search: `metadata.updated_at`. Person enrich/identify: top-level `updated_at`. Company search: `metadata.updated_at`/`indexed_at`. Company enrich: these came back **null**, so use `people[].updated_at`, `news[].article_publish_date`, or `headcount.timeseries[-1].date`. Per-section `last_updated` fields are disabled. Dates are month-granular, so "since 2024-12" means some day in December 2024.
9. **Filter paths ≠ response paths**: filter `current.company_id` but read `current.crustdata_company_id`. `past.end_date` is not filterable, so use `experience.employment_details.end_date` in `all_of`. Unlinked employers show id 0 (search) or null (enrich).
10. **Web search has no structured date.** Dates sit in the snippet and are localised by `location` (Hindi for IN). `location` + `start_date` returned 0 results. URLs are `google.com/goto` wrappers. The `ai` source has no references.
11. **Web enrich `success:true` on 403/Akamai blocks**, billed anyway. `human_mode` did not get past bata.com.
12. **Email → person identify is disabled**, and even when enabled it can name-match a spoofed address. Do not use it as proof of sender identity.
13. **Social `(.)` is fuzzy** and Hinglish collides with brands. The index lags about 1–3 months for company posts.
14. Rate limit **5 rpm** on search/enrich/identify for this account. Batch identifiers (≤25 per request) and cache by vendor id.
15. `assessment.authenticity` (profile-fabrication score) would be ideal for the gate but is **disabled**.

---

## 6. Coverage for small Indian vendors (SMEs) and "can't verify" policy

- **Company records exist even for tiny firms.** 864 Indian companies with "leather" in the name at 2–200 employees. Domain identify found wleltd.com (2-10 employees). But SME records are thin: `people` empty or 1 person, `news: []`, HQ only at city level ("Gurgaon, Haryana, India") or as a junk locality string, headcount 1–6, revenue band only. Duplicates and shards are common ("Mirza International Limited, Kanpur, Up").
- **People coverage at SMEs is very low.** 2 profiles across 2 SMEs. A real SME CFO "Rahul Mehta" will often **not be in the index**, so absence is *not* evidence of fraud. It is "cannot verify".
- **Lookalike or unknown domains** return `[]` (free). That is a strong signal when the invoice names a company whose canonical record has a *different* domain. It is "unknown" when the company itself is not indexed.
- **Web footprint for SMEs is minimal** (web search returned unrelated Facebook pages).
- Recommended verdict states for the gate:
  - `VERIFIED`: domain ∈ vendor `all_domains`, the sender is in `current[]` at the vendor id with a matching title and start date, and the record `updated_at` is ≤30 days old.
  - `CONTRADICTED / BLOCK`: the sender is in `past[]` at the vendor with an `end_date`, or is currently at another employer or the parent; or the domain is not the vendor's (lookalike); or the vendor domain is expired.
  - `CANNOT VERIFY`: the vendor is not indexed, the sender is not indexed (`total_count: 0`, or agent `reason: "no_match"`), the record is older than the freshness threshold, or the sources conflict (e.g. 2024 news names a different CFO than the 2026 profile). Say exactly which source was missing, and route to a call-back on the phone number or email on file (`basic_info.description` / `funding.contact_email` / `phone_number`).
- Every claim can be cited as: endpoint + `X-Request-Id` + record id (`crustdata_company_id` / `crustdata_person_id` / `share_url` / `article_url`) + the record timestamp (`updated_at`, `article_publish_date`, `date_posted`, WE `timestamp`).

---

## 7. Credit log (this agent)

| call | endpoint | status | X-Credits-Used |
|---|---|---|---|
| cid_domains | /company/identify | 200 | 0.8 |
| cid_names | /company/identify | 200 | 1 |
| cenrich_bata | /company/enrich | 200 | 2 |
| psearch_cfo_current | /person/search | 200 | 0.23 |
| psearch_cfo_past | /person/search | 200 | 0.69 |
| psearch_name_at_vendor | /person/search | 200 | 0.23 |
| penrich_vidhya | /person/enrich | 200 | 1 |
| pidentify_emails | /person/identify | 403 | 0 |
| pidentify_url | /person/identify | 200 | 1 |
| cenrich_eternal_zomato | /company/enrich | 200 | 4 |
| csearch_leather_sme (1st, bad field) | /company/search | 400 | 0 |
| csearch_leather_sme | /company/search | 200 | 0.09 |
| cid_sme_domains | /company/identify | 200 | 0.8 |
| cid_sme_names | /company/identify | 200 | 0.8 |
| cid_exact | /company/identify | 200 | 0.6 |
| jobsearch_bata | /job/search | 200 | 0 |
| jobsearch_eternal | /job/search | 200 | 0.06 |
| social_bata_company | /social_post/search | 200 | 1 |
| social_bankchange_count / social_mentions_count | /social_post/search | 200 | 0 / 0 |
| social_fraud_kw | /social_post/search | 200 | 0.5 |
| websearch_bata_news (empty) | /web/search/live | 200 | 0 |
| websearch_sme_web / bata_news2 / bata_web_q / news_dated / ai | /web/search/live | 200 | 1 each = 5 |
| psearch_durgesh | /person/search | 200 | 0.23 |
| webenrich_vendor | /web/enrich/live | 200 | 2 |
| webenrich_human | /web/enrich/live | 200 | 1 |
| agentquery_try | /agent/query | 404 | – |
| agentsearch (Bata CFO) | /agent/searches | 200 | 0.36 |
| agentsearch2 (SME no_match) | /agent/searches | 200 | 0 |
| cauto_name / pauto_title / pauto_company | autocomplete | 200 | 0 |
| cenrich_smes | /company/enrich | 200 | 4 |
| psearch_sme_staff | /person/search | 200 | 0.46 |
| psearch_recent_leavers (1st, bad field) | /person/search | 400 | 0 |
| psearch_recent_leavers | /person/search | 200 | 0.69 |
| penrich_disabled_field | /person/enrich | 403 | 0 |
| cid_liurl | /company/identify | 200 | 0.2 |
| csearch_domain | /company/search | 200 | 0.15 |
| cenrich_byname | /company/enrich | 200 | 6 |
| psearch_aman_url, psearch_aman_url2 | /person/search | 200 | 0.03 each |
| penrich_two | /person/enrich | 200 | 2 |
| **Total** | | | **36.95** |

Free calls: all `/account/endpoints` (14), `/account/credits` (2), `/account/usage/summary` (1), autocomplete (3), 400/403/404 errors, and empty results.

Files: raw calls are in `C:\Users\KRISHN~1\AppData\Local\Temp\claude\b77e92e8eba051cd\87a25b9a-52cf-454f-a2e7-9aac94327d7c\scratchpad\calls\`. The docs snapshot is in `...\scratchpad\docs\`. The helper is `...\scratchpad\cdcall.py`. The permissions appendix is `...\scratchpad\perm_appendix.md`.
