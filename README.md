# havano_taxes

**ERPNext v15 — Item-Level Tax Resolution for ZIMRA Fiscalisation**

Extends ERPNext's tax engine from a single invoice-level Tax Category to
**item-level Tax Category resolution**, so a single Sales Invoice can
contain VAT, ZERO RATED, and EXEMPT lines while correctly calculating
totals and preserving the fiscal classification required by ZIMRA.

---

## What this app does

| Without havano_taxes | With havano_taxes |
|---|---|
| Invoice header has ONE Tax Category | Each item resolves its own Tax Category |
| Mixed VAT + Zero Rated requires a workaround `Sales` category | Items use their real categories: `VAT`, `ZERO RATED`, `EXEMPT` |
| Fiscalisation cannot distinguish Zero Rated from Exempt | `custom_fiscal_tax_group` on every submitted item line |
| Tax misconfiguration fails silently | Submission blocked with item-specific error messages |

---

## Architecture

```
havano_taxes/
├── tax_resolver.py          ← Central resolver (single source of truth)
├── api.py                   ← Whitelisted endpoints (JS, POS, fiscalisation)
├── hooks.py                 ← Doc events + fixtures registration
├── overrides/
│   └── sales_invoice.py     ← on_validate + on_before_submit handlers
├── fixtures/
│   └── custom_field.json    ← 6 custom fields on Sales Invoice Item
└── public/js/
    └── sales_invoice.js     ← Client-side immediate feedback
```

### The one function to rule them all

```python
from havano_taxes.tax_resolver import resolve_item_tax

result = resolve_item_tax(
    item_code   = "Groundnuts",
    company     = "LENMASH MARKETING PVT LTD",
    posting_date = "2025-08-20",
)

# result:
# {
#     "tax_category":      "ZERO RATED",
#     "item_tax_template": "Zero Rated - DC1437",
#     "tax_account":       "VAT - DC1437",
#     "tax_rate":          0.0,
#     "fiscal_tax_group":  "ZERO RATED"
# }
```

Use this in:
- Fiscalisation integration
- POS custom scripts
- Credit Note / Returns logic
- Print format server scripts
- External API sync

**Never implement independent tax-detection logic elsewhere.**

---

## Custom fields added to Sales Invoice Item

| Field | Label | Purpose |
|---|---|---|
| `custom_fiscal_tax_group` | Fiscal Tax Group | `VAT` / `ZERO RATED` / `EXEMPT` — sent to ZIMRA |
| `custom_tax_category` | Tax Category | Link to ERPNext Tax Category |
| `custom_item_tax_template` | Item Tax Template (Resolved) | Which template was applied |
| `custom_tax_rate` | Tax Rate (%) | Resolved rate at time of transaction |
| `custom_tax_account` | Tax Account | VAT account used |

All fields are **read-only** and **no_copy=1** (not copied to new documents).
`custom_fiscal_tax_group` is shown inline in the items grid.

---

## Prerequisites (ERPNext configuration)

Before installing this app, your ERPNext must be configured as described in
the ERPNext v15 Mixed VAT Configuration Guide.  In summary:

### Tax Categories required

| Name | Purpose |
|---|---|
| `VAT` | Standard rated items |
| `ZERO RATED` | Zero-rated items |
| `EXEMPT` | Exempt items |

Create these at **Accounting → Tax Category**.

> The Tax Category name becomes the `fiscal_tax_group` automatically.
> No mapping is hard-coded in the app.

### Item Tax Templates required

| Template | Account | Rate |
|---|---|---|
| Zimbabwe Tax - DC1437 | VAT - DC1437 | 15.5 |
| Zero Rated - DC1437 | VAT - DC1437 | 0 |
| Exempt - DC1437 | VAT - DC1437 | 0 |

> Zero Rated and Exempt must use the **same VAT account** as the VAT template.
> The rate (0) is what overrides ERPNext's standard 15.5% calculation.

### Item master (each item)

