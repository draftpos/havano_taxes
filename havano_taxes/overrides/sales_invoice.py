"""
havano_taxes.overrides.sales_invoice
=====================================

Doc-event handlers for Sales Invoice.

on_validate   — resolves item-level taxes and recalculates totals.
on_before_submit — blocks submission if any item has an ambiguous or
                   missing tax configuration.

Design
------
ERPNext fires doc_events['Sales Invoice']['validate'] AFTER its own
validate() has run (including calculate_taxes_and_totals()).  We therefore:

  1. Set item_tax_rate on every item from our resolver.
  2. Call doc.calculate_taxes_and_totals() a second time so totals
     reflect the corrected per-item rates.

This is safe because calculate_taxes_and_totals() is pure calculation
(no DB writes); the final values are saved when ERPNext completes its
normal save flow.

No product names, accounts, or rates are hard-coded here.
Everything is driven by the Item master configuration.
"""

import frappe
from frappe import _
from frappe.utils import flt

from havano_taxes.tax_resolver import resolve_item_tax, build_item_tax_rate_json


# ---------------------------------------------------------------------------
# on_validate
# ---------------------------------------------------------------------------

def on_validate(doc, method=None):
    """
    Resolve each item's tax independently of the invoice-level tax_category,
    then recalculate the invoice totals.

    Called automatically after ERPNext's own validate().
    """
    if doc.doctype != "Sales Invoice":
        return

    _resolve_all_items(doc)
    doc.calculate_taxes_and_totals()


def _resolve_all_items(doc):
    """
    Iterate every Sales Invoice Item, call resolve_item_tax(), and persist:
      - item_tax_rate     (used by ERPNext's tax calculation engine)
      - custom_tax_category
      - custom_item_tax_template
      - custom_tax_rate
      - custom_tax_account
      - custom_fiscal_tax_group
    """
    for item in doc.get("items") or []:
        if not item.item_code:
            continue

        result = resolve_item_tax(
            item_code=item.item_code,
            company=doc.company,
            posting_date=doc.posting_date,
            net_rate=flt(item.rate),
        )

        if not result:
            # No Item Tax configuration found — leave ERPNext defaults in place
            # and let on_before_submit block if this is a problem.
            frappe.log_error(
                title=f"havano_taxes: no Item Tax found",
                message=(
                    f"Sales Invoice {doc.name or '(unsaved)'}: "
                    f"item '{item.item_code}' has no valid Item Tax row "
                    f"for company '{doc.company}' on {doc.posting_date}."
                ),
            )
            continue

        # Set item_tax_rate — ERPNext reads this in calculate_taxes_and_totals()
        # to apply per-item rate overrides on each Taxes and Charges row.
        new_rate_json = build_item_tax_rate_json(result.get("tax_details_dict", {}))
        item.item_tax_rate = new_rate_json

        # Also update the item_tax_template field on the invoice line so the
        # UI correctly reflects what template was applied.
        item.item_tax_template = result["item_tax_template"]

        # Persist resolved values in the custom fields (historical record).
        item.custom_tax_category = result["tax_category"]
        item.custom_item_tax_template = result["item_tax_template"]
        item.custom_tax_rate = result["tax_rate"]
        item.custom_tax_account = result["tax_account"]
        item.custom_fiscal_tax_group = result["fiscal_tax_group"]


# ---------------------------------------------------------------------------
# on_before_submit
# ---------------------------------------------------------------------------

def on_before_submit(doc, method=None):
    """
    Validate that every item has a resolved tax configuration before the
    invoice is submitted and locked.

    Also catches obvious mismatches (e.g. fiscal_tax_group = ZERO RATED but
    tax_rate > 0) that would indicate a misconfigured Item Tax Template.
    """
    if doc.doctype != "Sales Invoice":
        return

    errors = []

    for item in doc.get("items") or []:
        if not item.item_code:
            continue

        fiscal_group = (item.get("custom_fiscal_tax_group") or "").strip().upper()
        tax_rate = flt(item.get("custom_tax_rate") or 0)
        tax_category = (item.get("custom_tax_category") or "").strip()

        # ---- Missing configuration ----
        if not item.get("custom_item_tax_template"):
            errors.append(
                _(
                    "Row {row}: Item <b>{item}</b> — no valid Item Tax Template was "
                    "found for company <b>{company}</b>. Configure an Item Tax row "
                    "on the Item master or its Item Group."
                ).format(
                    row=item.idx,
                    item=item.item_code,
                    company=doc.company,
                )
            )
            continue

        # ---- Rate / group mismatch ----
        zero_groups = {"ZERO RATED", "EXEMPT", "ZERO-RATED"}
        if fiscal_group in zero_groups and tax_rate > 0:
            errors.append(
                _(
                    "Row {row}: Item <b>{item}</b> — fiscal group is "
                    "<b>{group}</b> but tax rate is <b>{rate}%</b>. "
                    "The zero-rated Item Tax Template should have rate 0."
                ).format(
                    row=item.idx,
                    item=item.item_code,
                    group=fiscal_group,
                    rate=tax_rate,
                )
            )

        if fiscal_group == "VAT" and tax_rate == 0:
            errors.append(
                _(
                    "Row {row}: Item <b>{item}</b> — fiscal group is <b>VAT</b> "
                    "but tax rate is <b>0%</b>. "
                    "Check the Zimbabwe Tax Item Tax Template configuration."
                ).format(
                    row=item.idx,
                    item=item.item_code,
                )
            )

    if errors:
        # Show all errors at once so the user can fix them in one pass.
        msg = "<br><br>".join(errors)
        frappe.throw(
            msg,
            title=_("Cannot Submit — Tax Configuration Issues"),
        )

