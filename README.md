# AI Employee Studio

No-code style platform to architect AI employees, deploy voice lines (Vapi), and connect channels (Telegram master bot + Supabase).

## Repository layout

| Path | Role |
|------|------|
| `backend/` | FastAPI: health, `/register`, `/webchat`, `/telegram` (AWS App Runner) |
| `frontend/` | Streamlit UI (`app.py`) — point **app.yourdomain.com** here when hosted |

**Domain mapping (recommended)**

- **api.yourdomain.com** → App Runner (or ALB) serving `backend/server.py`
- **app.yourdomain.com** → Streamlit host (see frontend options below)

Avoid hardcoded URLs: set `BACKEND_URL` to your public API origin.

---

## Backend (AWS App Runner)

**Build**

```bash
cd backend
python -m pip install -r requirements.txt
```

**Start (local)**

```bash
python -m uvicorn server:app --host 0.0.0.0 --port 8080
```

**App Runner**

- Configure the service root to the `backend/` directory (or use a Dockerfile that `WORKDIR`s into `backend`).
- Start command: `uvicorn server:app --host 0.0.0.0 --port 8080`
- Set environment variables (see `.env.example`): at minimum `TELEGRAM_MASTER_BOT_TOKEN`, `SUPABASE_URL`, `SUPABASE_KEY`, plus `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` if you use webchat/Claude on the API.

**Health**

- `GET /` → `{"status": "running"}`
- `GET /health` → registry stats (existing behavior)

**Telegram**

- Set webhook to `https://api.yourdomain.com/telegram`

A `Procfile` is included for platforms that honor it: `web: uvicorn server:app --host 0.0.0.0 --port 8080`

**Note:** Webchat with Claude requires the `anthropic` package; install it in the backend image if you use that path (not listed in the minimal backend `requirements.txt` by default).

---

## Frontend

**Local**

```bash
cd frontend
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

The app reads `BACKEND_URL` (or legacy `WEBHOOK_SERVER_URL`) and calls `GET {BACKEND_URL}/` and `POST {BACKEND_URL}/register` after deploy.

### Deployment options

**A — Streamlit Community Cloud (simplest)**  
Connect the repo, set app path to `frontend/app.py`, add secrets matching `.env.example`.

**B — AWS (Streamlit on compute)**  
Streamlit needs a long-lived Python process; **S3 + CloudFront alone** serve static sites only. Host Streamlit on **ECS Fargate**, **EC2**, or **App Runner** (with a Streamlit start command), then put **CloudFront** in front for **app.yourdomain.com** if desired.

**C — Static SPA later**  
Replace Streamlit with a React/Vite build, upload `dist/` to S3, serve via CloudFront at **app.yourdomain.com**; call **api.yourdomain.com** for APIs.

---

## Environment variables

Copy `.env.example` to `.env` at the **repository root** (both backend and frontend load it when run from typical layouts). See template for `TELEGRAM_MASTER_BOT_TOKEN`, `SUPABASE_URL`, `SUPABASE_KEY`, `BACKEND_URL`.

---

## Monorepo local install

From repo root:

```bash
python -m pip install -r requirements.txt
```
