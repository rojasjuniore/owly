# PRD v1.2 — Multichannel AI Assistant for Mortgage Loan Officers (Phase 1 Only)
**Audience:** Antigravity (Eng + Product + Ops)  
**Roles assumed:** Senior PM + Solutions Architect + Data/ML Lead + Security/Compliance Lead  
**Status:** Build-ready (FINAL — reviewed 2026-02-04)

---

## 1) Executive Summary

### What we're building
A multichannel AI assistant that helps Mortgage Loan Officers (LOs) determine **lender/program eligibility** using **RAG over 300+ lender requirement PDFs** that change frequently.

**Channels (Phase 1)**
- **Outlook (must):** LO emails agent mailbox; agent replies in-thread.
- **Microsoft Teams (must):** team bot accessible to LOs (1:1 only).
- **Teams group reply when tagged:** deferred to Phase 2 (architecture supports it).
- **WhatsApp:** design-ready only (not built in Phase 1).
- **Web app:** out of scope. Create a simple one for testing the flow.

### Unit of value (Phase 1)
**Primary:** Correct lender match (eligibility correctness **given the LO-provided scenario**).  
**Secondary:** LO satisfaction (thumb feedback) + faster decision cycles.

> **Critical Safety Constraint:** The agent must reject making a decision rather than guessing. "I don't know" is a valid and safe Phase 1 outcome; "Eligible" when actually "Ineligible" is a **P0 failure**.

### Definition of recommendation success (Phase 1)
- **Operational success proxy:** LO confirms the match helped (thumb up).
- **Correctness control:** Weekly Admin audit of 10–20 decisions + **Pre-flight Golden Set validation (mandatory before pilot)**.

### Success metrics (Phase 1)
**Quality / Risk**
- Eligibility correctness (Golden Set + Active Audit): **≥ 95%**
- "Confident wrong" rate (audited): **≤ 1%** (P0 defect)
- Citation coverage: **100%** of eligibility claims must include doc-level citations.

**Efficiency**
- Teams: p50 **≤ 15s**, p95 **≤ 30s**
- Outlook: p50 **≤ 60s**, p95 **≤ 120s**

**User**
- Thumb-up rate: **≥ 80%** after first month (tuning expected)
- Escalation rate: **≤ 10%** after tuning (early pilot may be higher)

---

## 2) Problem Definition

### Current LO workflow pain points
- Eligibility rules are scattered across **hundreds of PDFs** with inconsistent structure.
- Many rules are **multi-dimensional** (purpose × occupancy × state overlays × loan amount × FICO × LTV/CLTV × DTI × doc type × property type × credit events).
- PDFs are updated monthly/weekly; LOs accidentally use outdated guidance.
- Matrices and tables dominate many guidelines; naive "text chunking" misses table semantics.

### Why current methods fail
- Manual search is slow and error-prone.
- Incomplete intake: LOs don't consistently ask for the few variables that decide eligibility.
- No enforced confidence gating: people answer prematurely without the minimum data.

---

## 3) Users & Personas

### Primary: Loan Officer (≈ 50 users, Florida-first)
- Needs a short list of eligible options with **reasons** and **sources**.
- Does not care how "smart" the AI is; cares if the guideline is real.

### Secondary: Admin/Support (Ops liaison)
- Owns PDF hygiene (upload/versioning), audits, escalations, and incident response.
- **CRITICAL (Phase 1):** Responsible for verifying extracted matrix rules before activation.

### Jobs-to-be-Done (Phase 1)
1) "Given this scenario, which lenders/programs are **eligible**?"
2) "What is the **minimum information** needed to decide?"
3) "What disqualifies this lender and what are the alternatives?"
4) "Show me where this rule comes from (source)."

---

## 4) Scope & Non-Scope (Phase 1)

### In scope (Phase 1)
- Outlook + Teams agent (1:1 only)
- RAG over PDFs with **Staged Ingestion (Draft → Verify → Active)**
- Mandatory intake checklist / decision tree
- Eligibility determination: **Eligible / Ineligible / Conditional / Unknown**
- Recommendation shortlist (top 1–3 eligible) + "what could break"
- Bounded memory (LO preferences + recent context; 90-day retention)
- Admin console: upload/version, **verify extracted rules**, activate/deprecate, monitor, audit
- Audit logging + escalation workflow (secure link, no PII in email)

