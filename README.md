# Donatell.io Backend

Donatell.io turns a single image (or idea) into a game-ready, textured 3D model — no modeling software required. This repo is the backend that powers it: a FastAPI service plus a background worker fleet that takes a user from prompt/image → generated 3D mesh → textured asset, ready to download and drop into a game engine or 3D pipeline.

## Demo

https://github.com/user-attachments/assets/1662aa6f-a330-4b26-99b9-70700a80eca7

## What it does

1. **Image / prompt in** — a user uploads a reference image or describes what they want, optionally refining it through a few quick clarifying questions.
2. **Mesh generation** — the pipeline generates a 3D mesh from that input, running on GPU-backed inference providers (Replicate / RunPod).
3. **Texturing** — the mesh is textured to match the source art style, with Blender used server-side for processing and previews.
4. **Projects & collections** — generated assets, branches, and iterations are organized into projects the user can revisit, remix, and re-export.
5. **Delivery** — finished models and previews are stored and served back to the client (web app at [donatell.io](https://donatell.io)), ready to download.

Long-running generation work (mesh/texture jobs, Blender processing) is offloaded to an asynchronous job queue so the API stays fast and responsive while heavy GPU work happens in the background.

## Architecture

The codebase is split into three packages:

| Package | Responsibility |
|---|---|
| [`donna_api`](donna_api) | FastAPI application — auth, REST endpoints for images, meshes, textures, projects, collections, and jobs, plus billing (Stripe). |
| [`donna_worker`](donna_worker) | Background worker(s) that pick up generation jobs from the queue and drive the mesh/texture pipeline, including Blender-based processing. |
| [`donna_common`](donna_common) | Shared code used by both API and worker: the ORM/data-access layer, Redis/job-queue helpers, and integrations with generation providers (OpenAI, Replicate, RunPod) and storage. |

**Stack:** FastAPI · PostgreSQL (via SQLAlchemy ORM) · Redis + RQ for the job queue · Blender for 3D processing · Stripe for billing · Docker for containerization.

## Getting Started

```bash
pip install -r requirements.txt
```

1. Create a `static` folder in the project root (`donatellio-backend/static`).
2. Set up a PostgreSQL database.
3. From the directory containing your `.env` file, run:

   ```bash
   fastapi dev ./donatellio/api/main.py
   ```

### Running the worker

```bash
rq worker jobs --url redis://localhost:6379 --worker-class rq.worker.SpawnWorker
```

On Windows:

```bash
rq worker jobs --url redis://localhost:6379 -w win_worker.WindowsSimpleWorker
```

Or run the worker script directly:

```bash
python worker.py
```

### Running the API

```bash
uvicorn app.main:app --reload
```

### Stripe webhooks (local)

```bash
stripe listen --forward-to localhost:8000/api/user/pay/processed
```

## EC2 Setup

Systemd units for production deployment:

- `/etc/systemd/system/fastapi.service`
- `/etc/systemd/system/worker.service`

## Deployment

- **Containerize** each component (FastAPI, worker) with Docker.
- Use a managed Redis & PostgreSQL in production.
- Run workers in an autoscaling group to handle demand spikes.
- Monitor with Prometheus/Grafana and set alerts for job failures.

## Notes & Tips

- Trim Redis Streams / RQ registries regularly to prevent memory bloat.
- Use exponential backoff and retries for provider API calls.
- Secure all endpoints with API keys or OAuth.
- Log job lifecycle events into your preferred logging service (e.g., ELK).
