"""
havano_taxes.api
================

Whitelisted endpoints consumed by:
  - Client-side JS (immediate item-row feedback)
  - POS / Sales Order creation
  - Fiscalisation layer
  - External integrations
  - Credit Note / Return flows

All callers share one source of truth: resolve_item_tax().
"""

import frappe
from frappe import _

from havano_taxes.tax_resolver import resolve_item_tax


@frappe.whitelist()
def get_item_tax_details(item_code: str, company: str, posting_date: str = None, net_rate: float = None) -> dict:
    """
    Return the resolved tax details for *item_code*.

    Called from:
        - Sales Invoice item grid (JS)
        - POS
        - External API consumers

    Response shape
    --------------
    {
        "tax_category":       "ZERO RATED",
        "item_tax_template":  "Zero Rated - DC1437",
        "tax_account":        "VAT - DC1437",
        "tax_rate":           0.0,
        "fiscal_tax_group":   "ZERO RATED"
    }

    Returns an empty dict {} if no Item Tax row is found (not an error;
    let the caller decide how to handle unconfigured items).
    """
    if not item_code:
        frappe.throw(_("item_code is required"))
    if not company:
        frappe.throw(_("company is required"))

    result = resolve_item_tax(
        item_code=item_code,
        company=company,
        posting_date=posting_date,
        net_rate=float(net_rate) if net_rate is not None else None,
    )

    return result or {}


@frappe.whitelist()
def get_invoice_tax_summary(sales_invoice_name: str) -> dict:
    """
    Return a per-fiscal-group tax breakdown for a submitted Sales Invoice.

    Designed for consumption by the ZIMRA fiscalisation layer.

    Response shape
    --------------
    {
        "VAT": {
            "taxable_amount": 300.00,
            "tax_amount":      46.50,
            "tax_rate":        15.5,
            "items": ["Peanut Butter", "Pure Honey"]
        },
        "ZERO RATED": {
            "taxable_amount": 80.00,
            "tax_amount":      0.00,
            "tax_rate":        0.0,
            "items": ["Groundnuts", "Hupfu"]
        }
    }
    """
    if not sales_invoice_name:
        frappe.throw(_("sales_invoice_name is required"))

    doc = frappe.get_doc("Sales Invoice", sales_invoice_name)

    summary = {}

    for item in doc.get("items") or []:
        group = (item.get("custom_fiscal_tax_group") or "UNCLASSIFIED").strip().upper()
        rate = float(item.get("custom_tax_rate") or 0)
        net = float(item.net_amount or 0)
        tax_amount = round(net * rate / 100, 2)

        if group not in summary:
            summary[group] = {
                "taxable_amount": 0.0,
                "tax_amount": 0.0,
                "tax_rate": rate,
                "items": [],
            }

        summary[group]["taxable_amount"] = round(summary[group]["taxable_amount"] + net, 2)
        summary[group]["tax_amount"] = round(summary[group]["tax_amount"] + tax_amount, 2)
        summary[group]["items"].append(item.item_code)

    return summary


@frappe.whitelist()
def get_invoice_line_tax_details(sales_invoice_name: str) -> list:
    """
    Return full per-line tax details for a Sales Invoice.

    Used by fiscalisation to build the ZIMRA receipt line by line.

    Response shape (list of dicts)
    --------------------------------
    [
        {
            "idx":                 1,
            "item_code":           "Peanut Butter",
            "item_name":           "Peanut Butter",
            "qty":                 2.0,
            "rate":                100.0,
            "net_amount":          200.0,
            "fiscal_tax_group":   "VAT",
            "tax_rate":            15.5,
            "tax_amount":          31.0,
            "tax_account":        "VAT - DC1437",
            "item_tax_template":  "Zimbabwe Tax - DC1437",
        },
        ...
    ]
    """
    if not sales_invoice_name:
        frappe.throw(_("sales_invoice_name is required"))

    doc = frappe.get_doc("Sales Invoice", sales_invoice_name)

    lines = []
    for item in doc.get("items") or []:
        rate = float(item.get("custom_tax_rate") or 0)
        net = float(item.net_amount or 0)
        tax_amount = round(net * rate / 100, 2)

        lines.append({
            "idx": item.idx,
            "item_code": item.item_code,
            "item_name": item.item_name,
            "qty": float(item.qty or 0),
            "rate": float(item.rate or 0),
            "net_amount": net,
            "fiscal_tax_group": (item.get("custom_fiscal_tax_group") or "").strip().upper(),
            "tax_rate": rate,
            "tax_amount": tax_amount,
            "tax_account": item.get("custom_tax_account") or "",
            "item_tax_template": item.get("custom_item_tax_template") or "",
        })

    return lines