### Out of scope (Phase 1)
- Arive integration + KPIs (Phase 2+)
- Survey sent 3 days after interaction (Phase 3+)
- WhatsApp production integration
- Teams group chat @mentions (Phase 2)
- Web app UI
- Pricing/APR, underwriting approvals, legal advice
- Automated web scraping of PDFs

---

## 5) User Journeys (by channel)

### Outlook (must)
1) LO emails agent mailbox.
2) System Ingests → Maps Sender → Thread Context.
3) Agent calculates **Confidence Score** (Code-based, see Section 7.3).
4) If Confidence < 85%: Agent asks targeted follow-ups.
5) If Confidence ≥ 85%: Agent returns eligibility + citations.
6) If Stalled (3 rounds, still <85%): Agent escalates via **Secure Link** (no PII in email).

### Teams (must)
1) LO messages Teams bot in 1:1.
2) Bot runs structured intake (checklist).
3) Bot returns eligibility + citations.

### WhatsApp (design-ready only)
- Same flow as Teams, but:
  - shorter prompts
  - stricter redaction and output limits
- Integration specifics **TBD** (provider, consent, identity mapping).

---

## 6) Functional Requirements

### 6.1 Message ingestion + routing
**Outlook**
- Ingest inbound email to the **agent mailbox** via Microsoft Graph.
- Reply via Graph in the same thread (threading by conversationId / in-reply-to headers).
- Idempotency: de-duplicate by (channel, external_message_id).

**Teams**
- Bot Framework / Teams app.
- Capture: conversation ID, user ID, channel context, mentions.

**Normalized internal message schema**
```
channel, external_thread_id, external_message_id, sender_channel_id, 
sender_email(optional), timestamp, raw_text, cleaned_text, attachments_meta[]
```

### 6.2 Identity & access control (MVP-safe)
- Identity mapping:
  - Outlook: sender email
  - Teams: Teams user ID (and Entra/AAD object ID if available)
- Access control:
  - Default: allow users in "Loan Officers" Entra/AAD group (recommended)
  - MVP alternative: allow all tenant users (riskier; not recommended)

**Assumption:** You control M365 tenant and can grant Graph permissions (confirmed).  
**TBD:** Whether Entra/AAD directory lookup is available/desired for mapping Teams ↔ email.

### 6.3 Conversation state (thread memory)
- Store thread-level state:
  - extracted scenario fields
  - missing required fields
  - last follow-up asked
  - last decision output + citations
  - confidence breakdown
- **Bounded memory policy:**
  - LO preferences (doc type affinity, lender preferences): retained for **90 days**
  - Thread context: retained per Section 8.2 retention policy
  - Clear on explicit LO request ("forget my preferences")

### 6.4 Mandatory follow-up logic (decision tree)
- Agent must not claim Eligible/Ineligible until:
  - minimum required fields are collected (Section 7)
  - evidence retrieval is strong enough
  - no unresolved doc conflicts relevant to decision
- Max follow-up rounds: **3**. Then escalate.

### 6.5 RAG requirements (critical)
The sample PDFs show distinct complex document archetypes; ingestion/retrieval must treat them differently:

**Archetype A — Eligibility Matrices (tables)**
- Dense thresholds (FICO/LTV/loan amount/occupancy/purpose) + "Not Allowed" flags.
- Often includes explicit Effective Date/Revised metadata.
- **Footnotes/overlays:** Must be linked to their parent row as overlay conditions (e.g., "* = requires 12 months reserves").
- Retrieval must be backed by a **structured rule store**, not embeddings alone.
- **Human verification required** before activation (Admin must approve extracted rows).

**Archetype B — Program Guides / Highlights**
- Bullet overlays and restrictions (purpose, property, state overlays).
- Best handled with section-aware chunking + semantic retrieval.

**Archetype C — Long-form Underwriting Guidelines**
- Table of contents, sections, sometimes version control logs.
- Best handled with hierarchical chunking and section paths.

**Archetype D — Announcements / Bulletins**
- Short-lived changes; high risk if stale.
- Must be versioned and optionally time-bounded (expiration date).

