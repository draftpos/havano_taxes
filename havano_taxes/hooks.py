from . import __version__ as app_version

app_name = "havano_taxes"
app_title = "Havano Taxes"
app_publisher = "Havano"
app_description = (
    "Item-level VAT / ZERO RATED / EXEMPT resolution for ERPNext v15. "
    "Allows mixed tax classifications on one Sales Invoice while preserving "
    "ZIMRA fiscalisation compliance."
)
app_email = "dev@havano.cloud"
app_license = "MIT"

# ---------------------------------------------------------------------------
# After-install hook — ACTIVATES THE BYPASS ON INSTALL
# ---------------------------------------------------------------------------
# Runs automatically when:
#     bench --site <site> install-app havano_taxes
#
# Enables 'Automatically Add Taxes from Item Tax Template' in Accounts Settings
# so the bypass works immediately without any manual configuration.
# ---------------------------------------------------------------------------
after_install = "havano_taxes.after_install.after_install"

# ---------------------------------------------------------------------------
# SOURCE-LEVEL BYPASS — Layer 1 (browser → server item fetch)
# ---------------------------------------------------------------------------
# ERPNext's get_item_details uses the invoice-level tax_category to decide
# which Item Tax row applies.  We replace that endpoint with our wrapper that:
#   1. Calls the original ERPNext function unchanged (price, warehouse, UOM…)
#   2. Then overwrites ONLY item_tax_rate / item_tax_template using our resolver
#
# Effect: from the moment an item is selected in the browser, the correct
# rate is already set — before the user even saves.
# ---------------------------------------------------------------------------
override_whitelisted_methods = {
    "erpnext.stock.get_item_details.get_item_details": (
        "havano_taxes.patches.get_item_details_override.get_item_details"
    )
}

# ---------------------------------------------------------------------------
# Fixtures — installed via `bench --site <site> migrate`
# ---------------------------------------------------------------------------
fixtures = [
    {
        "doctype": "Custom Field",
        "filters": [
            ["dt", "=", "Sales Invoice Item"],
            ["fieldname", "in", [
                "custom_havano_tax_section",
                "custom_fiscal_tax_group",
                "custom_tax_category",
                "custom_col_break_1",
                "custom_item_tax_template",
                "custom_tax_rate",
                "custom_tax_account",
            ]],
        ],
    }
]

# ---------------------------------------------------------------------------
# DOC EVENTS — Layer 2 (server-side safety net on save)
# ---------------------------------------------------------------------------
# Fires AFTER ERPNext's own validate() so our resolver always wins.
# Even if something upstream resets item_tax_rate, on_validate restores it
# and calls calculate_taxes_and_totals() again with the corrected rates.
# on_before_submit blocks ambiguous or missing tax configurations.
# ---------------------------------------------------------------------------
doc_events = {
    "Sales Invoice": {
        "validate": "havano_taxes.overrides.sales_invoice.on_validate",
        "before_submit": "havano_taxes.overrides.sales_invoice.on_before_submit",
    }
}

# ---------------------------------------------------------------------------
# Client-side scripts — loaded ONLY on the Sales Invoice form
# ---------------------------------------------------------------------------
# doctype_js is scoped to the specified doctype form only.
# Using app_include_js would load on every desk page unnecessarily.
# ---------------------------------------------------------------------------
doctype_js = {"Sales Invoice": "public/js/sales_invoice.js"}

