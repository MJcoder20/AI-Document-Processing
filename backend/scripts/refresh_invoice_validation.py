import argparse
import json
from uuid import UUID

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.document import Document
from app.models.extraction_result import ExtractionResult
from app.services.invoice_validation import validate_invoice


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Refresh stored invoice validation for one document."
    )
    parser.add_argument("--document-id", required=True, type=UUID)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Save the refreshed validation. Without this flag, perform a dry run.",
    )
    args = parser.parse_args()

    db = SessionLocal()

    try:
        document = db.scalar(
            select(Document).where(Document.id == args.document_id)
        )

        if document is None:
            raise SystemExit("Document not found.")

        extraction = db.scalar(
            select(ExtractionResult)
            .where(ExtractionResult.document_id == document.id)
            .order_by(ExtractionResult.created_at.desc())
            .limit(1)
        )

        if extraction is None:
            raise SystemExit("No extraction found for this document.")

        old_validation = (extraction.extracted_data or {}).get("validation", {})

        new_validation = validate_invoice(
            db=db,
            extraction=extraction,
            document=document,
        )

        print(f"Document: {document.original_filename}")
        print("\nPrevious validation:")
        print(json.dumps(old_validation, indent=2, default=str))

        print("\nRefreshed validation:")
        print(json.dumps(new_validation, indent=2, default=str))

        if args.apply:
            extraction.extracted_data = {
                **(extraction.extracted_data or {}),
                "validation": new_validation,
            }
            db.commit()
            print("\nValidation successfully saved.")
        else:
            db.rollback()
            print("\nDry run only. No database changes were saved.")
            print("Run again with --apply to save the refreshed validation.")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
