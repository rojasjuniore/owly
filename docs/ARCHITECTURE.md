# Owly Agent — Architecture & Stack (Phase 1)

**Version:** 1.0  
**Date:** 2026-02-07  
**Status:** Proposal

---

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CHANNELS                                        │
├─────────────┬─────────────┬─────────────┬─────────────────────────────────────┤
│   Outlook   │   Teams     │  WhatsApp   │   Web (testing)                    │
│   (Graph)   │   (Bot FW)  │  (future)   │   (Next.js)                        │
└──────┬──────┴──────┬──────┴──────┬──────┴─────────────┬───────────────────────┘
       │             │             │                    │
       ▼             ▼             ▼                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CHANNEL ADAPTER LAYER                                │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Normalized Message Schema → Queue (Azure Service Bus)              │    │
│  │  - channel, thread_id, sender_id, timestamp, text, attachments      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ORCHESTRATOR SERVICE                                 │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐                 │
│  │ Thread Manager │  │ Checklist Gate │  │ Confidence Calc│                 │
│  │ (state machine)│  │ (required flds)│  │ (deterministic)│                 │
│  └────────────────┘  └────────────────┘  └────────────────┘                 │
│                              │                                               │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │                    DECISION ENGINE                                  │     │
│  │  1. Field validation → 2. Retrieval → 3. Rules eval → 4. Output    │     │
│  └────────────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
┌───────────────────────────────┐   ┌───────────────────────────────────────┐
│      RETRIEVAL SERVICE        │   │         RULES ENGINE                   │
│  ┌─────────────────────────┐  │   │  ┌─────────────────────────────────┐  │
│  │  Vector Search (pgvector│  │   │  │  Structured Rules (rules_matrix)│  │
│  │  or Azure AI Search)    │  │   │  │  State Licensing Table          │  │
│  └─────────────────────────┘  │   │  │  Deterministic Matching         │  │
│  ┌─────────────────────────┐  │   │  └─────────────────────────────────┘  │
│  │  Reranker (Cohere/Cross)│  │   │                                       │
│  │  Query Rewriter         │  │   │                                       │
│  └─────────────────────────┘  │   │                                       │
└───────────────────────────────┘   └───────────────────────────────────────┘
                    │                               │
                    └───────────────┬───────────────┘
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DATA LAYER                                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │  PostgreSQL     │  │  Blob Storage   │  │  Redis (cache/sessions)    │  │
│  │  + pgvector     │  │  (PDFs)         │  │                             │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         INGESTION PIPELINE                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ PDF      │→ │ Classify │→ │ Extract  │→ │ Chunk +  │→ │ Draft Store  │  │
│  │ Upload   │  │ Archetype│  │ Tables   │  │ Embed    │  │ (verify req) │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ADMIN CONSOLE                                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │ Doc Management  │  │ Rules Review UI │  │ Monitoring Dashboard        │  │
│  │ Upload/Version  │  │ Edit/Approve    │  │ Usage/Latency/Escalations   │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Component Details

### 2.1 Channel Adapters

| Channel | Integration | Auth | Threading |
|---------|-------------|------|-----------|
| **Outlook** | Microsoft Graph API | OAuth2 (App) | conversationId + In-Reply-To |
| **Teams** | Bot Framework SDK | AAD App | conversationId |
| **Web** | REST API | JWT | session-based |

**Normalized Message Schema:**
```typescript
interface InboundMessage {
  channel: 'outlook' | 'teams' | 'web' | 'whatsapp';
  externalThreadId: string;
  externalMessageId: string;
  senderChannelId: string;      // email or teams user id
  senderEmail?: string;
  timestamp: Date;
  rawText: string;
  cleanedText: string;
  attachments?: AttachmentMeta[];
}
```

### 2.2 Orchestrator Service

**Responsibilities:**
- Thread state management (facts collected, missing fields, follow-up count)
- Checklist enforcement (9 required fields before eligibility)
- Confidence calculation (deterministic, code-based)
- Routing to retrieval + rules engine
- Response formatting with citations

**State Machine:**
```
INIT → COLLECTING → EVALUATING → RESPONDED
         ↓              ↓
    FOLLOW_UP      ESCALATED
```