Open every item and add a row to the **Item Tax** table:

| Item | Tax Category | Item Tax Template |
|---|---|---|
| Peanut Butter | VAT | Zimbabwe Tax - DC1437 |
| Pure Honey | VAT | Zimbabwe Tax - DC1437 |
| Groundnuts | ZERO RATED | Zero Rated - DC1437 |
| Hupfu | ZERO RATED | Zero Rated - DC1437 |
| Medical Product | EXEMPT | Exempt - DC1437 |

### Accounts Settings

Enable:

> **Automatically Add Taxes and Charges from Item Tax Template**

---

## Installation

```bash
# From inside your bench directory
cd /home/frappe/frappe-bench

# Get the app
bench get-app havano_taxes /path/to/havano_taxes
# or if on GitHub:
# bench get-app havano_taxes https://github.com/your-org/havano_taxes

# Install on your site
bench --site erp1038.havano.cloud install-app havano_taxes

# Run migrate to install fixtures (custom fields)
bench --site erp1038.havano.cloud migrate

# Build JS assets
bench build --app havano_taxes

# Restart
bench restart
```

---

## Verification

After installation, create a test Sales Invoice with mixed items:

1. Add a VAT item (e.g. Peanut Butter)
2. Add a Zero Rated item (e.g. Groundnuts)
3. Check the items grid — `Fiscal Tax Group` column should show `VAT` and `ZERO RATED`
4. Check the tax total — should only apply 15.5% to VAT items
5. Submit the invoice — should succeed without errors
6. Check submitted invoice items — `custom_fiscal_tax_group` must be persisted

Expected tax calculation for:

| Item | Net | Group |
|---|---|---|
| Peanut Butter | 100.00 | VAT |
| Groundnuts | 50.00 | ZERO RATED |

```
VAT taxable base   100.00
VAT @ 15.5%         15.50

Net Total          150.00
VAT                 15.50
Grand Total        165.50
```

---

## Fiscalisation API

```python
# Get full fiscal breakdown of a submitted invoice
import frappe
from havano_taxes.api import get_invoice_tax_summary, get_invoice_line_tax_details

summary = get_invoice_tax_summary("ACC-SINV-2025-00001")
# {
#     "VAT":        {"taxable_amount": 300.00, "tax_amount": 46.50, "tax_rate": 15.5, "items": [...]},
#     "ZERO RATED": {"taxable_amount":  80.00, "tax_amount":  0.00, "tax_rate":  0.0, "items": [...]}
# }

lines = get_invoice_line_tax_details("ACC-SINV-2025-00001")
# [
#     {"item_code": "Peanut Butter", "fiscal_tax_group": "VAT",        "tax_rate": 15.5, ...},
#     {"item_code": "Groundnuts",    "fiscal_tax_group": "ZERO RATED", "tax_rate":  0.0, ...}
# ]
```

Or via HTTP (authenticated Frappe session):

```
GET /api/method/havano_taxes.api.get_invoice_line_tax_details
    ?sales_invoice_name=ACC-SINV-2025-00001
```

---

## Troubleshooting

| Symptom | Check |
|---|---|
| Items show `⚠ NOT CONFIGURED` in fiscal group | Item master has no Item Tax row |
| Submission blocked: "No valid Item Tax Template" | Same — configure Item Tax on the Item |
| VAT calculated on zero-rated items | `item_tax_rate` not being set — check if another custom app is overwriting it |
| `custom_fiscal_tax_group` is blank after save | Run `bench migrate` to install fixtures |
| JS not loading | Run `bench build --app havano_taxes` |

---

## Extending to Purchase Invoices

The resolver accepts `transaction_type="Purchase"` (reserved).
To extend to Purchase Invoices, add a `doc_events` entry for
`Purchase Invoice` in `hooks.py` pointing to a new handler in
`overrides/purchase_invoice.py` that calls `_resolve_all_items(doc)`.

---

## License

MIT
