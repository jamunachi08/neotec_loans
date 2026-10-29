// Neotec Loans — posting actions on the facility form.
const M = "neotec_loans.api.";
frappe.ui.form.on("Finance Facility", {
	refresh(frm) {
		if (frm.is_new()) return;
		const call = (method, args, done) => frappe.call({
			method: M + method, args: Object.assign({ name: frm.doc.name }, args || {}), freeze: true,
			callback: (r) => { if (done) done(r.message); frm.reload_doc(); },
		});
		const posted = (je) => frappe.show_alert({ message: __("Journal Entry {0} created", [je]), indicator: "green" });

		frm.add_custom_button(__("Preview plan"), () => frappe.call({
			method: M + "preview", args: { name: frm.doc.name },
			callback(r) {
				const rows = (r.message || []).map((x) =>
					`<tr><td>${x.month}</td><td style="text-align:right">${format_currency(x.profit)}</td>`
					+ `<td style="text-align:right">${format_currency(x.fee)}</td><td>${x.journal_entry || ""}</td></tr>`).join("");
				frappe.msgprint({ title: __("Monthly plan"), wide: true, message:
					`<table class="table table-bordered"><thead><tr><th>${__("Month end")}</th><th>${__("Profit")}</th>`
					+ `<th>${__("Charge")}</th><th>${__("Posted")}</th></tr></thead><tbody>${rows}</tbody></table>` });
			},
		}), __("Loan"));
		frm.add_custom_button(__("Post drawdown"), () => call("post_drawdown", {}, posted), __("Loan"));
		if (frm.doc.fee_amount) frm.add_custom_button(__("Post charge payment"), () => call("post_fee_payment", {}, posted), __("Loan"));
		frm.add_custom_button(__("Post month"), () => frappe.prompt(
			{ fieldname: "month_end", fieldtype: "Date", label: __("Month end"), reqd: 1,
			  default: frappe.datetime.month_end() },
			(v) => call("post_month", v, posted), __("Post month")), __("Loan"));
		frm.add_custom_button(__("Post repayment"), () => {
			const open = (frm.doc.schedule || []).filter((r) => !r.repayment_entry);
			if (!open.length) { frappe.msgprint(__("Every instalment is already posted.")); return; }
			frappe.prompt([
				{ fieldname: "row", fieldtype: "Select", label: __("Instalment"), reqd: 1,
				  options: open.map((r) => ({ value: r.name, label: `${r.due_date} · ${format_currency(r.principal)} + ${format_currency(r.profit)}` })) },
				{ fieldname: "posting_date", fieldtype: "Date", label: __("Paid on (blank = due date)") },
			], (v) => call("post_repayment", v, posted), __("Post repayment"));
		}, __("Loan"));
		frm.add_custom_button(__("Run month-end (all facilities)"), () => frappe.prompt(
			{ fieldname: "month_end", fieldtype: "Date", label: __("Month end"), reqd: 1, default: frappe.datetime.month_end() },
			(v) => frappe.call({ method: M + "run_month", args: { company: frm.doc.company, month_end: v.month_end }, freeze: true,
				callback(r) {
					const rows = (r.message || []).map((x) => `<li><b>${x.facility}</b>: ${x.status}`
						+ `${x.journal_entry ? " — " + x.journal_entry : ""}${x.error ? " — " + frappe.utils.escape_html(x.error) : ""}</li>`).join("");
					frappe.msgprint({ title: __("Month-end run"), message: `<ul>${rows}</ul>` });
					frm.reload_doc();
				} }), __("Run month-end")), __("Loan"));
	},
});
