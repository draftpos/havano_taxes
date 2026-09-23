"""
havano_taxes.patches.get_item_details_override
=================================================

Replaces ERPNext's whitelisted `get_item_details` endpoint.

WHY
---
When a user adds an item to a Sales Invoice in the browser, ERPNext calls
`erpnext.stock.get_item_details.get_item_details` to fetch defaults including
`item_tax_rate` and `item_tax_template`.  Internally ERPNext uses the
invoice-level `tax_category` to filter which Item Tax row applies, which means
a Zero Rated item on a VAT invoice gets the wrong rate.

HOW THIS FIXES IT
-----------------
This wrapper:
  1. Calls the original ERPNext function unchanged.
  2. After the original returns, calls resolve_item_tax() for the same item.
  3. Overwrites `item_tax_rate` and `item_tax_template` in the result dict
     with the item's own configured values, ignoring the invoice tax_category.

The result is that the browser already has the correct rate before the user
even saves.  The on_validate hook is then the server-side safety net for the
same correction.

REGISTERED IN hooks.py via override_whitelisted_methods.
"""

import json

import frappe
from frappe.utils import flt

from havano_taxes.tax_resolver import resolve_item_tax, build_item_tax_rate_json


@frappe.whitelist()
def get_item_details(args, doc=None, for_validate=False, overwrite_warehouse=True):
    """
    Wrapper around ERPNext's get_item_details that injects item-level
    tax resolution into the returned item_tax_rate / item_tax_template.

    All other fields (price, warehouse, UOM, etc.) come from ERPNext as
    normal — this only touches the tax fields.
    """
    # ----------------------------------------------------------------
    # Step 1 — Call the original ERPNext function
    # ----------------------------------------------------------------
    from erpnext.stock.get_item_details import get_item_details as _original

    out = _original(args, doc=doc, for_validate=for_validate, overwrite_warehouse=overwrite_warehouse)

    # ----------------------------------------------------------------
    # Step 2 — Parse args (may arrive as a JSON string from the client)
    # ----------------------------------------------------------------
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except (json.JSONDecodeError, TypeError):
            return out  # Cannot parse — return original untouched

    item_code = args.get("item_code")
    company   = args.get("company")

    if not item_code or not company:
        return out  # Not enough info — return original untouched

    # ERPNext uses 'transaction_date' for Sales Invoice, 'posting_date' for others
    posting_date = (
        args.get("transaction_date")
        or args.get("posting_date")
    )

    # Use the rate already determined by ERPNext (after price lists etc.)
    # This is needed for minimum/maximum net rate filtering in the resolver.
    net_rate = flt(
        (out.get("rate") if isinstance(out, dict) else None)
        or args.get("rate")
        or args.get("price_list_rate")
        or 0
    )

    # ----------------------------------------------------------------
    # Step 3 — Resolve item-level tax (ignores invoice tax_category)
    # ----------------------------------------------------------------
    try:
        result = resolve_item_tax(
            item_code=item_code,
            company=company,
            posting_date=posting_date,
            net_rate=net_rate,
        )
    except Exception:
        # Never break ERPNext item selection — silently log and return original
        frappe.log_error(
            title="havano_taxes: resolve_item_tax error in get_item_details",
            message=frappe.get_traceback(),
        )
        return out

    if not result:
        return out  # Item has no tax config — return original untouched

    # ----------------------------------------------------------------
    # Step 4 — Inject our resolved values into the result
    # ----------------------------------------------------------------
    # out may be a dict or a Frappe _dict
    tax_account = result.get("tax_account")
    tax_rate    = result.get("tax_rate", 0.0)
    template    = result.get("item_tax_template")

    if template or tax_account:
        out["item_tax_rate"]     = build_item_tax_rate_json(result.get("tax_details_dict", {}))
        out["item_tax_template"] = template

    # Also inject the custom fields so the client-side JS can display
    # them immediately without a second round-trip.
    out["custom_fiscal_tax_group"]   = result.get("fiscal_tax_group", "")
    out["custom_tax_category"]       = result.get("tax_category", "")
    out["custom_item_tax_template"]  = template or ""
    out["custom_tax_rate"]           = tax_rate
    out["custom_tax_account"]        = tax_account or ""

    return out

