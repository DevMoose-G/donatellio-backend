import signal
import sys

from redis import Redis
from rq import Queue, Worker

from donna_common.settings import settings

# maybe should separate one day
listen_queues = ["jobs"]


def main():
    # 1) Restore default Ctrl+C/TERM behavior
    signal.signal(signal.SIGINT, signal.default_int_handler)
    signal.signal(signal.SIGTERM, signal.default_int_handler)

    # 2) Point at your Redis server
    conn = Redis.from_url(settings.redis_url)

    # 3) Let RQ know you’re using this connection
    # 4) Turn each queue name into a Queue object
    queues = [Queue(name, connection=conn) for name in listen_queues]
    # 5) Spin up the worker
    worker = Worker(queues)
    worker.work()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Worker interrupted. Shutting down...")
        sys.exit(0)
