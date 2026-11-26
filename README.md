# Intervucopilot

Intervucopilot is an AI interview-preparation application with a React website, an Electron desktop app, and a Python backend. It brings resume context, interview sessions, transcription and AI-assisted answers into one workspace.

The repository also contains subscription management, account privacy workflows and role-based administration. Availability depends on the configured environment, account permissions and feature readiness.

## Features

- **Resume and profile:** Upload a resume, review extracted information and use it as preparation context.
- **Interview sessions:** Work with transcripts, generated answers, AI Notes, Ask AI and saved answers.
- **Desktop assistant:** Use supported microphone/system-audio workflows and a separate answer overlay.
- **Screen analysis:** Analyse supported on-screen questions through the configured processing path.
- **Sketch:** Generate architecture diagrams from eligible saved system-design answers in the supported desktop interface. Generation requires separate configuration and entitlement.
- **Subscriptions:** Manage plan definitions, published offers, allowances and supported billing workflows.
- **Account privacy:** Export account data and use approved session/history/account deletion workflows when enabled.
- **Administration:** Access permitted operational metrics, customer metadata, campaigns and administration tools according to role.

Not every feature is enabled in a fresh checkout. A successful build does not configure external services or activate production features.

## Project structure

| Directory | Purpose |
| --- | --- |
| `backend/app/` | FastAPI application, integrations and supporting services |
| `backend/tests/` | Backend and integration verification |
| `frontend/src/` | React website and application interfaces |
| `frontend/electron/` | Electron desktop main process and integrations |
| `frontend/tests/` | Browser, desktop and frontend verification |
| `supabase/migrations/` | Ordered database migrations |
| `browser-extension/` | Browser extension source and checks |
| `docs/` | Architecture, implementation and operational documentation |

## Technology

| Area | Stack |
| --- | --- |
| Website | React, Vite |
| Desktop | Electron |
| Backend | Python, FastAPI |
| Identity and cloud data | Supabase Auth, PostgreSQL, Storage |
| Realtime paths | WebSocket and opt-in gRPC integrations |
| AI and transcription | Configurable provider adapters and supported local paths |
| Verification | pytest, Node tests, Playwright and isolated database tests |

## Local development

### Prerequisites

- Git, Python and Node.js/npm. Repository CI currently uses **Python 3.11** and **Node.js 20**; check compatibility and runtime support when selecting a deployment version.
- The native dependencies required by the selected backend/audio features. Audio processing may require ffmpeg and platform-specific components.
- An isolated, configured Auth/database/Storage environment for cloud features. Docker/local services are needed only for workflows that require them.

The commands below use Windows PowerShell. Run them from the repository root unless otherwise indicated. The current `electron:dev` command is Windows-specific.

### 1. Install dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt

cd frontend
npm ci
cd ..
```

### 2. Configure your local environment

Use [.env.example](.env.example) as a configuration reference. Supply only the credentials and services needed for the features you intend to test. The template is not a production activation profile.

Keep local secrets outside version control. Browser configuration must contain only browser-safe values; never include server credentials in frontend environment variables or distributed bundles. Do not copy another developer's private environment files.

A fresh checkout does not include personal credentials, private execution records or a preconfigured admin login. Cloud and provider-backed features require their own setup. Do not apply migrations to an existing shared project as part of routine local startup.

### 3. Start the backend

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

### 4. Start the website or desktop app

In a second terminal, choose one:

```powershell
cd frontend

# Website development: http://localhost:5173
npm run dev

# Alternatively, Windows desktop development; starts Vite and Electron.
npm run electron:dev
```

Do not run both commands on the same port simultaneously. A Vite page loading successfully does not establish that its backend, authentication or cloud services are available.

## Build and verification

Frontend build, from `frontend/`:

```powershell
npm run build
```

For backend tests, install the test dependencies from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-test.txt
.\.venv\Scripts\python.exe -m pytest backend/tests -q
```

Some suites require additional isolated runtimes or explicit opt-in and may skip without them. A skipped integration test is not acceptance evidence. Follow the relevant test documentation before running native database, browser, installed-app or provider-backed checks.

The [CI workflow](.github/workflows/ci.yml) defines the automated repository checks. Local tests, real-engine integration, installed desktop acceptance and production acceptance are distinct.

## Status and review entry points

This repository contains reviewed implementation work, not an assertion that every production integration is active. Production deployment and feature activation require their documented acceptance and release steps. Payment-provider activity remains separately controlled.

Start a technical review with:

1. [Product implementation roadmap](SAIIA_CLOUD_PRODUCT_IMPLEMENTATION_ROADMAP.md)
2. [Production progress tracker](SAIIA_PRODUCTION_PHASES_TRACKER.md)
3. [Core product requirements](SAIIA_PRODUCTION_PRD_CORE.md)
4. [Technology and architecture](SAIIA_PRODUCTION_TECHSTACK.md)
5. [C15 closure matrix](docs/C15_CLOSURE_MATRIX.md)
6. [C15.5 implementation and acceptance](docs/C15_5_ADMIN_IMPLEMENTATION.md)

Detailed configuration and release procedures belong in their dedicated documentation, not in this public-facing overview. Private accounts, credentials, execution records and environment-specific access instructions are intentionally omitted.
