# Owly Agent — Phase 0 MVP (Railway)

**Objetivo:** Demo funcional para cliente  
**Timeline:** 2-3 semanas  
**Plataforma:** Railway  
**Después:** Migrar a Azure (Phase 1)

---

## 1. Scope Phase 0 (recortado para demo)

### ✅ Incluido
- **Web chat** (testing UI) — más rápido que integrar Outlook/Teams
- **RAG básico** sobre 10-20 PDFs de ejemplo
- **Checklist de campos** (9 campos mínimos)
- **Eligibility output** con citaciones
- **Admin UI mínimo** (upload PDF, ver docs, aprobar reglas)
- **Thumb feedback** (up/down)

### ❌ Excluido (Phase 1)
- Outlook integration
- Teams bot
- WhatsApp
- Escalation workflow completo
- PII redaction avanzado
- Audit logs completos
- Human-in-the-loop verification (simplificado para demo)

---

## 2. Stack Phase 0 (Railway)

| Capa | Tecnología | Servicio Railway |
|------|------------|------------------|
| **API** | FastAPI (Python) | `owly-api` |
| **Database** | PostgreSQL + pgvector | `owly-db` |
| **Storage** | Railway Volume o S3 | (incluido o externo) |
| **Cache** | Redis | `owly-redis` |
| **LLM** | OpenAI API (directo) | - |
| **Embeddings** | OpenAI text-embedding-3-small | - |
| **PDF extraction** | PyMuPDF + pdfplumber | (en API) |
| **Web UI** | Next.js | `owly-web` |
| **Admin UI** | Next.js (mismo app) | (incluido en web) |

**Costo estimado Railway:** ~$20-50/mes (dev tier)

---

## 3. Arquitectura Phase 0

```
┌─────────────────────────────────────────────────────────┐
│                     owly-web                             │
│                  (Next.js on Railway)                    │
│  ┌─────────────────┐  ┌─────────────────────────────┐   │
│  │   Chat UI       │  │   Admin Dashboard           │   │
│  │   /chat         │  │   /admin/*                  │   │
│  └─────────────────┘  └─────────────────────────────┘   │
└────────────────────────────┬────────────────────────────┘
                             │ API calls
                             ▼
┌─────────────────────────────────────────────────────────┐
│                      owly-api                            │
│                   (FastAPI on Railway)                   │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │ Chat Handler │  │ Retrieval    │  │ Rules Engine │   │
│  │ /api/chat    │  │ (pgvector)   │  │ (structured) │   │
│  └──────────────┘  └──────────────┘  └──────────────┘   │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │ Ingestion    │  │ Admin API    │  │ Confidence   │   │
│  │ (PDF→chunks) │  │ /api/admin/* │  │ Calculator   │   │
│  └──────────────┘  └──────────────┘  └──────────────┘   │
└────────────────────────────┬────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
       ┌───────────┐  ┌───────────┐  ┌───────────┐
       │ PostgreSQL│  │   Redis   │  │  OpenAI   │
       │ + pgvector│  │  (cache)  │  │   API     │
       └───────────┘  └───────────┘  └───────────┘
```

---

## 4. Data Model (simplificado Phase 0)

```sql
-- Users (simplified)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    role VARCHAR(20) DEFAULT 'lo', -- lo | admin
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Conversations (web chat)
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    status VARCHAR(20) DEFAULT 'active',
    facts JSONB DEFAULT '{}',
    missing_fields TEXT[],
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id),
    role VARCHAR(20) NOT NULL, -- user | assistant
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Documents
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename VARCHAR(255) NOT NULL,
    lender VARCHAR(255),
    program VARCHAR(255),
    archetype VARCHAR(10), -- A, B, C, D, E
    status VARCHAR(20) DEFAULT 'active', -- draft | active | deprecated
    file_path VARCHAR(500),
    uploaded_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Chunks (vector store)
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    section_path TEXT,
    chunk_index INT,
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX chunks_embedding_idx ON chunks 
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Rules (structured, simplified)
CREATE TABLE rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    lender VARCHAR(255) NOT NULL,
    program VARCHAR(255),
    fico_min INT,
    fico_max INT,
    ltv_max DECIMAL(5,2),
    loan_min DECIMAL(15,2),
    loan_max DECIMAL(15,2),
    purposes TEXT[], -- purchase, refi, cashout
    occupancies TEXT[], -- primary, second, investment
    property_types TEXT[], -- sfr, condo, 2-4unit
    doc_types TEXT[], -- full, bank_statement, dscr
    notes TEXT,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Feedback
CREATE TABLE feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id),
    message_id UUID REFERENCES messages(id),
    thumbs VARCHAR(10), -- up | down
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 5. API Endpoints (Phase 0)

```yaml
# Auth (simplified - email only for demo)
POST /api/auth/login        # {email} → {token, user}

