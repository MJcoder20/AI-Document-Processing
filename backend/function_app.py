
import logging

import azure.functions as func

from app.db.session import SessionLocal
from app.services.outbox_dispatcher import (
    dispatch_pending_outbox_messages,
)


app = func.FunctionApp()


@app.timer_trigger(
    schedule="0 */1 * * * *",
    arg_name="timer",
    run_on_startup=False,
    use_monitor=True,
)
def dispatch_outbox_timer(timer: func.TimerRequest) -> None:
    """Publish pending outbox messages every minute."""

    if timer.past_due:
        logging.warning("The outbox dispatcher timer is past due.")

    db = SessionLocal()

    try:
        results = dispatch_pending_outbox_messages(
            db,
            limit=100,
        )

        logging.info(
            "Outbox dispatch completed: published=%s, failed=%s",
            results["published"],
            results["failed"],
        )

    except Exception:
        db.rollback()
        logging.exception("Outbox dispatcher execution failed.")

        raise

    finally:
        db.close()
