// Neotec Loans — import the loan workbook into Draft facilities.
frappe.listview_settings["Finance Facility"] = {
	onload(list) {
		list.page.add_inner_button(__("Import workbook"), () => {
			const acc = (fieldname, label, options) => ({ fieldname, label, fieldtype: "Link", options: options || "Account" });
			const d = new frappe.ui.Dialog({
				title: __("Import loan workbook"), size: "extra-large",
				fields: [
					{ fieldname: "file_url", label: __("Workbook (.xlsx)"), fieldtype: "Attach", reqd: 1 },
					{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", reqd: 1,
					  default: frappe.defaults.get_user_default("Company") },
					{ fieldtype: "Column Break" },
					{ fieldname: "term_treatment", label: __("Term loans"), fieldtype: "Select",
					  options: "Accrue monthly, pay with instalment\nDeferred upfront, amortise monthly",
					  default: "Accrue monthly, pay with instalment" },
					{ fieldname: "short_treatment", label: __("Short-term financings"), fieldtype: "Select",
					  options: "Deferred upfront, amortise monthly\nAccrue monthly, pay with instalment",
					  default: "Deferred upfront, amortise monthly" },
					{ fieldname: "vat_rate", label: __("VAT rate %"), fieldtype: "Float", default: 15 },
					{ fieldtype: "Section Break", label: __("Default accounts (optional — editable per facility later)"), collapsible: 1 },
					acc("bank_account", __("Bank")), acc("loan_payable_account", __("Loan / financing payable")),
					acc("finance_cost_account", __("Finance cost")), acc("cost_center", __("Cost center"), "Cost Center"),
					{ fieldtype: "Column Break" },
					acc("accrued_profit_account", __("Accrued profit")), acc("deferred_finance_cost_account", __("Deferred finance cost")),
					acc("fee_expense_account", __("Facility charges expense")), acc("prepaid_fee_account", __("Prepaid charges")),
					acc("input_vat_account", __("Input VAT")),
					{ fieldtype: "Section Break" },
					{ fieldname: "preview", fieldtype: "HTML" },
				],
				primary_action_label: __("Preview"),
				primary_action(v) {
					const defaults = {};
					["bank_account", "loan_payable_account", "finance_cost_account", "cost_center", "accrued_profit_account",
					 "deferred_finance_cost_account", "fee_expense_account", "prepaid_fee_account", "input_vat_account"]
						.forEach((k) => { if (v[k]) defaults[k] = v[k]; });
					const run = (create) => { v = d.get_values() || v; Object.keys(defaults).forEach((k) => delete defaults[k]);
						["bank_account", "loan_payable_account", "finance_cost_account", "cost_center", "accrued_profit_account",
						 "deferred_finance_cost_account", "fee_expense_account", "prepaid_fee_account", "input_vat_account"]
							.forEach((k) => { if (v[k]) defaults[k] = v[k]; });
						return frappe.call({
						method: "neotec_loans.api.import_workbook", freeze: true,
						args: { file_url: v.file_url, company: v.company, term_treatment: v.term_treatment,
								short_treatment: v.short_treatment, vat_rate: v.vat_rate, defaults: JSON.stringify(defaults), create },
						callback(r) {
							const m = r.message || {};
							const esc = frappe.utils.escape_html;
							const badge = (c) => c.status === "exact" ? `<span class="indicator-pill green">${__("matches sheet")}</span>`
								: c.status === "rounding" ? `<span class="indicator-pill blue" title="${esc(c.note)}">${__("bank figures; sheet rounding")}</span>`
								: `<span class="indicator-pill red">${__("check")}</span>`;
							const rows = (m.facilities || []).map((f) => `<tr><td>${esc(f.facility_name)}${f.exists ? " <i>(" + __("exists") + ")</i>" : ""}</td>`
								+ `<td>${__(f.facility_type)}</td><td style="text-align:right">${format_currency(f.principal)}</td>`
								+ `<td>${f.rows}</td><td>${esc(f.treatment)}</td><td>${esc(f.first_month)}</td><td>${badge(f.check)}</td></tr>`).join("");
							const warn = (m.warnings || []).map((w) => `<li>${esc(w)}</li>`).join("");
							const done = create ? `<div class="alert alert-success">${__("Created")}: ${m.created.length}`
								+ (m.skipped.length ? ` · ${__("skipped (already exist)")}: ${m.skipped.length}` : "") + `</div>` : "";
							d.fields_dict.preview.$wrapper.html(done
								+ `<table class="table table-bordered table-sm"><thead><tr><th>${__("Facility")}</th><th>${__("Type")}</th>`
								+ `<th>${__("Amount")}</th><th>${__("Rows")}</th><th>${__("Treatment")}</th><th>${__("First month")}</th>`
								+ `<th>${__("Self-check")}</th></tr></thead><tbody>${rows}</tbody></table>`
								+ (warn ? `<b>${__("Notes")}</b><ul>${warn}</ul>` : ""));
							if (!create) {
								d.set_primary_action(__("Create facilities"), () => run(1));
							} else {
								d.set_primary_action(__("Close"), () => { d.hide(); list.refresh(); });
							}
						},
					});
					}; // run
					run(0);
				},
			});
			d.show();
		});
	},
};
