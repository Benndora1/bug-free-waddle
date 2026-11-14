frappe.query_reports["Fund NAV Reconciliation"] = {
	filters: [
		{
			fieldname: "fund",
			label: __("Fund"),
			fieldtype: "Link",
			options: "Asset Fund",
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -7),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && !data.within_tolerance) {
			value = `<span style="color: var(--red-600, #dc2626); font-weight: 600;">${value}</span>`;
		}
		return value;
	},
};
