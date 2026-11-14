
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.erp_invoice import ERPInvoice


class SimulatedERPError(Exception):
    """Raised when the simulated ERP cannot create an invoice."""


class SimulatedERP:
    """A persistent adapter that simulates an external ERP system."""

    provider = "simulated_erp"

    def __init__(self, db: Session):
        self.db = db

    def create_invoice(
        self,
        invoice_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Create an invoice or return an existing matching record."""

        required_fields = [
            "supplier_name",
            "invoice_number",
            "invoice_date",
            "currency",
            "subtotal",
            "vat_amount",
            "total_amount",
        ]

        missing_fields = [
            field
            for field in required_fields
            if invoice_data.get(field) is None
        ]

        if missing_fields:
            raise SimulatedERPError(
                "Missing required ERP invoice fields: "
                f"{', '.join(missing_fields)}"
            )

        supplier_name = invoice_data["supplier_name"].strip()
        invoice_number = invoice_data["invoice_number"].strip()

        if not supplier_name or not invoice_number:
            raise SimulatedERPError(
                "Supplier name and invoice number cannot be empty."
            )

        statement = select(ERPInvoice).where(
            ERPInvoice.supplier_name == supplier_name,
            ERPInvoice.invoice_number == invoice_number,
        )

        existing_invoice = self.db.scalar(statement)

        if existing_invoice is not None:
            return self._build_response(existing_invoice)

        try:
            invoice = ERPInvoice(
                external_record_id=self._generate_external_id(),
                supplier_name=supplier_name,
                invoice_number=invoice_number,
                invoice_date=self._parse_date(
                    invoice_data["invoice_date"]
                ),
                due_date=self._parse_date(
                    invoice_data.get("due_date")
                ),
                currency=invoice_data["currency"],
                subtotal=Decimal(str(invoice_data["subtotal"])),
                vat_amount=Decimal(str(invoice_data["vat_amount"])),
                total_amount=Decimal(str(invoice_data["total_amount"])),
            )

            self.db.add(invoice)
            self.db.commit()
            self.db.refresh(invoice)

            return self._build_response(invoice)

        except Exception:
            self.db.rollback()

            # Another concurrent request may have created this invoice.
            existing_invoice = self.db.scalar(statement)

            if existing_invoice is not None:
                return self._build_response(existing_invoice)

            raise


    def find_invoice(
        self,
        supplier_name: str,
        invoice_number: str,
    ) -> dict[str, Any] | None:
        """Find an existing ERP invoice by supplier and invoice number."""

        statement = select(ERPInvoice).where(
            ERPInvoice.supplier_name == supplier_name.strip(),
            ERPInvoice.invoice_number == invoice_number.strip(),
        )

        invoice = self.db.scalar(statement)

        if invoice is None:
            return None

        return self._build_response(invoice)


    @staticmethod
    def _generate_external_id() -> str:
        from uuid import uuid4

        return f"ERP-INV-{uuid4().hex[:12].upper()}"

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        if value is None:
            return None

        if isinstance(value, datetime):
            return value.date()

        if isinstance(value, date):
            return value

        return date.fromisoformat(value)

    @staticmethod
    def _build_response(invoice: ERPInvoice) -> dict[str, Any]:
        return {
            "success": True,
            "external_record_id": invoice.external_record_id,
            "message": "Invoice successfully created in simulated ERP.",
            "invoice": {
                "supplier_name": invoice.supplier_name,
                "invoice_number": invoice.invoice_number,
                "invoice_date": (
                    invoice.invoice_date.isoformat()
                    if invoice.invoice_date else None
                ),
                "due_date": (
                    invoice.due_date.isoformat()
                    if invoice.due_date else None
                ),
                "currency": invoice.currency,
                "subtotal": str(invoice.subtotal),
                "vat_amount": str(invoice.vat_amount),
                "total_amount": str(invoice.total_amount),
            },
            "created_at": invoice.created_at.isoformat(),
        }
