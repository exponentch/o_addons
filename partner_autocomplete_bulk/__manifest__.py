{
    "name": "Partner Autocomplete Bulk",
    "version": "19.0.1.0.0",
    "summary": "Enrich multiple contacts at once using Odoo's partner autocomplete service",
    "description": """
Partner Autocomplete Bulk
=========================
Enrich multiple contacts at once using Odoo's partner autocomplete and enrichment
service. Select partners from the list view, review exact name matches, and update
their information in bulk. Each enrichment consumes IAP credits.
    """,
    "author": "Exponent",
    "website": "https://www.exponent.ch",
    "category": "Sales",
    "depends": ["base", "contacts", "partner_autocomplete"],
    "data": [
        "security/ir.model.access.csv",
        "data/server_actions_data.xml",
        "wizard/partner_autocomplete_bulk_wizard.xml",
    ],
    "images": ["static/description/banner.png"],
    "application": False,
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