### 2.3 Retrieval Service

**Hybrid approach:**
1. **Vector search** — semantic similarity for narrative chunks
2. **Keyword boost** — exact matches for policy sections, codes
3. **Reranking** — cross-encoder or Cohere rerank
4. **Query rewriting** — if initial retrieval weak, reformulate

**Retrieval flow:**
```python
def retrieve(query: str, scenario: ScenarioFacts) -> RetrievalResult:
    # 1. Embed query
    embedding = embed(query)
    
    # 2. Vector search (top 20)
    candidates = vector_search(embedding, top_k=20)
    
    # 3. Keyword boost for exact matches
    candidates = boost_keywords(candidates, query)
    
    # 4. Rerank (top 5)
    ranked = rerank(query, candidates, top_k=5)
    
    # 5. If weak results, rewrite and retry
    if ranked.max_score < 0.7:
        rewritten = rewrite_query(query, scenario)
        ranked = retrieve(rewritten, scenario)
    
    return ranked
```

### 2.4 Rules Engine

**Deterministic matching against structured data:**

```python
def evaluate_eligibility(scenario: ScenarioFacts) -> List[EligibilityResult]:
    results = []
    
    # 1. State licensing gate
    licensed_lenders = get_licensed_lenders(scenario.state)
    
    # 2. For each lender, check matrix rules
    for lender in licensed_lenders:
        rules = get_active_rules(lender, scenario.doc_type)
        
        for rule in rules:
            match = rule.matches(
                fico=scenario.fico_band,
                ltv=scenario.ltv,
                purpose=scenario.purpose,
                occupancy=scenario.occupancy,
                property_type=scenario.property_type
            )
            
            if match.status != 'NOT_ALLOWED':
                results.append(EligibilityResult(
                    lender=lender,
                    program=rule.program,
                    status=match.status,  # ELIGIBLE | CONDITIONAL
                    conditions=match.conditions,
                    footnotes=rule.footnotes,
                    source=rule.doc_version
                ))
    
    # 3. Apply narrative overlays (restrictions from chunks)
    results = apply_overlays(results, scenario)
    
    # 4. Rank and return top 3
    return rank_results(results)[:3]
```

### 2.5 Ingestion Pipeline

**Flow:**
```
PDF Upload → Archetype Classification → Metadata Extraction
     ↓
Text Extraction (PyMuPDF / Azure Document Intelligence)
     ↓
┌─────────────────────────────────────────────────┐
│ Archetype A (Matrix)    → Table extraction      │
│                         → rules_matrix (DRAFT)  │
│                         → Human verification    │
├─────────────────────────────────────────────────┤
│ Archetype B-D (Narrative) → Chunking           │
│                           → Embeddings          │
│                           → chunks table        │
├─────────────────────────────────────────────────┤
│ Archetype E (Licensing) → state_licensing      │
└─────────────────────────────────────────────────┘
     ↓
Admin Review → Approve → ACTIVE
```

### 2.6 Admin Console

**Features (Phase 1):**
- Document upload with metadata
- Version management (draft/active/deprecated)
- Rules Review UI (grid view, edit, bulk approve)
- Escalation queue
- Usage dashboard (latency, thumbs, escalation rate)
- Audit trail viewer

---

## 3. Stack Recommendation

### 3.1 Primary Stack (Azure-native, recommended)

