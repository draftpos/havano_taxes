/**
 * havano_taxes — Sales Invoice client-side script
 *
 * Immediately resolves and displays each item's fiscal tax group as soon
 * as the item is selected in the invoice items grid.
 *
 * This is purely cosmetic for the user — the authoritative resolution
 * happens server-side in on_validate.  The JS gives instant visual
 * feedback so the user sees "VAT" or "ZERO RATED" without saving first.
 *
 * Loaded via hooks.py → doctype_js (Sales Invoice form only).
 */

frappe.ui.form.on("Sales Invoice Item", {

    /**
     * Fired when the user selects or changes an item in a row.
     */
    item_code: function (frm, cdt, cdn) {
        _resolve_item_row(frm, cdt, cdn);
    },

    /**
     * Re-resolve when rate changes — triggers minimum/maximum net-rate
     * restrictions in the server-side resolver.
     */
    rate: function (frm, cdt, cdn) {
        _resolve_item_row(frm, cdt, cdn);
    },
});


/**
 * Call the server resolver and populate custom tax fields on the item row.
 * Named function so both item_code and rate handlers share the same logic
 * without relying on the internal frappe.ui.form.handlers[] API.
 */
function _resolve_item_row(frm, cdt, cdn) {
    const row = frappe.get_doc(cdt, cdn);
    if (!row.item_code || !frm.doc.company) return;

    frappe.call({
        method: "havano_taxes.api.get_item_tax_details",
        args: {
            item_code: row.item_code,
            company: frm.doc.company,
            posting_date: frm.doc.posting_date || frappe.datetime.get_today(),
            net_rate: row.rate || 0,
        },
        callback: function (r) {
            if (!r.message || Object.keys(r.message).length === 0) {
                // No config found — warn the user in the row
                frappe.model.set_value(cdt, cdn, "custom_fiscal_tax_group", "⚠ NOT CONFIGURED");
                return;
            }

            const d = r.message;

            frappe.model.set_value(cdt, cdn, "custom_fiscal_tax_group",  d.fiscal_tax_group  || "");
            frappe.model.set_value(cdt, cdn, "custom_tax_category",       d.tax_category      || "");
            frappe.model.set_value(cdt, cdn, "custom_item_tax_template",  d.item_tax_template || "");
            frappe.model.set_value(cdt, cdn, "custom_tax_rate",           d.tax_rate          || 0);
            frappe.model.set_value(cdt, cdn, "custom_tax_account",        d.tax_account       || "");

            // Colour-code the fiscal group cell for quick visual scan
            _colour_fiscal_group_cell(cdn, d.fiscal_tax_group);
        },
    });
}


/**
 * Apply a subtle background colour to the Fiscal Tax Group cell.
 *
 *   VAT         → light green
 *   ZERO RATED  → light blue
 *   EXEMPT      → light amber
 */
function _colour_fiscal_group_cell(cdn, group) {
    if (!group) return;

    const colour_map = {
        "VAT":        "#e6f4ea",
        "ZERO RATED": "#e8f0fe",
        "ZERO-RATED": "#e8f0fe",
        "EXEMPT":     "#fef9e7",
    };

    const colour = colour_map[(group || "").toUpperCase().trim()] || "";
    if (!colour) return;

    // ERPNext grid rows are identified by data-name attribute
    setTimeout(function () {
        const $cell = $(`.grid-row[data-name="${cdn}"] [data-fieldname="custom_fiscal_tax_group"]`);
        if ($cell.length) {
            $cell.css("background-color", colour);
        }
    }, 300);
}

