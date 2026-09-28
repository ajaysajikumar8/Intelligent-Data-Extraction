"""
Static registry of system-provided templates for the Template Library.
These are not stored in the database to prevent polluting tenant data.
When a user "adds" one to their workspace, a copy is inserted into the DB.
"""

from typing import Any, Dict

LIBRARY_TEMPLATES: list[Dict[str, Any]] = [
    {
        "slug": "standard-invoice",
        "name": "Standard Invoice",
        "description": "Extracts common fields from standard invoices.",
        "schema": {
            "vendor_name": "string",
            "invoice_number": "string",
            "date": "string",
            "total_amount": "number",
            "tax_amount": "number",
            "line_items": "array of objects with description, quantity, price"
        }
    },
    {
        "slug": "expense-receipt",
        "name": "Expense Receipt",
        "description": "Extracts vendor, total, and date for expense tracking.",
        "schema": {
            "merchant_name": "string",
            "date": "string",
            "total_amount": "number",
            "currency": "string"
        }
    },
    {
        "slug": "resume-cv",
        "name": "Resume / CV",
        "description": "Extracts candidate details from resumes.",
        "schema": {
            "candidate_name": "string",
            "email": "string",
            "phone": "string",
            "education": "array of objects with degree, institution, year",
            "skills": "array of strings",
            "years_of_experience": "number"
        }
    },
    {
        "slug": "business-card",
        "name": "Business Card",
        "description": "Extracts contact info from business cards.",
        "schema": {
            "person_name": "string",
            "company_name": "string",
            "job_title": "string",
            "email": "string",
            "phone_number": "string",
            "website": "string"
        }
    }
]

def get_library_template(slug: str) -> Dict[str, Any] | None:
    for t in LIBRARY_TEMPLATES:
        if t["slug"] == slug:
            return t
    return None