# Chat
POST /api/chat              # {message, conversation_id?} → {response, conversation_id}
GET  /api/conversations     # List user's conversations
GET  /api/conversations/:id # Get conversation with messages

# Feedback
POST /api/feedback          # {message_id, thumbs, reason?}

# Admin - Documents
GET    /api/admin/documents
POST   /api/admin/documents           # Upload PDF (multipart)
DELETE /api/admin/documents/:id
PATCH  /api/admin/documents/:id       # Update status

# Admin - Rules (auto-extracted, editable)
GET    /api/admin/rules
GET    /api/admin/rules/:id
PATCH  /api/admin/rules/:id           # Edit rule
DELETE /api/admin/rules/:id

# Admin - Stats (basic)
GET    /api/admin/stats               # {total_chats, thumbs_up, thumbs_down}
```

---

## 6. Chat Flow (Phase 0)

```python
async def handle_chat(message: str, conversation_id: str | None) -> ChatResponse:
    # 1. Get or create conversation
    conv = await get_or_create_conversation(conversation_id)
    
    # 2. Save user message
    await save_message(conv.id, "user", message)
    
    # 3. Extract/update scenario facts from message
    facts = await extract_facts(message, conv.facts)
    conv.facts = facts
    
    # 4. Check minimum required fields
    missing = get_missing_required_fields(facts)
    
    if missing:
        # 5a. Ask for missing fields
        response = generate_followup_question(missing, facts)
        conv.missing_fields = missing
    else:
        # 5b. Run eligibility check
        # Retrieve relevant chunks
        chunks = await vector_search(build_query(facts), top_k=10)
        
        # Match against structured rules
        matching_rules = await match_rules(facts)
        
        # Generate response with citations
        response = await generate_eligibility_response(
            facts=facts,
            chunks=chunks,
            rules=matching_rules
        )
    
    # 6. Save assistant message
    await save_message(conv.id, "assistant", response)
    await update_conversation(conv)
    
    return ChatResponse(
        message=response,
        conversation_id=conv.id,
        facts=facts,
        missing_fields=missing
    )
```

---

## 7. Required Fields (checklist)

```python
REQUIRED_FIELDS = [
    "state",           # FL, TX, CA, etc.
    "loan_purpose",    # purchase | refi | cashout
    "occupancy",       # primary | second_home | investment
    "property_type",   # sfr | condo | 2-4unit | other
    "loan_amount",     # number
    "ltv",             # percentage
    "fico",            # number or band
    "doc_type",        # full_doc | bank_statement | dscr | etc.
    "credit_events",   # none | bk | foreclosure | short_sale
]

def get_missing_required_fields(facts: dict) -> list[str]:
    return [f for f in REQUIRED_FIELDS if f not in facts or facts[f] is None]