| Layer | Technology | Rationale |
|-------|------------|-----------|
| **Runtime** | Azure Container Apps | Serverless containers, auto-scale, cheap |
| **API** | FastAPI (Python) | Async, fast, great for AI workloads |
| **Database** | Azure PostgreSQL Flex + pgvector | Relational + vector in one, cost-effective |
| **Queue** | Azure Service Bus | Reliable messaging, dead-letter support |
| **Storage** | Azure Blob Storage | PDFs, cheap, integrates with everything |
| **Cache** | Azure Cache for Redis | Session state, hot data |
| **Vector Search** | pgvector (in Postgres) | Avoid extra service, good enough for 300 docs |
| **LLM** | Azure OpenAI (GPT-4o) | Enterprise-grade, same region, low latency |
| **Embeddings** | Azure OpenAI (text-embedding-3-small) | 1536 dims, cheap, fast |
| **Reranker** | Cohere Rerank API | Best quality/cost for reranking |
| **PDF Extraction** | Azure Document Intelligence | Best for tables/matrices |
| **Teams Bot** | Azure Bot Service + Bot Framework SDK | Native integration |
| **Outlook** | Microsoft Graph API | Direct, no middleware needed |
| **Admin UI** | Next.js (static) on Azure Static Web Apps | Fast, cheap, SSR for auth |
| **Auth** | Azure AD / Entra ID | Already in M365 tenant |
| **Monitoring** | Azure Monitor + Application Insights | Native, good enough |
| **Secrets** | Azure Key Vault | Required for enterprise |

### 3.2 Alternative Stack (Cloud-agnostic, if Azure not required)

| Layer | Technology | Rationale |
|-------|------------|-----------|
| **Runtime** | Railway or Render | Simpler, faster deploy |
| **API** | FastAPI (Python) | Same |
| **Database** | Supabase (Postgres + pgvector) | Managed, includes auth |
| **Queue** | BullMQ + Redis | Simple, effective |
| **Storage** | Supabase Storage or S3 | Cheap |
| **LLM** | Anthropic Claude or OpenAI direct | Flexible |
| **PDF Extraction** | Unstructured.io or LlamaParse | Good for tables |
| **Admin UI** | Next.js on Vercel | Fast iteration |

### 3.3 Cost Estimate (Azure, Phase 1)

| Service | Tier | Monthly Est. |
|---------|------|--------------|
| Container Apps | Consumption | $50-100 |
| PostgreSQL Flex | Burstable B1ms | $30 |
| Blob Storage | Hot, 10GB | $5 |
| Redis Cache | Basic C0 | $16 |
| Azure OpenAI | GPT-4o ~500k tokens/day | $300-500 |
| Document Intelligence | S0 ~1000 pages/mo | $50 |
| Bot Service | Standard | $0 (included) |
| Static Web Apps | Free tier | $0 |
| **Total** | | **~$450-700/mo** |

---

## 4. Service Boundaries

```
┌─────────────────────────────────────────────────────────────────┐
│                        owly-api                                  │
│  Single deployable containing:                                   │
│  - Channel adapters (Outlook, Teams, Web)                       │
│  - Orchestrator                                                  │
│  - Retrieval service                                            │
│  - Rules engine                                                  │
│  - Admin API                                                     │
│                                                                  │
│  WHY: Faster iteration in Phase 1. Split later if needed.      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     owly-ingestion                               │
│  Separate worker for:                                            │
│  - PDF processing (CPU-intensive)                               │
│  - Table extraction                                              │
│  - Embedding generation                                          │
│  - Triggered by queue or cron                                   │
│                                                                  │
│  WHY: Decoupled from request path. Can scale independently.     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      owly-admin                                  │
│  Next.js app for:                                                │
│  - Document management UI                                        │
│  - Rules review grid                                            │
│  - Monitoring dashboard                                          │
│  - Escalation queue                                             │
│                                                                  │
│  WHY: Separate deploy cycle from API. Static hosting = cheap.   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. Data Model (Postgres)

```sql
-- Core entities
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE,
    teams_user_id VARCHAR(255),
    display_name VARCHAR(255),
    role VARCHAR(50) DEFAULT 'lo', -- lo | admin
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE threads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel VARCHAR(50) NOT NULL,
    external_thread_id VARCHAR(255) NOT NULL,
    user_id UUID REFERENCES users(id),
    status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_activity_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(channel, external_thread_id)
);

CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id UUID REFERENCES threads(id),
    direction VARCHAR(10) NOT NULL, -- inbound | outbound
    external_message_id VARCHAR(255),
    raw_text TEXT,
    cleaned_text TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE scenario_state (
    thread_id UUID PRIMARY KEY REFERENCES threads(id),
    facts JSONB DEFAULT '{}',
    missing_fields TEXT[],
    follow_up_count INT DEFAULT 0,
    confidence_score INT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Document management
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lender VARCHAR(255) NOT NULL,
    program VARCHAR(255),
    archetype VARCHAR(10) NOT NULL, -- A, B, C, D, E
    tags TEXT[],
    source_path VARCHAR(500),
    distribution_restricted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE document_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id),
    version_label VARCHAR(100),
    effective_date DATE,
    revised_date DATE,
    status VARCHAR(20) DEFAULT 'draft', -- draft | active | deprecated
    file_hash VARCHAR(64),
    blob_path VARCHAR(500),
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    verified_by UUID REFERENCES users(id),
    verified_at TIMESTAMPTZ,
    supersedes_version_id UUID REFERENCES document_versions(id)
);

-- Vector store
CREATE TABLE chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_version_id UUID REFERENCES document_versions(id),
    section_path TEXT,
    chunk_text TEXT NOT NULL,
    chunk_index INT,
    is_table BOOLEAN DEFAULT FALSE,
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX chunks_embedding_idx ON chunks 
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Structured rules
CREATE TABLE rules_matrix (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_version_id UUID REFERENCES document_versions(id),
    lender VARCHAR(255) NOT NULL,
    program VARCHAR(255),
    keys JSONB NOT NULL, -- {purpose, occupancy, property_type, doc_type}
    thresholds JSONB NOT NULL, -- {fico_min, ltv_max, loan_min, loan_max, dti_max}
    footnotes TEXT[],
    notes TEXT,
    effective_date DATE,
    status VARCHAR(20) DEFAULT 'draft', -- draft | approved
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE state_licensing (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_version_id UUID REFERENCES document_versions(id),
    lender VARCHAR(255) NOT NULL,
    allowed_states TEXT[] NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Decisions & audit
CREATE TABLE decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id UUID REFERENCES threads(id),
    inputs JSONB NOT NULL,
    outputs JSONB NOT NULL,
    confidence JSONB NOT NULL,
    retrieval_log_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE retrieval_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id UUID REFERENCES messages(id),
    query TEXT,
    rewritten_query TEXT,
    top_chunks JSONB, -- [{chunk_id, score, text_preview}]
    top_rules JSONB,  -- [{rule_id, match_score}]
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id UUID REFERENCES decisions(id),
    user_id UUID REFERENCES users(id),
    thumbs VARCHAR(10), -- up | down
    reason_code VARCHAR(50),
    comment TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE escalations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id UUID REFERENCES threads(id),
    reason VARCHAR(100),
    payload JSONB,
    sent_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    resolved_by UUID REFERENCES users(id)
);
```

---

## 6. API Design

### 6.1 Internal APIs (owly-api)

```yaml
# Channel webhooks
POST /webhooks/outlook     # Graph subscription callback
POST /webhooks/teams       # Bot Framework messages

# Orchestrator (internal)
POST /internal/process-message
POST /internal/generate-response

# Admin API
GET    /api/admin/documents
POST   /api/admin/documents
GET    /api/admin/documents/:id/versions
POST   /api/admin/documents/:id/versions
PATCH  /api/admin/versions/:id          # status: active/deprecated

GET    /api/admin/rules
GET    /api/admin/rules/:id
PATCH  /api/admin/rules/:id             # edit thresholds, approve
POST   /api/admin/rules/bulk-approve

GET    /api/admin/escalations
PATCH  /api/admin/escalations/:id       # resolve

GET    /api/admin/stats                 # usage, latency, thumbs
GET    /api/admin/audit/:decision_id    # retrieval + reasoning trace
```

### 6.2 Response Contract

```typescript
interface EligibilityResponse {
  confidence: number;  // 0-100
  status: 'complete' | 'need_info' | 'escalated';
  
  // If need_info
  missingFields?: string[];
  followUpQuestion?: string;
  
  // If complete
  results?: EligibilityResult[];
  
  // If escalated
  escalationReason?: string;
}

interface EligibilityResult {
  lender: string;
  program: string;
  status: 'eligible' | 'ineligible' | 'conditional' | 'unknown';
  why: string[];           // 2-5 bullets
  whatCouldBreak: string[]; // 1-3 bullets
  sources: SourceCitation[];
}

interface SourceCitation {
  docTitle: string;
  versionLabel: string;
  effectiveDate: string;
  status: 'active' | 'deprecated';
}
```

---

## 7. Security Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      SECURITY LAYERS                             │
├─────────────────────────────────────────────────────────────────┤
│  1. NETWORK                                                      │
│     - Azure VNet for backend services                           │
│     - Private endpoints for Postgres, Redis, Blob               │
│     - WAF on public endpoints (Admin UI, webhooks)              │
├─────────────────────────────────────────────────────────────────┤
│  2. IDENTITY                                                     │
│     - Azure AD for Admin console (AAD groups: LO, Admin)        │
│     - Service Principal for API-to-API                          │
│     - Managed Identity for Azure resources                      │
├─────────────────────────────────────────────────────────────────┤
│  3. DATA                                                         │
│     - Encryption at rest (AES-256, Azure-managed keys)          │
│     - TLS 1.2+ in transit                                       │
│     - PII redaction on ingestion (SSN, DOB, account #)         │
│     - No PII in escalation emails (secure links only)          │
├─────────────────────────────────────────────────────────────────┤
│  4. ACCESS CONTROL                                               │
│     - RBAC: LO sees own threads only                            │
│     - RBAC: Admin sees all + corpus controls                    │
│     - Audit logs append-only                                    │
├─────────────────────────────────────────────────────────────────┤
│  5. SECRETS                                                      │
│     - Azure Key Vault for all credentials                       │
│     - No secrets in code or config files                        │
│     - Rotation policy: 90 days                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 8. Deployment Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    AZURE RESOURCE GROUP                          │
│                    (owly-prod-eastus)                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐                     │
│  │  Container Apps  │  │  Container Apps  │                     │
│  │  Environment     │  │  Environment     │                     │
│  │  (owly-api)      │  │  (owly-ingestion)│                     │
│  │  - min: 1        │  │  - min: 0        │                     │
│  │  - max: 10       │  │  - max: 5        │                     │
│  └──────────────────┘  └──────────────────┘                     │
│           │                     │                                │
│           └─────────┬───────────┘                                │
│                     ▼                                            │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Azure Virtual Network                        │   │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────────────┐   │   │
│  │  │ PostgreSQL │ │   Redis    │ │  Blob Storage      │   │   │
│  │  │ (private)  │ │ (private)  │ │  (private endpoint)│   │   │
│  │  └────────────┘ └────────────┘ └────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐                     │
│  │  Static Web App  │  │  Bot Service     │                     │
│  │  (owly-admin)    │  │  (Teams bot)     │                     │
│  └──────────────────┘  └──────────────────┘                     │
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐                     │
│  │  Key Vault       │  │  App Insights    │                     │
│  └──────────────────┘  └──────────────────┘                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

External:
- Azure OpenAI (same region)
- Cohere Rerank API
- Azure Document Intelligence
```

---

## 9. Key Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Monolith vs Microservices** | Modular monolith (Phase 1) | Faster iteration, split later |
| **Vector DB** | pgvector (in Postgres) | Avoid extra service for 300 docs |
| **LLM provider** | Azure OpenAI | Enterprise SLA, same region, low latency |
| **PDF extraction** | Azure Doc Intelligence | Best for tables, matrices |
| **Reranker** | Cohere Rerank | Best quality/cost, simple API |
| **Queue** | Azure Service Bus | Reliable, dead-letter, native |
| **Admin UI framework** | Next.js | Fast, SSR, good DX |
| **Confidence calc** | Code-based (not LLM) | Deterministic, auditable |
| **Human-in-the-loop** | Required for matrices | PRD non-negotiable |

---

## 10. Next Steps

1. **Resolve Open Questions** (Section 17 of PRD)
2. **Set up Azure resources** (Terraform/Bicep)
3. **Scaffold repos** (owly-api, owly-admin)
4. **M1 Sprint** — Outlook + Teams channel adapters
5. **Golden Set** — Start collecting 20 Q/A pairs NOW

---

*Document: /projects/owly/docs/ARCHITECTURE.md*
