<div align="center">

# 🏭 Industrial Knowledge Brain

**Real-time IIoT monitoring platform with AI-powered diagnostics**

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.8-3178C6?style=flat-square&logo=typescript)](https://www.typescriptlang.org)
[![TailwindCSS](https://img.shields.io/badge/Tailwind-v4-06B6D4?style=flat-square&logo=tailwindcss)](https://tailwindcss.com)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python)](https://python.org)
[![Gemini](https://img.shields.io/badge/Gemini-AI-8E75B2?style=flat-square&logo=google)](https://ai.google.dev)

</div>

---

## Overview

Industrial Insight Hub (IKB) is a full-stack monorepo for monitoring industrial machinery in real time. It combines a modern React dashboard with a Python REST API, a SQLite database, and a Google Gemini–powered AI assistant that can diagnose machine faults, search the knowledge base, and recommend corrective actions.

| Page | What it does |
|------|-------------|
| **Dashboard** | Live KPIs, vibration chart, machine table, AI insights feed |
| **Machines** | Sensor cards (temp · vibration · RPM · pressure) with a detail drawer |
| **Alerts** | Active / acknowledged / resolved alert queue with one-click actions |
| **Knowledge Base** | Searchable FMEA reports, SOPs, procedures, and incident logs |
| **AI Chat** | Conversational assistant with live sensor context injection |
| **Settings** | Integrations, AI model config, notification preferences |

---

## Repository Layout

```
industrial-insight-hub/
│
├── frontend/                   # React + TanStack Router SPA
│   ├── src/
│   │   ├── routes/             # File-based pages
│   │   │   ├── index.tsx       # Dashboard
│   │   │   ├── machines.tsx    # Machine management
│   │   │   ├── alerts.tsx      # Alert queue
│   │   │   ├── chat.tsx        # AI assistant
│   │   │   ├── knowledge-base.tsx
│   │   │   └── settings.tsx
│   │   ├── components/         # AppShell, StatusBadge, shadcn/ui
│   │   ├── lib/
│   │   │   ├── api.ts          # Typed API client → all backend calls
│   │   │   └── mock-data.ts    # Seed reference (not used at runtime)
│   │   └── styles.css
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── .env                    # VITE_API_URL=http://localhost:8000
│
├── backend/                    # Python FastAPI + SQLite + Gemini
│   ├── main.py                 # App entry, CORS, startup hook
│   ├── database.py             # SQLite engine & session factory
│   ├── models.py               # SQLModel table definitions
│   ├── seed.py                 # Auto-seeds DB on first run
│   ├── routes/
│   │   ├── machines.py         # CRUD + live sensor noise simulation
│   │   ├── alerts.py           # Acknowledge / resolve / add note
│   │   ├── documents.py        # Knowledge base search
│   │   ├── dashboard.py        # KPIs, vibration, insights, activity
│   │   └── chat.py             # Gemini AI with machine context
│   ├── requirements.txt
│   ├── .env.example
│   └── ikb.db                  # SQLite database (auto-created)
│
├── .gitignore
└── README.md
```

---

## Getting Started

### Prerequisites

- **Node.js** ≥ 18 and **npm** ≥ 9
- **Python** ≥ 3.11
- A [Google Gemini API key](https://aistudio.google.com/app/apikey) *(optional — the app runs without it)*

---

### 1. Clone & install

```bash
# Frontend dependencies
cd frontend
npm install
cd ..

# Backend dependencies
pip install -r backend/requirements.txt
```

### 2. Configure environment

```bash
# Backend AI chat (optional)
copy backend\.env.example backend\.env
# Open backend/.env and set:  GEMINI_API_KEY=your_key_here

# Frontend is pre-configured — no changes needed for local dev
# frontend/.env already contains: VITE_API_URL=http://localhost:8000
```

### 3. Run

Open **two terminals** from the repo root:

```bash
# Terminal 1 — Backend API  →  http://localhost:8000
uvicorn backend.main:app --reload --port 8000

# Terminal 2 — Frontend     →  http://localhost:5173
cd frontend && npm run dev
```

> **First run:** the backend auto-creates `backend/ikb.db` and seeds it with
> 6 machines, 3 alerts, 6 documents, 3 AI insights, and vibration time-series.

### 4. Open

| Service | URL |
|---------|-----|
| App | http://localhost:5173 |
| REST API | http://localhost:8000 |
| Interactive API docs | http://localhost:8000/docs |

---

## API Reference

### Machines
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/machines` | List machines — filter with `?status=` `?type=` |
| `GET` | `/api/machines/{id}` | Single machine with live sensor readings |
| `POST` | `/api/machines` | Create a machine |
| `PATCH` | `/api/machines/{id}` | Update machine fields |
| `DELETE` | `/api/machines/{id}` | Remove a machine |

### Alerts
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/alerts` | List alerts — filter with `?status=` `?severity=` `?machine=` |
| `GET` | `/api/alerts/{id}` | Single alert detail |
| `POST` | `/api/alerts/{id}/acknowledge` | Mark as acknowledged |
| `POST` | `/api/alerts/{id}/resolve` | Mark as resolved |
| `POST` | `/api/alerts/{id}/note` | Add a technician note |

### Knowledge Base
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/documents` | Search docs — `?q=keyword` `?category=FMEA` |
| `GET` | `/api/documents/{id}` | Single document |
| `POST` | `/api/documents` | Add document metadata |

### Dashboard
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/dashboard/kpis` | Active machines, alerts, efficiency rate, insight count |
| `GET` | `/api/dashboard/vibration` | Time-series data — `?machine_id=m2` |
| `GET` | `/api/dashboard/insights` | Latest AI insight cards |
| `GET` | `/api/dashboard/activity` | Recent activity feed |

### AI Chat
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/chat` | Send a message, receive a Gemini-powered response |

**Chat request body:**
```json
{
  "message": "Why is CNC Mill #3 vibrating?",
  "machine_id": "m2",
  "history": [
    { "role": "user", "content": "..." },
    { "role": "assistant", "content": "..." }
  ]
}
```

---

## Tech Stack

### Frontend
| | |
|--|--|
| **React 19** | UI library |
| **TypeScript 5** | Type safety |
| **TanStack Router** | File-based routing |
| **TanStack Query** | Server-state caching |
| **Tailwind CSS v4** | Utility-first styling |
| **shadcn/ui** | Component library |
| **Recharts** | Sensor & vibration charts |
| **Framer Motion** | Micro-animations |
| **Lucide Icons** | Icon set |

### Backend
| | |
|--|--|
| **FastAPI** | Async REST framework with auto OpenAPI docs |
| **SQLModel** | Pydantic + SQLAlchemy ORM |
| **SQLite** | Zero-setup database (`ikb.db`) |
| **Google Gemini** | `gemini-2.0-flash` for AI chat |
| **Uvicorn** | ASGI server |

---

## Key Design Decisions

**Live sensor simulation** — Every `GET /api/machines` response adds ±3 % random noise to temperature, vibration, RPM, and pressure values, making the dashboard feel alive without a physical data source.

**Graceful AI fallback** — If `GEMINI_API_KEY` is missing or invalid, the `/api/chat` endpoint returns a helpful stub message. The rest of the application is completely unaffected.

**Typed API client** — `frontend/src/lib/api.ts` provides fully-typed wrappers for every endpoint. All frontend data fetching goes through `api.*` methods, keeping network logic in one place.

**Zero-config database** — SQLite is used by default. To switch to PostgreSQL, change `DATABASE_URL` in `backend/database.py` to a Postgres connection string — no other code changes needed.

---

## Reset the Database

```bash
# Delete the database file and restart — seed runs automatically
del backend\ikb.db
uvicorn backend.main:app --reload --port 8000
```
