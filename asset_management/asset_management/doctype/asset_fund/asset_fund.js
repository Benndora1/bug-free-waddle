// Copyright (c) 2026, benndora1 and contributors
// For license information, please see license.txt

frappe.ui.form.on("Asset Fund", {
	refresh(frm) {
		if (
			!frm.is_new() &&
			(frappe.user.has_role("Asset Management Admin") ||
				frappe.user.has_role("Asset Finance Officer") ||
				frappe.user.has_role("System Manager"))
		) {
			frm.add_custom_button(__("Set up Accounts"), () => {
				frappe.call({
					method: "asset_management.services.fund_setup.setup_fund_accounts_api",
					args: { fund: frm.doc.name },
					freeze: true,
					freeze_message: __("Provisioning fund company and accounts..."),
					callback(r) {
						if (!r.exc) {
							frappe.msgprint({
								message: __("Accounting setup completed successfully for fund {0}.", [frm.doc.name]),
								indicator: "green",
								title: __("Accounting Setup Complete"),
							});
							frm.reload_doc();
						}
					},
				});
			});
		}
	},
});
