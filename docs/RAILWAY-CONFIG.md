# Owly Railway Configuration

**Status:** 🚀 DEPLOYED  
**Updated:** 2026-02-08

## Project Info

| Key | Value |
|-----|-------|
| **Project ID** | `65b09e33-9d92-4f61-9acb-25e020f35b3a` |
| **Environment ID** | `c30e37d6-7687-40a9-8a47-29ed481a6960` |
| **Dashboard** | https://railway.app/project/65b09e33-9d92-4f61-9acb-25e020f35b3a |
| **GitHub Repo** | https://github.com/rojasjuniore/owly |

## Services

| Service | ID | Image/Source | URL |
|---------|-----|--------------|-----|
| `owly-api` | `cae744d0-af8e-40f6-bdf4-a50f6bdc7db2` | GitHub /api | https://owly-api-production.up.railway.app |
| `owly-web` | `66d57e62-1391-4889-8ae2-dcfa29d799f9` | GitHub /web | https://owly-web-production.up.railway.app |
| `owly-db` | `8ec53654-3a0b-4391-af40-9c9f69286408` | pgvector/pgvector:pg16 | (internal) |
| `owly-redis` | `a71c5120-702a-461a-a8cb-bb4b539276f7` | redis:7-alpine | (internal) |

## URLs

| Service | URL |
|---------|-----|
| **Web App** | https://owly-web-production.up.railway.app |
| **API** | https://owly-api-production.up.railway.app |
| **API Docs** | https://owly-api-production.up.railway.app/docs |
| **Health Check** | https://owly-api-production.up.railway.app/health |

## Environment Variables

### owly-api
| Variable | Value |
|----------|-------|
| `DATABASE_URL` | `postgresql+asyncpg://owly:***@owly-db.railway.internal:5432/owly` |
| `REDIS_URL` | `redis://owly-redis.railway.internal:6379` |
| `OPENAI_API_KEY` | `sk-proj-***` |
| `JWT_SECRET` | `owly-jwt-secret-2026-phase0-mvp` |
| `CORS_ORIGINS` | `["https://owly-web-production.up.railway.app"]` |

### owly-web
| Variable | Value |
|----------|-------|
| `NEXT_PUBLIC_API_URL` | `https://owly-api-production.up.railway.app` |

### owly-db
| Variable | Value |
|----------|-------|
| `POSTGRES_USER` | `owly` |
| `POSTGRES_PASSWORD` | `Owly2026Secure` |
| `POSTGRES_DB` | `owly` |

## Database

- **Image:** pgvector/pgvector:pg16
- **Volume:** `/var/lib/postgresql/data` (a7ab6dec-72d9-42d4-b283-72749e4f0cb0)
- **Extension:** pgvector (auto-installed)

### Connection String (internal)
```
postgresql://owly:Owly2026Secure@owly-db.railway.internal:5432/owly
```

### Enable pgvector (run once after first deploy)
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

## Deployment Flow

1. Push to `main` branch on GitHub
2. Railway auto-detects and builds
3. API builds from `/api/Dockerfile`
4. Web builds from `/web/Dockerfile`
5. Services restart with new images

## Monitoring

- Railway dashboard: Build logs, metrics, logs
- Health endpoint: `/health`
- API docs: `/docs`

---

*Last updated: 2026-02-08*
