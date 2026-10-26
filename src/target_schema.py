"""The clean format we want every legacy file to end up in.

Think of this as the "import template" a new system expects. Each field has a
type, whether it's required, and a plain-English description. The description
is what the LLM reads when deciding which messy column belongs where.
"""

TARGET_SCHEMA = {
    "invoice_number": {
        "type": "string",
        "required": True,
        "description": "Unique ID of the invoice, e.g. INV-1001.",
    },
    "customer_name": {
        "type": "string",
        "required": True,
        "description": "Name of the customer company or person being billed.",
    },
    "customer_email": {
        "type": "email",
        "required": False,
        "description": "Billing email address for the customer.",
    },
    "invoice_date": {
        "type": "date",
        "required": True,
        "description": "Date the invoice was issued.",
    },
    "due_date": {
        "type": "date",
        "required": False,
        "description": "Date payment is due. Must not be before invoice_date.",
    },
    "amount": {
        "type": "money",
        "required": True,
        "description": "Total invoice amount. Must be greater than zero.",
    },
    "currency": {
        "type": "currency",
        "required": False,
        "description": "Three-letter currency code, e.g. CAD or USD.",
    },
    "status": {
        "type": "string",
        "required": False,
        "description": "Payment status, e.g. Open, Paid, Overdue.",
    },
}

ALLOWED_CURRENCIES = {"CAD", "USD", "GBP", "EUR"}

TARGET_FIELDS = list(TARGET_SCHEMA)
REQUIRED_FIELDS = [f for f, spec in TARGET_SCHEMA.items() if spec["required"]]