**Archetype E — State Licensing / Allowed States**
- Determines whether a lender can operate in a state.
- Must be extracted into a structured "state eligibility" table.

**Requirements**
- Citations: doc-level only is acceptable. Must include: doc_title + version label/effective date (if present) + ingestion timestamp.
- Provenance stored for every decision (retrieval logs).
- Hybrid retrieval: make sure you include semantic meaning (e.g., "ATM charges" ≈ "cash withdrawal fee") and keyword matters (e.g, "Section 23B of the lending policy").
- Rerank: enter the Compression Retriever. Instead of passing everything, we rerank and prune results before feeding them into the LLM. 
- Rewrite: If the reranker step retrieves irrelevant or insufficient documents, look at the input and try to reason about the underlying semantic intent/meaning and reformulate an improved question.

### 6.6 Eligibility + recommendation output contract
For each candidate lender/program:
- `Status:` Eligible | Ineligible | Conditional | Unknown
- `Why:` 2–5 bullets mapping scenario → rule thresholds
- `What could break:` 1–3 bullets (missing fields, edge overlays)
- `Sources:` doc title + version/effective date + "active/deprecated" status

### 6.7 Feedback capture (Phase 1)
- Inline feedback per decision:
  - Thumb up / Thumb down
  - If thumb down: reason code (required) + optional free text
    - reason codes: Wrong eligibility, Missing overlay, Outdated doc, Unclear output, Other

### 6.8 Admin console (Phase 1 minimum)
- Upload PDFs manually OR ingest from a designated folder (SharePoint recommended; Google Drive optional) — **TBD final choice**.
- Required metadata at upload:
  - lender, program tags, doc archetype, effective date/revised date (if not auto-extracted), source URL (optional), "internal distribution constraints" flag
- **Extracted Rules Review UI (REQUIRED for Phase 1):**
  - View auto-extracted `rules_matrix` rows in a grid
  - Edit/correct parsing errors (cell values, footnote links)
  - Approve rows individually or in bulk
  - Only approved rows move from Draft → Active
- Version management:
  - activate/deprecate/supersede
  - set "next review date" (default monthly) to force hygiene
- Re-index controls and status
- Monitoring:
  - usage, latency, escalations, thumbs down rates by lender/doc
- Audit tooling:
  - show retrieved evidence for a decision
  - compare versions (diff summary)

### 6.9 Escalation workflow (Admin/Support)
**Trigger:**
- confidence < 85% after 3 follow-up rounds OR
- conflicting doc evidence OR
- no doc coverage for scenario

**Action:**
- Send email/notification to Admin/Support containing:
  - **Secure link to Admin Console Escalation View** (requires login)
  - Summary only: LO name, topic, confidence score, escalation reason
  - **NO PII in email body** (no transcript, no borrower fields)
- Admin Console Escalation View (after login) displays:
  - full transcript
  - extracted fields + missing fields
  - top retrieved docs/chunks + scores + versions
  - diagnosis: missing fields vs conflict vs taxonomy gap vs stale doc
  - recommended admin action

**Escalation SLA:** **TBD** — Admin/Support to define response time target.

---

## 7) Internal Checklist / Decision Tree Spec (mandatory)

### 7.1 Minimum required fields before Eligible/Ineligible
Agent must collect (ask if missing):

**Deal essentials**
1) State
2) Loan purpose: Purchase | Rate/Term | Cash-Out | Debt Consolidation (if used as separate)
3) Occupancy: Primary | Second Home | Investment
4) Property type: SFR | Condo | 2–4 Unit | Mixed-use | Other
5) Loan amount (number or range)
6) Estimated LTV/CLTV (or purchase price + down payment)

**Borrower essentials**
7) FICO band: <620 | 620–679 | 680–739 | 740+
8) Income/document type: Full doc | Bank Statement | 1099 | WVOE | P&L | Asset Utilization | DSCR | Other
9) Credit event flags (if any): recent BK/FC/SS; late-pay pattern if known

**Ask only if needed by retrieved rules**
- DTI band
- Reserves band
- ITIN / Foreign National / DACA
- Condo warrantability / HOA issues
- Prepayment penalty tolerance
- Purchase type (owner purchase vs entity)

