# AI Finance Controller — Reconciliation Agent

Multi-source financial reconciliation: matching transaction records across an internal order ledger, a payment gateway settlement report, and a bank statement to verify money moved correctly.

Built for the AI Finance Controller hackathon track.

## Project Structure

```
├── backend/              FastAPI REST layer
├── src/                  Core pipeline (matcher, scoring, explanations, grading)
├── frontend/             Vite + React + TypeScript dashboard
├── data/                 Input CSVs and ground truth
├── output/               Generated match reports
├── Dockerfile            Backend container (Python 3.12-slim)
├── docker-compose.yml    Orchestrates backend + frontend
└── requirements.txt      Python dependencies
```

## Running with Docker

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) installed on your machine.
- A Groq API key (get one at https://console.groq.com/keys).

### Setup

1. **Create your `.env` file** from the template:

   ```bash
   cp .env.example .env
   ```

2. **Edit `.env`** and fill in your real Groq API key:

   ```
   GROQ_API_KEY=gsk_your_actual_key_here
   GROQ_MODEL=qwen/qwen3.8-27b
   ```

### Build and Run

```bash
docker-compose up --build
```

This builds both containers and starts the services. On first run it takes a few minutes to install dependencies.

### Access

| Service  | URL                     | What it is                           |
|----------|-------------------------|--------------------------------------|
| Frontend | http://localhost:8080   | React dashboard                      |
| Backend  | http://localhost:8000   | FastAPI REST API                     |
| Swagger  | http://localhost:8000/docs | Interactive API documentation     |

### Tear Down

```bash
docker-compose down          # Stop containers (preserves output/ data)
docker-compose down -v       # Stop and remove volumes (clean slate)
```

### Running from Published Images (no build required)

If you only want to run the project (e.g. for a demo or evaluation) and don't need to modify any source code, you can pull the pre-built images directly from Docker Hub. **This requires only Docker — no Node.js, no Python, no cloning the repository.**

1. **Create a `.env` file** with your Groq API key (the only file you need to create locally):

   ```
   GROQ_API_KEY=gsk_your_actual_key_here
   GROQ_MODEL=qwen/qwen3.8-27b
   ```

2. **Download `docker-compose.prod.yml`** from this repository (this is the only project file you need).

3. **Start the services:**

   ```bash
   docker-compose -f docker-compose.prod.yml up
   ```

4. **Open the dashboard** at http://localhost:8080.

To stop: `docker-compose -f docker-compose.prod.yml down` (add `-v` to also remove saved data).

> **Key difference:** `docker-compose.yml` builds images from source (for development / making changes). `docker-compose.prod.yml` pulls ready-made images from Docker Hub (for running the finished project with no source code needed).

### How It Works

- **Backend** (`Dockerfile` at project root): Python 3.12-slim image with the FastAPI app and the `src/` pipeline code. Loads `GROQ_API_KEY` and `GROQ_MODEL` from the `.env` file at runtime.
- **Frontend** (`frontend/Dockerfile`): Multi-stage build — Node 22 builds the Vite bundle, then nginx serves the static output. Nginx reverse-proxies `/api/*` to the backend container by service name, so the browser talks to a single origin (no CORS issues).
- **Networking**: Docker Compose's default bridge network provides DNS resolution between containers. The frontend's nginx uses `proxy_pass http://backend:8000` to route API calls.
- **Persistence**: `output/` and `data/custom/` use Docker named volumes so reconciliation results survive container restarts. Use `docker-compose down -v` to reset.

## Local Development (without Docker)

```bash
# Backend
pip install -r requirements.txt
uvicorn backend.main:app --reload

# Frontend (in a separate terminal)
cd frontend
npm install
npm run dev
```

The Vite dev server on port 5173 proxies `/api` to `http://127.0.0.1:8000` automatically.

## Explanation Modes

The dashboard lets you choose between two explanation modes before running reconciliation:

| | AI Explanations | Instant Explanations |
|---|---|---|
| **How it works** | Generates natural-language explanations via an external LLM API (Groq) | Rule-based engine applies structured, transaction-specific templates |
| **Speed** | ~1-2 minutes for a full batch (rate-limited on free tier) | Completes in seconds |
| **Network** | Requires internet access and a valid Groq API key | No network dependency |
| **Determinism** | Varies slightly between runs (LLM stochasticity) | Same input always produces the same output |
| **Best for** | Final demos, stakeholder-facing reports | Quick iteration, testing, or unreliable API access |

The mode is selected via the toggle in the header before clicking "Run Reconciliation." In both modes, every transaction still gets a specific, non-generic explanation — the difference is phrasing quality and speed. If the AI API is unreachable mid-run, the system silently falls back to rule-based explanations for that batch (so you always get results).
