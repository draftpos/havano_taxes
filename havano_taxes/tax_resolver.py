"""
havano_taxes.tax_resolver
=========================

Central item-level tax resolution for ERPNext v15.

Every part of the system (Sales Invoice calculation, POS, Credit Notes,
fiscalisation, print formats, external API) must call resolve_item_tax()
and never implement its own tax-detection logic.

Resolution priority
-------------------
1. Item Tax rows are filtered by company (if the template is company-scoped).
2. Rows are filtered by posting_date against the `valid_from` window.
3. Rows are filtered by net_rate against minimum_net_rate / maximum_net_rate.
   A value of 0 in either limit means "no restriction".
4. The most recently valid row (latest valid_from) is selected.
5. The fiscal_tax_group is derived directly from the Tax Category name —
   no hard-coded mapping is needed.

The resolver never inspects the Sales Invoice header tax_category.
Each item carries its own tax identity.
"""

import json
import frappe
from frappe.utils import getdate, nowdate, flt


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_item_tax(
    item_code: str,
    company: str,
    posting_date=None,
    transaction_type: str = "Sales",
    net_rate: float = None,
) -> dict | None:
    """
    Resolve the complete tax configuration for *item_code* at *posting_date*.

    Parameters
    ----------
    item_code : str
        The ERPNext Item code.
    company : str
        The company for which the invoice is being created.  Used to
        scope Item Tax Templates that are company-specific.
    posting_date : str | date | None
        The transaction date.  Defaults to today.
    transaction_type : str
        Reserved for future use ("Sales" / "Purchase").  Currently only
        Sales is implemented.
    net_rate : float | None
        The item's net rate.  Used to filter minimum/maximum net rate
        restrictions on the Item Tax row.  Pass None to skip rate filtering.

    Returns
    -------
    dict with keys:
        tax_category        — name of the Tax Category (e.g. "ZERO RATED")
        item_tax_template   — name of the Item Tax Template
        tax_account         — account head (e.g. "VAT - COMPANY")
        tax_rate            — float, e.g. 15.5 or 0.0
        fiscal_tax_group    — same as tax_category; explicit for clarity
    None if no valid Item Tax row is found.
    """
    if not posting_date:
        posting_date = nowdate()

    posting_date = getdate(posting_date)

    # ------------------------------------------------------------------
    # Step 1 — Load all Item Tax rows from the Item master
    # ------------------------------------------------------------------
    item_tax_rows = frappe.get_all(
        "Item Tax",
        filters={"parent": item_code, "parenttype": "Item"},
        fields=[
            "item_tax_template",
            "tax_category",
            "valid_from",
            "minimum_net_rate",
            "maximum_net_rate",
        ],
        order_by="valid_from desc",
    )

    if not item_tax_rows:
        item_group = frappe.get_cached_value("Item", item_code, "item_group")
        if item_group:
            lft_rgt = frappe.get_cached_value("Item Group", item_group, ["lft", "rgt"])
            if lft_rgt:
                lft, rgt = lft_rgt
                ancestor_groups = frappe.db.sql_list(
                    """select name from `tabItem Group`
                    where lft <= %s and rgt >= %s order by lft desc""",
                    (lft, rgt),
                )
                
                for group in ancestor_groups:
                    item_tax_rows = frappe.get_all(
                        "Item Tax",
                        filters={"parent": group, "parenttype": "Item Group"},
                        fields=[
                            "item_tax_template",
                            "tax_category",
                            "valid_from",
                            "minimum_net_rate",
                            "maximum_net_rate",
                        ],
                        order_by="valid_from desc",
                    )
                    if item_tax_rows:
                        break

    if not item_tax_rows:
        return None

    # ------------------------------------------------------------------
    # Step 2 — Filter by date and net-rate validity
    # ------------------------------------------------------------------
    valid_rows = []
    for row in item_tax_rows:
        # Skip rows whose validity window has not yet started
        if row.valid_from and getdate(row.valid_from) > posting_date:
            continue

        # Skip rows whose net-rate restrictions exclude this item's rate
        if net_rate is not None:
            min_rate = row.minimum_net_rate or 0
            max_rate = row.maximum_net_rate or 0
            if min_rate and net_rate < min_rate:
                continue
            if max_rate and net_rate > max_rate:
                continue

        valid_rows.append(row)

    if not valid_rows:
        return None

    # ------------------------------------------------------------------
    # Step 3 — Select the best row (most recent valid_from wins)
    # ------------------------------------------------------------------
    best_row = valid_rows[0]  # Already sorted DESC by valid_from above

    template_name = best_row.item_tax_template
    tax_category = best_row.tax_category or ""

    if not template_name:
        return None

    # ------------------------------------------------------------------
    # Step 4 — Resolve the template's tax account and rate
    # ------------------------------------------------------------------
    tax_account, tax_rate = _get_template_tax_details(template_name, company)

    # ------------------------------------------------------------------
    # Step 5 — Derive fiscal_tax_group from the Tax Category name
    # No hard-coded mapping — the category name IS the fiscal group.
    # ------------------------------------------------------------------
    fiscal_tax_group = tax_category.upper() if tax_category else ""

    return {
        "tax_category": tax_category,
        "item_tax_template": template_name,
        "tax_account": tax_account,
        "tax_rate": tax_rate,
        "fiscal_tax_group": fiscal_tax_group,
    }


def build_item_tax_rate_json(tax_account: str, tax_rate: float) -> str:
    """
    Return the JSON string ERPNext expects in Sales Invoice Item.item_tax_rate.

    Example: '{"VAT - COMPANY": 15.5}'

    ERPNext's calculate_taxes_and_totals() reads this field during
    get_item_wise_taxes_dict() to determine the per-item override rate.
    """
    if not tax_account:
        return "{}"
    return json.dumps({tax_account: tax_rate})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_template_tax_details(template_name: str, company: str) -> tuple[str, float]:
    """
    Return (tax_account, tax_rate) from the first row of an Item Tax Template.

    Item Tax Templates can be company-scoped (name = "Template - ABBR").
    We try the template as named first; if it has no rows we fall back
    gracefully and return ("", 0.0).
    """
    rows = frappe.get_all(
        "Item Tax Template Detail",
        filters={"parent": template_name},
        fields=["tax_type", "tax_rate"],
        limit=1,
    )

    if not rows:
        # Try company-scoped variant: "Template - <company abbreviation>"
        abbr = frappe.get_cached_value("Company", company, "abbr")
        if abbr:
            scoped_name = f"{template_name} - {abbr}"
            rows = frappe.get_all(
                "Item Tax Template Detail",
                filters={"parent": scoped_name},
                fields=["tax_type", "tax_rate"],
                limit=1,
            )

    if rows:
        return rows[0].tax_type or "", flt(rows[0].tax_rate)

    return "", 0.0