### 7.2 Decision tree flow (Phase 1)
1) Identify intent:
   - eligibility check vs parameter lookup vs "find me docs"
2) Collect minimum fields (above).
3) Run structured rule check (matrices + licensing).
4) Apply narrative overlays (program highlights / long-form sections).
5) Resolve conflicts:
   - **Priority order:** Prefer doc with latest `effective_date` among active versions.
   - If versions conflict and latest active is unclear → do not decide; escalate.
6) Produce verdicts and shortlist.

### 7.3 Confidence rubric (0–100) and gating
**IMPORTANT:** Confidence is a **deterministic code calculation**, NOT an LLM self-assessment.

**Calculation formula:**
- Field completeness (0–40): `(fields_present / fields_required) × 40`
- Retrieval strength (0–25): top chunk similarity score normalized + cross-evidence agreement
- Determinism (0–25): 25 if explicit threshold match in `rules_matrix`; 10 if narrative-only; 0 if no evidence
- Recency certainty (0–10): 10 if doc effective_date < 30 days; 5 if < 90 days; 0 otherwise

**Policy:**
- **≥85:** allow Eligible/Ineligible claims
- **70–84:** ask the highest-leverage missing field
- **<85 after 3 rounds:** escalate

---

## 8) Data & Storage Design (Phase 1)

### 8.1 Core entities/tables
| Table | Key fields | Purpose |
|---|---|---|
| `users` | id, email, teams_user_id, display_name, status | LO identity |
| `threads` | id, channel, external_thread_id, user_id, status, created_at, last_activity_at | conversation container |
| `messages` | id, thread_id, direction, raw_text, cleaned_text, external_message_id, created_at | message log |
| `scenario_state` | thread_id, facts_json, missing_json, updated_at | checklist + extracted fields |
| `documents` | id, lender, archetype, tags_json, source_path, distribution_flag | doc registry |
| `document_versions` | id, document_id, version_label, effective_date, revised_date, **status (draft/active/deprecated)**, hash, ingested_at, supersedes_version_id, **verified_by**, **verified_at** | version control |
| `chunks` | id, doc_version_id, section_path, chunk_text, embedding_id, table_flag | vector retrieval units |
| `rules_matrix` | id, doc_version_id, lender, program, keys_json, thresholds_json, footnotes_json, notes, effective_date, **status (draft/approved)**, **approved_by**, **approved_at** | structured eligibility rows |
| `state_licensing` | id, doc_version_id, lender, allowed_states[], notes | structured licensing |
| `retrieval_logs` | id, message_id, query, top_docs_json, top_chunks_json, scores_json, created_at | audit trace |
| `decisions` | id, thread_id, inputs_json, outputs_json, confidence_json, created_at | eligibility outputs |
| `feedback` | id, decision_id, user_id, thumbs, reason_code, comment, created_at | learning signals |
| `escalations` | id, thread_id, reason, payload_json, sent_at, **resolved_at**, **resolved_by** | admin workflow |

### 8.2 Retention + privacy (must confirm)
- Thread message content: **90 days** (ASSUMPTION; confirm with compliance)
- Decision/audit logs: **1 year** (ASSUMPTION; confirm with compliance)
- LO preferences: **90 days**
- Minimize stored borrower PII: store bands/ranges; redact SSN/DOB/account numbers if detected.

---

## 9) RAG + Ingestion Pipeline Design (Phase 1)

### 9.1 Key principle
Do not treat PDFs as uniform text. Use a **hybrid retrieval stack**:
1) **Structured extraction** for matrices/licensing (rules store)
2) **Vector search** for narrative overlays and edge cases
3) Answer generator that only uses retrieved evidence and cites the doc versions.

### 9.2 Ingestion pipeline (with Human-in-the-Loop)
1) Ingest PDF → object storage + metadata
2) Classify archetype (A–E)
3) Extract metadata:
   - lender/program, effective/revised dates (auto + admin override), distribution constraints flag
4) Text extraction
5) Chunking:
   - Long-form guides: hierarchical sections (`section_path`)
   - Program guides: subsection chunking
   - Announcements: small chunks + time-bounding metadata