```

---

## 8. Project Structure

```
owly/
├── api/                          # FastAPI backend
│   ├── app/
│   │   ├── main.py              # FastAPI app
│   │   ├── config.py            # Settings
│   │   ├── db.py                # Database connection
│   │   │
│   │   ├── routers/
│   │   │   ├── auth.py
│   │   │   ├── chat.py
│   │   │   ├── admin.py
│   │   │   └── feedback.py
│   │   │
│   │   ├── services/
│   │   │   ├── chat_service.py      # Chat orchestration
│   │   │   ├── retrieval_service.py # Vector search
│   │   │   ├── rules_service.py     # Structured matching
│   │   │   ├── ingestion_service.py # PDF processing
│   │   │   └── llm_service.py       # OpenAI calls
│   │   │
│   │   ├── models/              # Pydantic models
│   │   └── utils/
│   │       ├── extraction.py    # Fact extraction
│   │       └── confidence.py    # Confidence calculation
│   │
│   ├── requirements.txt
│   ├── Dockerfile
│   └── railway.json
│
├── web/                          # Next.js frontend
│   ├── app/
│   │   ├── page.tsx             # Landing / redirect
│   │   ├── chat/
│   │   │   └── page.tsx         # Chat interface
│   │   ├── admin/
│   │   │   ├── page.tsx         # Dashboard
│   │   │   ├── documents/
│   │   │   │   └── page.tsx     # Doc management
│   │   │   └── rules/
│   │   │       └── page.tsx     # Rules grid
│   │   └── api/                 # Next.js API routes (proxy)
│   │
│   ├── components/
│   │   ├── ChatWindow.tsx
│   │   ├── MessageBubble.tsx
│   │   ├── FactsPanel.tsx
│   │   ├── FeedbackButtons.tsx
│   │   ├── DocumentUpload.tsx
│   │   └── RulesGrid.tsx
│   │
│   ├── package.json
│   ├── Dockerfile
│   └── railway.json
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── PHASE-0-MVP.md
│   └── API.md
│
└── README.md
```

---

## 9. Railway Deployment

### Services to create:

| Service | Type | Config |
|---------|------|--------|
| `owly-api` | Docker | Dockerfile in /api |
| `owly-web` | Docker | Dockerfile in /web |
| `owly-db` | PostgreSQL | Railway template |
| `owly-redis` | Redis | Railway template |

### Environment Variables:

```bash
# owly-api
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
OPENAI_API_KEY=sk-...
JWT_SECRET=...
CORS_ORIGINS=https://owly-web-xxx.up.railway.app

# owly-web
NEXT_PUBLIC_API_URL=https://owly-api-xxx.up.railway.app
```

### Deploy commands:

```bash
# Create Railway project
railway login
railway init owly

# Add services
railway add --service owly-api
railway add --service owly-web
railway add --database postgres --name owly-db
railway add --database redis --name owly-redis

# Deploy
railway up --service owly-api
railway up --service owly-web
```

---

## 10. Demo Flow (for client)

### Demo Script:

1. **Show Admin Console**
   - Upload 3-5 sample PDFs
   - Show auto-extracted rules
   - Show document list with status

2. **Show Chat Interface**
   - Start new conversation
   - Agent asks for missing fields (state, FICO, etc.)
   - User provides scenario details
   - Agent returns eligibility with citations

3. **Show Eligibility Output**
   - Top 3 eligible lenders/programs
   - "Why" bullets with rule references
   - "What could break" warnings
   - Source citations (doc + effective date)

4. **Show Feedback**
   - Thumbs up/down on response
   - Admin can see feedback in dashboard

---

## 11. Timeline Phase 0

| Week | Deliverable |
|------|-------------|
| **W1** | API scaffold + DB + basic chat flow |
| **W1** | PDF ingestion + chunking + embeddings |
| **W2** | Retrieval + rules matching + eligibility output |
| **W2** | Web chat UI + admin dashboard |
| **W3** | Polish + deploy Railway + demo prep |

**Total: 2-3 semanas**

---

## 12. Migration Path → Phase 1 (Azure)

Lo que se reutiliza:
- ✅ FastAPI codebase (99%)
- ✅ Next.js frontend (95%)
- ✅ Data model (100%)
- ✅ Business logic (100%)

Lo que cambia:
- 🔄 PostgreSQL → Azure PostgreSQL Flex
- 🔄 Redis → Azure Cache for Redis
- 🔄 Railway → Azure Container Apps
- 🔄 OpenAI direct → Azure OpenAI
- ➕ Add Outlook/Teams integrations
- ➕ Add Azure Document Intelligence
- ➕ Add proper auth (Azure AD)
- ➕ Add escalation workflow
- ➕ Add PII redaction

**Migración estimada: 1-2 semanas adicionales**

---

## 13. Sample PDFs Needed for Demo

Necesitamos 10-20 PDFs representativos:

- 3-5 **Eligibility Matrices** (Archetype A) — con tablas FICO/LTV
- 3-5 **Program Guides** (Archetype B) — bullets, overlays
- 2-3 **State Licensing** (Archetype E) — allowed states
- 2-3 **Announcements** (Archetype D) — optional

**Pregunta para el equipo:** ¿Pueden proporcionar estos PDFs de ejemplo?

---

*Document: /projects/owly/docs/PHASE-0-MVP.md*
