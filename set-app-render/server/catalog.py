"""Catalog templates: REMOVED 2026-11-06 per Ovi.

The 3 catalog templates (Long Sleeve Tee, Classic Long Sleeve,
V-neck) were taken out of the app: Ovi does not want the app
connected with that print-on-demand service at all. The new
products come from Cat Kiss Fish instead, and nothing is created
through that service. The app is standalone: it works with
Shopify store products and designs the seller uploads; the generic
garment-outline PNGs in static/design-area-templates/ (used by
designAreaTemplateUrl for any product of that type) are not catalog
data and stay.

This module is kept as a stub so the rest of the app keeps importing
from it: TEMPLATES is empty and get_template always returns None.
The catalog endpoints (/api/catalog/templates and
/api/sets/<sid>/catalog-templates) are gone and now 404.
"""

TEMPLATES = []


def get_template(product_id):
    """No catalog templates exist, so nothing matches, ever."""
    return None