6) Table extraction:
   - Matrices → `rules_matrix` records (normalized rows, status = **draft**)
   - Licensing → `state_licensing` table
   - **Footnotes extracted and linked to parent rows**
7) Embeddings:
   - Embed chunks + optionally embed each normalized rule row text for semantic lookup
8) **Draft state:** All extracted rules sit in `status = draft`. Document version is `draft`.
9) **Human Verification (REQUIRED for Archetype A):**
   - Admin reviews extracted `rules_matrix` rows in Admin Console grid
   - Admin corrects errors (cell values, footnote links, threshold ranges)
   - Admin approves rows → `status = approved`
10) **Activation:** Admin promotes document version from `draft` → `active`. Only approved rules are used.

### 9.3 Document hygiene + versioning policy
- Every new upload creates a new `document_version` (hash-based, status = draft).
- Admin must verify (for matrices) and set status: active/deprecated.
- System uses **only active** versions. If only deprecated versions match, agent flags "deprecated source" and refuses eligibility verdict by default.
- **No auto-activation:** New docs never go straight to active.

### 9.4 Retrieval evaluation plan (Phase 1)
- **Golden Set (REQUIRED BEFORE PILOT):** Collect 20 Q/A pairs from SME/Admin. System must pass ≥95%.
- MVP evaluation:
  - weekly admin audit of 10–20 decisions
  - track "wrong eligibility" P0s
  - update taxonomy, rules extraction, and prompts based on failures

---

## 10) Eligibility & Recommendation Engine (Phase 1)

### Inputs
- Scenario facts from checklist
- Structured rules (`rules_matrix`, `state_licensing`) — **only approved/active**
- Retrieved narrative chunks (overlays/restrictions)
- LO preferences (bounded; optional)

### Process
1) Validate minimum fields; else ask follow-ups.
2) Licensing/state gate (if state known).
3) Matrix eligibility computation:
   - match scenario to program/lender row keys
   - compute pass/fail/conditional
4) Overlay check:
   - apply restrictions from narrative chunks (purpose/property/credit events)
5) Produce ranked shortlist (top 1–3 eligible) by:
   - fewer overlays/conditions
   - higher max LTV at given FICO band
   - alignment with doc type (full doc vs alt doc)
6) Output with citations + "what could break".

### Guardrails
- If a critical field is missing: no Eligible/Ineligible claim.
- If evidence conflicts: no claim; ask more or escalate.
- No pricing, APR, underwriting promises.

---

## 11) Non-Functional Requirements (Phase 1)

### Latency
- Teams: p50 ≤ 15s; p95 ≤ 30s
- Outlook: p50 ≤ 60s; p95 ≤ 120s

### Availability
- 99.5% monthly (MVP)

### Security/Compliance
- Encryption at rest (AES-256) and in transit (TLS 1.2+)
- RBAC:
  - LO: own threads only
  - Admin: all threads + corpus controls
- Audit logs append-only
- **PII Redaction patterns (buildable):**
  - SSN: `\b\d{3}-\d{2}-\d{4}\b` or `\b\d{9}\b`
  - DOB: `\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b`
  - Account numbers: `\b\d{8,17}\b` (context-aware; flag for review)
  - Email: standard email regex (store hashed if possible)
- Respect lender doc distribution constraints: never forward raw PDFs to consumers; summarize internally.

### Cost control
- Cap retrieved context (topK chunks + limited tokens)
- Use structured rules to reduce token usage for matrix-heavy questions
- Incremental re-indexing (avoid re-embedding whole corpus unnecessarily)

---

## 12) Metrics & Instrumentation (Phase 1)

### KPIs
- Adoption: WAU LOs, conversations/LO/week
- Efficiency: time-to-answer, turns-to-resolution
- Quality: citation coverage, escalation rate, "unknown" rate
- Risk: audited eligibility accuracy, P0 wrong-eligibility count
- Satisfaction: thumb-up rate; thumb-down reasons distribution

### Required events
- `message_received`, `intent_classified`, `followup_asked`, `facts_updated`
- `retrieval_run`, `rules_evaluated`, `decision_generated`
- `decision_sent`, `feedback_received`
- `escalation_triggered`, `escalation_sent`
- `doc_uploaded`, `doc_version_verified`, `doc_version_activated`, `reindex_completed`

