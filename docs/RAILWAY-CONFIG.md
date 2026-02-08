# Owly Railway Configuration

## Project Info

| Key | Value |
|-----|-------|
| **Project ID** | `65b09e33-9d92-4f61-9acb-25e020f35b3a` |
| **Environment ID** | `c30e37d6-7687-40a9-8a47-29ed481a6960` |
| **Project URL** | https://railway.app/project/65b09e33-9d92-4f61-9acb-25e020f35b3a |

## Services

| Service | ID | Purpose |
|---------|-----|---------|
| `owly-db` | `8ec53654-3a0b-4391-af40-9c9f69286408` | PostgreSQL + pgvector |
| `owly-redis` | `a71c5120-702a-461a-a8cb-bb4b539276f7` | Redis cache |
| `owly-api` | `cae744d0-af8e-40f6-bdf4-a50f6bdc7db2` | FastAPI backend |
| `owly-web` | `66d57e62-1391-4889-8ae2-dcfa29d799f9` | Next.js frontend |

## Setup Steps (Manual via Railway Dashboard)

### 1. Configure PostgreSQL (`owly-db`)

1. Go to Railway Dashboard → owly project → owly-db service
2. Click "Add Database" → Select "PostgreSQL"
3. Or use Docker image: `pgvector/pgvector:pg16`
4. After creation, note the `DATABASE_URL`

### 2. Configure Redis (`owly-redis`)

1. Go to owly-redis service
2. Click "Add Database" → Select "Redis"
3. After creation, note the `REDIS_URL`

### 3. Deploy API (`owly-api`)

1. Go to owly-api service
2. Connect to GitHub repo OR use Docker deploy
3. Set root directory: `/api`
4. Add environment variables:
   ```
   DATABASE_URL=${{owly-db.DATABASE_URL}}
   REDIS_URL=${{owly-redis.REDIS_URL}}
   OPENAI_API_KEY=sk-...
   JWT_SECRET=<generate-secure-secret>
   CORS_ORIGINS=["https://owly-web-production.up.railway.app"]
   ```
5. Deploy

### 4. Deploy Web (`owly-web`)

1. Go to owly-web service
2. Connect to GitHub repo OR use Docker deploy
3. Set root directory: `/web`
4. Add environment variables:
   ```
   NEXT_PUBLIC_API_URL=https://owly-api-production.up.railway.app
   ```
5. Deploy

### 5. Enable pgvector Extension

After PostgreSQL is running, connect and run:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

## Quick Deploy Commands (if using Railway CLI)

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Link to project
railway link 65b09e33-9d92-4f61-9acb-25e020f35b3a

# Deploy API
cd api
railway up --service owly-api

# Deploy Web
cd ../web
railway up --service owly-web
```

## URLs (after deployment)

| Service | URL |
|---------|-----|
| API | `https://owly-api-production-XXXX.up.railway.app` |
| Web | `https://owly-web-production-XXXX.up.railway.app` |
| API Docs | `https://owly-api-production-XXXX.up.railway.app/docs` |

---

*Created: 2026-02-07*
