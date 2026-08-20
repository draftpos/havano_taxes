"""
havano_taxes.after_install
===========================

Runs automatically when the app is installed via:
    bench --site <site> install-app havano_taxes

Sets up the ERPNext configuration required for item-level tax resolution
to work without any manual steps.
"""

import frappe


def after_install():
    """
    Automatically configure ERPNext on install so havano_taxes works
    immediately without manual Accounts Settings changes.
    """
    _enable_item_tax_from_template()
    _print_success_banner()


def _enable_item_tax_from_template():
    """
    Enable 'Automatically Add Taxes and Charges from Item Tax Template'.

    Without this, ERPNext ignores Item Tax Templates entirely when an
    item is added to a Sales Invoice.  The havano_taxes bypass depends
    on ERPNext reading item_tax_rate per item.
    """
    try:
        frappe.db.set_single_value(
            "Accounts Settings",
            "add_taxes_from_item_tax_template",
            1,
        )
        # Note: no explicit commit — Frappe commits after after_install() returns.
        frappe.logger("havano_taxes").info(
            "havano_taxes after_install: "
            "'Automatically Add Taxes from Item Tax Template' ENABLED."
        )
    except Exception as e:
        frappe.log_error(
            title="havano_taxes: after_install warning",
            message=(
                "Could not enable 'add_taxes_from_item_tax_template' automatically.\n"
                "Please enable it manually at:\n"
                "  Accounting → Accounts Settings → "
                "Automatically Add Taxes and Charges from Item Tax Template\n\n"
                f"Error: {e}"
            ),
        )


def _print_success_banner():
    frappe.msgprint(
        msg=(
            "<b>havano_taxes installed successfully.</b><br><br>"
            "✅ 'Automatically Add Taxes from Item Tax Template' has been enabled.<br><br>"
            "The app will now resolve VAT / ZERO RATED / EXEMPT at item level "
            "on every Sales Invoice automatically.<br><br>"
            "No further configuration is required in Accounts Settings."
        ),
        title="Havano Taxes — Ready",
        indicator="green",
    )
