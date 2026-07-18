import logging
import time

from backend.app.core.logging import configure_logging
from backend.app.db.session import engine
from backend.app.observability.tracing import configure_tracing
from backend.app.retry_scheduler.service import RetryScheduler

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging()

    configure_tracing(
        engine=engine,
    )

    scheduler = RetryScheduler()

    logger.info("retry_scheduler_started")

    while True:
        try:
            scheduler.run_once()
        except Exception as exc:
            logger.exception(
                "retry_scheduler_iteration_failed",
                extra={
                    "error": str(exc),
                },
            )

        time.sleep(5)


if __name__ == "__main__":
    main()