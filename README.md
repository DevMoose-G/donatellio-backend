 Stop-Process -Name "python"

## Setup
do pip install -r requirements.txt
create a static folder in the 1st donatellio folder (so donatellio/static)
Setup postgres database
In whatever directory your .env file is in, run `fastapi dev ./donatellio/api/main.py`

## Project Overview

This project implements a scalable, provider-agnostic inference API using FastAPI, Redis (as a broker), RQ (Redis Queue), custom GPU providers (RunPod & Lambda Labs), and PostgreSQL (via SQLAlchemy). The architecture separates concerns into modular services for ease of development, testing, and deployment.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Service Breakdown](#service-breakdown)
   - [FastAPI Server](#fastapi-server)
   - [Task Queue & Workers (Redis + RQ)](#task-queue--workers-redis--rq)
   - [GPU Providers](#gpu-providers)
   - [PostgreSQL Database](#postgresql-database)
3. [Configuration](#configuration)
4. [Setup & Installation](#setup--installation)
5. [Running Locally](#running-locally)
6. [Deployment](#deployment)
7. [Notes & Tips](#notes--tips)

---

## Prerequisites

- Python 3.9+
- Docker (for local services)
- Redis server
- PostgreSQL server
- API keys for RunPod and Lambda Labs
- OpenAI API key (if using OpenAI alongside custom models)

---

## Service Breakdown

### FastAPI Server

1. **Purpose**: Expose REST endpoints for both OpenAI and custom-model inference.
2. **Key Steps**:
   - Create `app/main.py` with FastAPI instance.
   - Define endpoints:
     - `/v1/chat` for proxying to OpenAI.
     - `/custom-model` to enqueue jobs (returns job ID).
   - Integrate dependency injection for settings, DB session, and queue client.

### Task Queue & Workers (Redis + RQ)

1. **Purpose**: Handle asynchronous, long-running custom-model inference jobs.
2. **Key Steps**:
   - Install `rq` and `redis` Python packages.
   - Create `worker.py` to listen for jobs:
     ```python
     from rq import Worker, Queue, Connection
     from redis import Redis

     redis_conn = Redis.from_url(settings.redis_url)
     q = Queue("inference", connection=redis_conn)

     if __name__ == "__main__":
         with Connection(redis_conn):
             Worker([q], default_worker_ttl=3600).work()
     ```
   - Define a task function in `tasks.py`:
     ```python
     def run_custom_inference(job_id, payload, provider_name):
         # spin up instance, run inference, store result, teardown
         pass
     ```
   - Enqueue tasks in FastAPI endpoint:
     ```python
     from rq import Queue
     q = Queue("inference", connection=redis_conn)
     job = q.enqueue("tasks.run_custom_inference", job_id, payload, provider_name)
     ```

### GPU Providers

1. **Purpose**: Abstract spinning up/down GPU instances on RunPod & Lambda Labs.
2. **Key Steps**:
   - Define `providers/base.py`:
     ```python
     from abc import ABC, abstractmethod

     class GPUProvider(ABC):
         @abstractmethod
         def start_instance(self, image: str) -> str: ...
         @abstractmethod
         def wait_until_ready(self, instance_id: str): ...
         @abstractmethod
         def run_inference(self, instance_id: str, payload: dict) -> dict: ...
         @abstractmethod
         def stop_instance(self, instance_id: str): ...
     ```
   - Implement `providers/runpod.py` and `providers/lambdalabs.py` using each service’s REST API.
   - Register providers in a factory or via dependency injection.

### PostgreSQL Database

1. **Purpose**: Persist user requests, job metadata, and inference results.
2. **Key Steps**:
   - Install `sqlalchemy` and `asyncpg`.
   - Create `models.py`:
     ```python
     from sqlalchemy.ext.declarative import declarative_base
     from sqlalchemy import Column, String, JSON, TIMESTAMP

     Base = declarative_base()

     class InferenceJob(Base):
         __tablename__ = "inference_jobs"
         id = Column(String, primary_key=True)
         payload = Column(JSON)
         response = Column(JSON, nullable=True)
         status = Column(String)
         created_at = Column(TIMESTAMP)
         updated_at = Column(TIMESTAMP)
     ```
   - Configure `database.py`:
     ```python
     from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
     from sqlalchemy.orm import sessionmaker

     engine = create_async_engine(settings.db_url)
     AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
     ```
   - Use FastAPI dependencies to inject `AsyncSession` into routes and tasks.

---

## Configuration

- Create a `.env` file with:
  ```ini
  REDIS_URL=redis://localhost:6379/0
  DATABASE_URL=postgresql+asyncpg://user:pass@localhost/db
  RUNPOD_API_KEY=your_runpod_key
  LAMBDALABS_API_KEY=your_lambda_key
  OPENAI_API_KEY=your_openai_key
  DEFAULT_PROVIDER=runpod
  ```
- Load variables using Pydantic’s `BaseSettings`.

---

## Setup & Installation

1. Clone the repo:
   ```bash
   git clone https://github.com/your-org/your-repo.git
   cd your-repo
   ```
2. Create a virtual environment:
   ```bash
   python -m venv venv && source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Apply database migrations (with Alembic):
   ```bash
   alembic upgrade head
   ```
5. Ensure Redis & PostgreSQL are running (via Docker Compose or local installs).

---

## Running Locally

1. **Start Redis & PostgreSQL** (e.g., `docker-compose up -d redis postgres`).
2. **Launch Worker**:
   ```bash
   python worker.py
   ```
3. **Run FastAPI**:
   ```bash
   uvicorn app.main:app --reload
   ```
4. **Test Endpoints** via `curl` or Postman:
   - `POST /v1/chat` → proxy to OpenAI
   - `POST /custom-model` → enqueue job

---

## Deployment

- **Containerize** each component (FastAPI, worker) with Docker.
- Use a managed Redis & PostgreSQL in production.
- Run workers in an autoscaling group (to handle spikes).
- Monitor with Prometheus/Grafana and set alerts for job failures.

---

## Notes & Tips

- Trim Redis Streams or RQ registries regularly to prevent memory bloat.
- Use exponential backoff and retries for provider API calls.
- Secure all endpoints with API keys or OAuth.
- Log job lifecycle events into your preferred logging service (e.g., ELK).

