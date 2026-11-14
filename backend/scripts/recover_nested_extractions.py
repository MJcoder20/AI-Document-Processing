
import argparse
import copy
import logging
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.document import Document
from app.models.extraction_result import ExtractionResult
from app.services.ai_extraction import extract_invoice_data
from app.services.invoice_validation import validate_invoice


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)

TARGET_DOCUMENTS = {
    UUID("6206c510-dd7b-447b-9f45-28a3a1407569"),
    UUID("dc26d479-797e-454c-a37e-4a3e2713d4d6"),
    UUID("99be6807-050d-41c0-899c-c5950ac66e17"),
}

INVOICE_FIELDS = (
    "supplier_name",
    "invoice_number",
    "invoice_date",
    "due_date",
    "currency",
    "subtotal",
    "vat_amount",
    "total_amount",
    "confidence_score",
)


def json_safe(value):
    """Convert values to JSON-friendly representations."""
    if isinstance(value, Decimal):
        return str(value)

    return value


def main(apply_changes: bool) -> None:
    db = SessionLocal()

    try:
        documents = {
            document.id: document
            for document in db.scalars(
                select(Document).where(
                    Document.id.in_(TARGET_DOCUMENTS)
                )
            ).all()
        }

        if set(documents) != TARGET_DOCUMENTS:
            missing = TARGET_DOCUMENTS - set(documents)
            raise RuntimeError(
                f"Some target documents were not found: {missing}"
            )

        extractions = db.scalars(
            select(ExtractionResult).where(
                ExtractionResult.document_id.in_(TARGET_DOCUMENTS)
            )
        ).all()

        if len(extractions) != len(TARGET_DOCUMENTS):
            raise RuntimeError(
                "Expected exactly one extraction per target document."
            )

        extraction_by_document = {
            extraction.document_id: extraction
            for extraction in extractions
        }

        prepared = []

        # Phase 1: Re-extract every invoice without changing the database.
        for document_id in sorted(TARGET_DOCUMENTS, key=str):
            document = documents[document_id]
            extraction = extraction_by_document[document_id]

            if document.status != "pending_review":
                raise RuntimeError(
                    f"{document.original_filename} has unexpected "
                    f"status: {document.status}"
                )

            original_data = copy.deepcopy(
                extraction.extracted_data or {}
            )

            document_text = original_data.get("text", "")
            tables = original_data.get("tables", [])

            if not isinstance(document_text, str) or not document_text.strip():
                raise RuntimeError(
                    f"Original text is missing for {document_id}."
                )

            if not isinstance(tables, list):
                raise RuntimeError(
                    f"Unexpected tables structure for {document_id}."
                )

            invoice = extract_invoice_data(
                document_text=document_text,
                tables=tables,
            )

            invoice_values = invoice.model_dump()

            if not invoice_values.get("supplier_name"):
                raise RuntimeError(
                    f"AI did not identify supplier for {document_id}."
                )

            if not invoice_values.get("invoice_number"):
                raise RuntimeError(
                    f"AI did not identify invoice number for {document_id}."
                )

            prepared.append(
                {
                    "document": document,
                    "extraction": extraction,
                    "original_data": original_data,
                    "invoice": invoice,
                    "invoice_values": invoice_values,
                }
            )

        # Phase 2: Populate every target record before duplicate validation.
        for item in prepared:
            extraction = item["extraction"]
            invoice = item["invoice"]
            values = item["invoice_values"]

            for field in INVOICE_FIELDS:
                setattr(extraction, field, values.get(field))

            updated_data = copy.deepcopy(item["original_data"])
            updated_data["invoice"] = invoice.model_dump(mode="json")

            # Preserve original text and tables.
            extraction.extracted_data = updated_data

        db.flush()

        # Phase 3: Validate after all target invoice fields are populated.
        for item in prepared:
            extraction = item["extraction"]
            validation = validate_invoice(db, extraction)

            updated_data = copy.deepcopy(extraction.extracted_data)
            updated_data["validation"] = validation
            extraction.extracted_data = updated_data

            item["validation"] = validation

        # Phase 4: Display proposed results.
        print("\nRECOVERY PREVIEW")
        print("=" * 65)

        for item in prepared:
            document = item["document"]
            extraction = item["extraction"]
            validation = item["validation"]

            print(f"\nDocument: {document.original_filename}")
            print(f"ID: {document.id}")
            print(f"Status: {document.status}")
            print(f"Supplier: {extraction.supplier_name}")
            print(f"Invoice: {extraction.invoice_number}")
            print(f"Invoice date: {extraction.invoice_date}")
            print(f"Currency: {extraction.currency}")
            print(f"Subtotal: {extraction.subtotal}")
            print(f"VAT: {extraction.vat_amount}")
            print(f"Total: {extraction.total_amount}")
            print(f"Validation: {validation['status']}")
            print(f"Valid: {validation['is_valid']}")
            print(f"Warnings: {validation['warnings']}")
            print(f"Errors: {validation['errors']}")

        if not apply_changes:
            db.rollback()
            print("\nDRY RUN COMPLETE — no database changes committed.")
            return

        # Phase 5: Commit all three records atomically.
        db.commit()

        print(
            "\nRECOVERY COMMITTED — all three existing extraction "
            "records were updated."
        )

    except Exception:
        db.rollback()
        logging.exception("Recovery failed. Database transaction rolled back.")
        raise

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Safely recover nested invoice extraction records."
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit recovered extraction data. Without this flag, dry-run only.",
    )

    args = parser.parse_args()
    main(apply_changes=args.apply)
