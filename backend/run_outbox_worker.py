import logging
import time

from app.db.session import SessionLocal
from app.services.local_outbox_processor import (
    process_pending_outbox_messages,
)
from app.services.login_rate_limiter import cleanup_expired_login_attempts
from app.services.erp_integration import recover_stale_integrations

POLL_INTERVAL_SECONDS = 10
LOGIN_ATTEMPT_CLEANUP_INTERVAL_SECONDS = 24 * 60 * 60

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


def main():
    logging.info("Local outbox worker started.")
    last_login_attempt_cleanup = 0.0

    try:
        while True:
            db = SessionLocal()

            try:
                results = process_pending_outbox_messages(
                    db,
                    limit=100,
                )

                recovery_results = recover_stale_integrations(
                    db,
                    stale_after_minutes=10,
                )

                if recovery_results["checked"] or recovery_results["errors"]:
                    logging.info(
                        "ERP recovery completed: checked=%s, recovered=%s, "
                        "retryable=%s, errors=%s",
                        recovery_results["checked"],
                        recovery_results["recovered"],
                        recovery_results["retryable"],
                        recovery_results["errors"],
                    )

                current_time = time.monotonic()

                if (
                    current_time - last_login_attempt_cleanup
                    >= LOGIN_ATTEMPT_CLEANUP_INTERVAL_SECONDS
                ):
                    deleted_count = cleanup_expired_login_attempts(db)

                    logging.info(
                        "Login-attempt cleanup completed: deleted=%s",
                        deleted_count,
                    )

                    last_login_attempt_cleanup = current_time

                if any(results.values()):
                    logging.info(
                        "Processing completed: processed=%s, retried=%s, failed=%s",
                        results["processed"],
                        results["retried"],
                        results["failed"],
                    )

            except Exception:
                db.rollback()
                logging.exception("Outbox worker encountered an error.")

            finally:
                db.close()

            time.sleep(POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        logging.info("Local outbox worker stopped.")


if __name__ == "__main__":
    main()
