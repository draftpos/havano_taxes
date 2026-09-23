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
    if not posting_date:
        posting_date = nowdate()

    posting_date = getdate(posting_date)

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
        ignore_permissions=True,
    )

    if not item_tax_rows:
        item_group = frappe.get_cached_value("Item", item_code, "item_group")
        if item_group:
            lft_rgt = frappe.get_cached_value("Item Group", item_group, ["lft", "rgt"])
            if lft_rgt:
                lft, rgt = lft_rgt
                ancestor_groups = frappe.db.sql_list(
                    """select name from \	abItem Group\
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
                        ignore_permissions=True,
                    )
                    if item_tax_rows:
                        break

    if not item_tax_rows:
        return None

    valid_rows = []
    for row in item_tax_rows:
        if row.valid_from and getdate(row.valid_from) > posting_date:
            continue

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

    best_row = valid_rows[0]

    template_name = best_row.item_tax_template
    tax_category = best_row.tax_category or ""

    if not template_name:
        return None

    tax_details = _get_template_tax_details(template_name, company)

    fiscal_tax_group = tax_category.upper() if tax_category else ""
    
    # We pick the first tax_account for the custom_tax_account field to avoid breaking db schema
    primary_tax_account = list(tax_details.keys())[0] if tax_details else ""
    primary_tax_rate = tax_details[primary_tax_account] if primary_tax_account else 0.0

    return {
        "tax_category": tax_category,
        "item_tax_template": template_name,
        "tax_account": primary_tax_account,
        "tax_rate": primary_tax_rate,
        "fiscal_tax_group": fiscal_tax_group,
        "tax_details_dict": tax_details
    }


def build_item_tax_rate_json(tax_details_dict: dict) -> str:
    if not tax_details_dict:
        return "{}"
    return json.dumps(tax_details_dict)


def _get_template_tax_details(template_name: str, company: str) -> dict:
    rows = frappe.get_all(
        "Item Tax Template Detail",
        filters={"parent": template_name},
        fields=["tax_type", "tax_rate"],
        ignore_permissions=True,
    )

    if not rows:
        abbr = frappe.get_cached_value("Company", company, "abbr")
        if abbr:
            scoped_name = f"{template_name} - {abbr}"
            rows = frappe.get_all(
                "Item Tax Template Detail",
                filters={"parent": scoped_name},
                fields=["tax_type", "tax_rate"],
                ignore_permissions=True,
            )

    tax_dict = {}
    for row in rows:
        if row.tax_type:
            tax_dict[row.tax_type] = flt(row.tax_rate)
            
    return tax_dict
