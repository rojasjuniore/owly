# Owly - Mortgage Eligibility Assistant

🦉 AI-powered multichannel assistant for Mortgage Loan Officers.

## Overview

Owly helps Loan Officers determine lender/program eligibility using RAG over 300+ lender requirement PDFs.

## Phase 0 MVP

This is the Phase 0 MVP for demo purposes.

### Features

- ✅ Web chat interface
- ✅ RAG over sample PDFs
- ✅ Structured rules extraction
- ✅ Eligibility determination with citations
- ✅ Admin dashboard (documents, stats)
- ✅ Thumb feedback

### Stack

| Service | Technology |
|---------|------------|
| API | FastAPI (Python) |
| Web | Next.js 14 |
| Database | PostgreSQL + pgvector |
| Cache | Redis |
| LLM | OpenAI GPT-4o |

## Project Structure

```
owly/
├── api/                    # FastAPI backend
│   ├── app/
│   │   ├── main.py        # App entrypoint
│   │   ├── config.py      # Settings
│   │   ├── db.py          # Database
│   │   ├── models/        # SQLAlchemy models
│   │   ├── routers/       # API endpoints
│   │   └── services/      # Business logic
│   ├── requirements.txt
│   └── Dockerfile
│
├── web/                    # Next.js frontend
│   ├── app/
│   │   ├── page.tsx       # Landing
│   │   ├── chat/          # Chat interface
│   │   └── admin/         # Admin dashboard
│   ├── package.json
│   └── Dockerfile
│
├── data/
│   └── pdfs/              # Sample PDFs
│
└── docs/                   # Documentation
    ├── ARCHITECTURE.md
    ├── PHASE-0-MVP.md
    └── PRD-v1.3.md
```

## Local Development

### Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL with pgvector extension
- Redis

### API Setup

```bash
cd api

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your values

# Run
uvicorn app.main:app --reload
```

### Web Setup

```bash
cd web

# Install dependencies
npm install

# Set environment variables
cp .env.example .env.local
# Edit .env.local with your values

# Run
npm run dev
```

## Railway Deployment

### Create Project

```bash
# Login to Railway
railway login

# Create project
railway init owly

# Add PostgreSQL
railway add --database postgres

# Add Redis
railway add --database redis

# Deploy API
cd api
railway link
railway up

# Deploy Web
cd ../web
railway link
railway up
```

### Environment Variables

**API Service:**
```
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://...
OPENAI_API_KEY=sk-...
JWT_SECRET=your-secret
CORS_ORIGINS=["https://your-web-url.up.railway.app"]
```

**Web Service:**
```
NEXT_PUBLIC_API_URL=https://your-api-url.up.railway.app
```

## API Endpoints

### Chat
- `POST /api/chat` - Send message, get response

### Admin
- `GET /api/admin/documents` - List documents
- `POST /api/admin/documents` - Upload PDF
- `DELETE /api/admin/documents/:id` - Delete document
- `GET /api/admin/rules` - List rules
- `PATCH /api/admin/rules/:id` - Update rule
- `GET /api/admin/stats` - Get statistics

### Feedback
- `POST /api/feedback` - Submit feedback

## Next Steps (Phase 1)

- [ ] Outlook integration
- [ ] Teams bot
- [ ] Escalation workflow
- [ ] PII redaction
- [ ] Human-in-the-loop verification
- [ ] Azure migration

---

Built by Antigravity 🚀
