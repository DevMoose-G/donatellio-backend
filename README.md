## Setup
do pip install -r requirements.txt
create a static folder in the main directory (so donatellio-backend/static)
Setup postgres database
In whatever directory your .env file is in, run `fastapi dev ./donatellio/api/main.py`

## EC2 Setup
/etc/systemd/system/fastapi.service 
/etc/systemd/system/worker.service 

**Launch Worker**:
   ```bash
   python worker.py
   ```
**Run FastAPI**:
   ```bash
   uvicorn app.main:app --reload
   ```

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