---

## 13) Rollout Plan & Milestones (Phase 1)

### Timeline (indicative; adjust after stack decision)
**M1 (Weeks 1–2):** Channels + data foundation  
- Outlook ingestion + reply
- Teams bot MVP
- Core DB schema + logging

**M2 (Weeks 3–4):** RAG foundation  
- PDF ingestion + chunking + embeddings
- Doc registry + versioning controls (draft/active/deprecated)
- Basic answer with citations (no eligibility yet)

**M3 (Weeks 5–6):** Eligibility gating  
- Checklist + confidence rubric + follow-up logic
- Structured matrix extraction for top 10 lenders
- **Admin Rules Review UI**
- Eligibility output contract

**M4 (Weeks 7–8):** Admin + QA  
- Admin console v1 (upload/version/verify/monitor)
- Escalation email workflow (secure link)
- **Golden Set creation (20 Q/A pairs)**
- Pilot audits + tuning

### Pilot gates (MUST PASS BEFORE LAUNCH)
- **Golden Set accuracy ≥ 95%** (20 Q/A pairs)
- Audited eligibility accuracy ≥ 95% (10–20 live decisions)
- p95 latency within target
- P0 wrong-eligibility ≤ 1% in sample
- Escalation volume manageable (SLA met)

---

## 14) Risks, Failure Modes, Mitigations (Phase 1)

| Risk | Failure mode | Mitigation |
|---|---|---|
| **Confident wrong eligibility** | LO acts on wrong rule | minimum fields gating + structured rules + audits + Human-in-the-Loop verification |
| **Stale docs** | old versions used | strict active/deprecated + review dates + admin activation |
| **Table semantics lost** | embeddings misread matrices | parse matrices into rules store + Human verification + deterministic evaluation |
| **Conflicting rules** | two docs disagree | conflict detection + effective_date priority + refuse/ask/escalate |
| **Identity mismatch** | wrong memory applied | group-based access + cautious memory + channel-based IDs |
| **Data leakage** | borrower PII stored/exposed | redaction regex + minimization + RBAC + audit logs + secure escalation links |
| **Announcement staleness** | old bulletin overrides current | time-bounded metadata + versioning + admin governance |
| **Matrix footnotes missed** | overlay condition ignored | footnote extraction + linking to parent rows |

---

## 15) Acceptance Criteria (testable)

### Epic A — Outlook channel
- **AC-A1:** Inbound email to agent mailbox is ingested and replied to in the same thread within p95 latency.
- **AC-A2:** Duplicate webhook deliveries do not create duplicate replies (idempotency test).

### Epic B — Teams channel
- **AC-B1:** Teams 1:1 message receives response within p95 latency target.
- **AC-B2:** Unauthorized users (not in LO group) receive access denied message.

### Epic C — Checklist enforcement
- **AC-C1:** If FICO is missing, agent asks for it and does NOT issue Eligible/Ineligible.
- **AC-C2:** If LTV is missing, agent asks for it and does NOT issue Eligible/Ineligible.
- **AC-C3:** Agent stops after 3 follow-up rounds if confidence <85% and triggers escalation.

### Epic D — Evidence + citations
- **AC-D1:** Every eligibility claim includes doc-level citations (doc + version label/effective date).
- **AC-D2:** Retrieval logs are stored and accessible to admins per decision (audit trail).

### Epic E — Matrix rules extraction (top lenders)
- **AC-E1:** For a known scenario (from Golden Set), eligibility row match is deterministic and reproducible.
- **AC-E2:** Admin can re-run decision with the same inputs and reproduce the same verdict.
- **AC-E3:** Footnotes are extracted and displayed linked to their parent row in Admin Console.

### Epic F — Admin console
- **AC-F1:** Admin uploads a new PDF; it appears with status = draft (not active).
- **AC-F2:** Admin can view, edit, and approve extracted `rules_matrix` rows.
- **AC-F3:** Only approved docs (status = active) are used for eligibility decisions.
- **AC-F4:** Deprecated versions are not used; if referenced, agent flags "deprecated source."

