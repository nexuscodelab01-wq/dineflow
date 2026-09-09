# DineFlow

Restaurant ordering and management platform — a full-stack SaaS-style application for customer ordering and restaurant operations.

## Overview

DineFlow provides:

- **Customer app** — browse menu, customize items, cart, checkout, order tracking
- **Restaurant admin** — menu, orders, kitchen display, tables, customers, analytics, settings
- **Role-based access** — Customer, Restaurant Staff, Restaurant Admin, Super Admin

## Technology Stack

| Layer | Technology |
|-------|------------|
| Frontend | Nuxt 4, Vue 3, TypeScript, Pinia, Tailwind CSS |
| Backend | Python 3.12+, FastAPI, Pydantic, SQLAlchemy 2.x, Alembic |
| Database | PostgreSQL |
| Auth | JWT (access + refresh), role-based authorization |
| Infra | Docker, Docker Compose, GitHub Actions |
| Tests | Vitest (frontend), Pytest (backend) |

## Architecture

```
frontend/   → Nuxt 4 customer + admin UI
backend/    → FastAPI REST API (/api/v1)
postgres    → PostgreSQL via Docker Compose
```

Layered backend: routes → services → repositories → models.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (provides `docker` and `docker compose`)
- (Optional local dev) Node.js 22+, Python 3.12+, PostgreSQL 16

## Quick Start (Docker — development)

```bash
# 1. Configure environment
cp .env.example .env

# 2. Start all services (hot reload + auto-seed)
docker compose up --build
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| OpenAPI docs | http://localhost:8000/docs |
| Health check | http://localhost:8000/api/v1/health |

Development Compose mounts source code, runs Nuxt dev mode, and seeds the database on startup.

## Production (Docker)

Use the production stack for a built, non-reload deployment:

```bash
cp .env.example .env
# Edit .env: set POSTGRES_PASSWORD, JWT_SECRET, JWT_REFRESH_SECRET, CORS_ORIGINS, NUXT_PUBLIC_API_URL

# First deploy only — load demo restaurant data
RUN_SEED=true docker compose -f docker-compose.prod.yml up --build -d

# Subsequent deploys
docker compose -f docker-compose.prod.yml up --build -d
```

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Local development (reload, volumes, seed) |
| `docker-compose.prod.yml` | Production (built images, workers, no bind mounts) |
| `backend/Dockerfile.prod` | FastAPI image with migrations entrypoint |
| `frontend/Dockerfile.prod` | Multi-stage Nuxt build + Node server |

**Important:** `NUXT_PUBLIC_API_URL` is baked into the frontend at **build time**. Set it to the URL browsers use to reach the API (e.g. `https://api.yourdomain.com`), not an internal Docker hostname.

### Deploying to a VPS (outline)

1. Install Docker on the server.
2. Clone the repository and configure `.env` with production secrets.
3. Point your domain(s) at the server; terminate TLS with a reverse proxy (Caddy, Nginx, or Traefik).
4. Proxy `/` → frontend (`:3000`) and `/api` or a subdomain → backend (`:8000`).
5. Run `docker compose -f docker-compose.prod.yml up --build -d`.
6. Set `RUN_SEED=true` only on the first run if you want demo data.

## CI/CD

GitHub Actions workflow: [`.github/workflows/ci.yml`](.github/workflows/ci.yml)

On every push/PR to `main` or `master`:

- **Backend** — migrations + pytest against PostgreSQL 16
- **Frontend** — Vitest + Nuxt production build
- **Docker** — builds production images to catch Dockerfile regressions

Add branch protection requiring the CI workflow to pass before merge.

## Environment Variables

See [`.env.example`](.env.example). Key variables:

- `DATABASE_URL` — PostgreSQL connection string
- `JWT_SECRET` / `JWT_REFRESH_SECRET` — token signing secrets
- `CORS_ORIGINS` — allowed frontend origins
- `NUXT_PUBLIC_API_URL` — frontend API base URL

Never commit a real `.env` file.

## Local Development (without Docker for apps)

### Database

```bash
docker compose up postgres -d
```

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
# Use localhost in DATABASE_URL when running outside Compose
export DATABASE_URL=postgresql+psycopg://dineflow:dineflow_dev_password@localhost:5432/dineflow
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Database Migrations

```bash
cd backend
alembic upgrade head          # apply migrations
alembic revision --autogenerate -m "description"  # new migration
```

## Seed Data

```bash
cd backend
DATABASE_URL=postgresql+psycopg://dineflow:dineflow_dev_password@localhost:5432/dineflow python -m app.db.seed
```

### Demo credentials

All demo accounts use password: **`Demo1234!`**

| Role | Email |
|------|-------|
| Super Admin | superadmin@dineflow.demo |
| Restaurant Admin | admin@bellavista.demo |
| Restaurant Staff | staff@bellavista.demo |
| Customer | customer1@demo.com |

Demo restaurant: **Bella Vista Kitchen** (`bella-vista-kitchen`) with 10 categories, 32 menu items, modifiers, 11 tables, and sample orders.

## Testing

```bash
# Backend
cd backend && pytest

# Frontend
cd frontend && npm run test
```

## API Documentation

With the backend running, open [http://localhost:8000/docs](http://localhost:8000/docs) for interactive OpenAPI docs.

## Project Status

**Phase 7 — Deployment** complete: production Docker Compose stack, production Dockerfiles, GitHub Actions CI, and deployment documentation.

All planned phases (1–7) are implemented.

## Future Improvements

- Real payment provider integration (Stripe)
- Multi-restaurant SaaS onboarding
- Email/SMS order notifications
- Real-time kitchen updates (WebSockets)
- Platform super-admin UI
- E2E tests (Playwright)

## License

Private / portfolio project.
