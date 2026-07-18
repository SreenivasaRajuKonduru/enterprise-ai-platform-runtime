import logging
import sys

from backend.app.core.logging import configure_logging
from backend.app.db.session import engine
from backend.app.observability.tracing import configure_tracing
from backend.app.workers.consumer import JobConsumer

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging()

    logger.info(
        "worker_bootstrap_started",
        extra={"python_version": sys.version},
    )

    configure_tracing(
        service_name=None,
        engine=engine,
    )

    logger.info("worker_process_started")

    consumer = JobConsumer()
    consumer.run()


if __name__ == "__main__":
    main()