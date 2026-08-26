# DineFlow

Restaurant ordering and management platform — full-stack SaaS-style demo project.

## Stack

- **Frontend:** Nuxt 4, Vue 3, TypeScript, Pinia, Tailwind CSS
- **Backend:** Python 3.12+, FastAPI, SQLAlchemy, Alembic
- **Database:** PostgreSQL
- **Infra:** Docker Compose

## Project structure

```
frontend/   Nuxt 4 application
backend/    FastAPI REST API
```

## Getting started

```bash
cp .env.example .env
docker compose up --build
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Health check | http://localhost:8000/api/v1/health |
| OpenAPI docs | http://localhost:8000/docs |

## Project status

**Phase 1 — Foundation** in progress: monorepo scaffold, FastAPI health endpoint, and Nuxt landing page.