### Epic G — Escalations
- **AC-G1:** Escalation email contains secure link only (no PII).
- **AC-G2:** Admin Console Escalation View (after login) displays full transcript + evidence.

### Epic H — Golden Set
- **AC-H1:** System passes ≥ 19/20 Golden Set questions before pilot launch.

---

## 16) Architecture Options (Phase 1) + Recommendation

### Option 1 — Lean MVP (fastest to pilot)
**Core**
- Single backend service (API + worker)
- Postgres (with JSONB) + pgvector (or managed vector store)
- Object storage for PDFs
- Teams Bot + Graph integration for Outlook
- Admin web console minimal

**Pros**
- Speed to ship, fewer moving parts
- Easy debugging and iteration

**Cons**
- Can get messy at scale (pipelines, audits, observability)
- Rework likely when adding WhatsApp/Web app or high doc churn

### Option 2 — Scalable foundation (clean separation)
**Core**
- Channel adapters → queue/event bus
- Orchestrator service for conversation state + gating
- Dedicated ingestion workers + doc registry/version service
- Retrieval service (vector + structured rules)
- Analytics/monitoring pipeline
- Strong audit/observability

**Pros**
- Better governance, safer scaling, easier future phases
- Cleaner admin workflows and compliance posture

**Cons**
- Slower initial delivery
- Higher infra overhead

**Recommendation**
Start with **Option 1**, but enforce **Option-2 interfaces** from day 1:
- normalized message schema
- doc registry + versioning service boundary (with draft/active/deprecated)
- structured rules store for matrices (with approval workflow)
- immutable audit logs

That's the minimum to avoid building a demo that collapses under real usage.

---

## 17) Open Questions (Phase 1) — must be resolved to finalize build

1) **Golden Set ownership:** Who is the SME responsible for creating the 20 Q/A pairs before pilot?
2) **Identity mapping:** Confirm whether we can/should use Entra/AAD directory lookup to link Teams user → email.
3) **Corpus location for Phase 1:** SharePoint folder vs Google Drive folder (pick one).
4) **Admin/Support escalation email DL** + SLA expectations (response time target).
5) **Retention requirements:** Confirm 90 days for messages, 1 year for audit logs.
6) **Initial pilot lender/program set:** Top 10 to prioritize matrix extraction.
7) **Allowed user access policy:** LO-only Entra group (recommended) vs all tenant users.
8) **Florida default:** Is it allowed when state missing, or must ask every time? (Recommended: ask every time.)
9) **Borrower PII storage:** Confirm no SSN/DOB stored beyond bands/ranges (recommended: no).
10) **Stack constraint:** Azure-native preferred or flexible?

---

# Brutally Honest Review (for Antigravity)

## What will break if you build this naively
1) **If you auto-activate extracted matrix rows, you will ship wrong rules.** The footnotes, merged cells, and "N/A" patterns in the sample PDFs (e.g., Activator Alt Doc Matrix) will break naive parsing. Human verification is non-negotiable.
2) **If you send PII in escalation emails, you create a compliance incident.** Use secure links.
3) **If you let the LLM self-report confidence, it will hallucinate 90% when it has no idea.** Confidence must be code-calculated.
4) **If you launch without a Golden Set, you have no evidence the system works.** "We'll audit later" is not a launch gate.
5) **If you skip version governance, you'll ship stale rules.** "Eligible/ineligible" with stale docs is worse than useless.

## Non-negotiable implementation recommendations
- Implement structured `rules_matrix` extraction for the first 10 lenders before expanding.
- Build the Admin Rules Review UI (grid view + edit + approve) in M3.
- Extract footnotes and link them to parent rows in the matrix.
- Treat announcements as time-bounded overrides; do not let old bulletins dominate retrieval.
- Enforce minimum fields gating at the orchestration layer, not in prompt text.
- Build an admin "activate/deprecate" flow; never auto-activate new docs by default.
- Add a hard "no eligibility without active docs" rule.
- Create the Golden Set (20 Q/A) before M4 pilot audits begin.

## Reality check on "85% confidence"
Without labeled data, 85% is a product threshold, not a calibrated probability. Use it as a gate, then calibrate over time using audit outcomes and feedback. The formula in Section 7.3 provides a starting point; expect to tune weights after pilot.
