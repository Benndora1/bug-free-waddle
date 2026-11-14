app_name = "asset_management"
app_title = "Asset Management"
app_publisher = "Frappe Developer"
app_description = "Asset Management App"
app_email = "developer@example.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "asset_management",
# 		"logo": "/assets/asset_management/logo.png",
# 		"title": "Asset Management",
# 		"route": "/asset_management",
# 		"has_permission": "asset_management.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/asset_management/css/asset_management.css"
# app_include_js = "/assets/asset_management/js/asset_management.js"

# include js, css files in header of web template
# web_include_css = "/assets/asset_management/css/asset_management.css"
# web_include_js = "/assets/asset_management/js/asset_management.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "asset_management/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "asset_management/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "asset_management.utils.jinja_methods",
# 	"filters": "asset_management.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "asset_management.install.before_install"
# after_install = "asset_management.install.after_install"
# after_migrate = []

# Uninstallation
# ------------

# before_uninstall = "asset_management.uninstall.before_uninstall"
# after_uninstall = "asset_management.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "asset_management.utils.before_app_install"
# after_app_install = "asset_management.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "asset_management.utils.before_app_uninstall"
# after_app_uninstall = "asset_management.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "asset_management.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "asset_management.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["asset_management.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"asset_management.tasks.all"
# 	],
# 	"daily": [
# 		"asset_management.tasks.daily"
# 	],
# 	"hourly": [
# 		"asset_management.tasks.hourly"
# 	],
# 	"weekly": [
# 		"asset_management.tasks.weekly"
# 	],
# 	"monthly": [
# 		"asset_management.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "asset_management.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "asset_management.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "asset_management.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "asset_management.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

ignore_links_on_delete = [
	"GL Entry",
	"Payment Ledger Entry",
	"Asset Unit Ledger Entry",
	"Asset Investor Register Line",
]

# Request Events
# ----------------
# before_request = ["asset_management.utils.before_request"]
# after_request = ["asset_management.utils.after_request"]

# Job Events
# ----------
# before_job = ["asset_management.utils.before_job"]
# after_job = ["asset_management.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"asset_management.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []


# Scheduler events for daily tasks
# scheduler_events = {
#     "daily": [
#         "asset_management.tasks.daily"
#     ]
# }

fixtures = [
	{
		"dt": "Role",
		"filters": [
			[
				"name",
				"in",
				[
					"Asset Management Operations",
					"Asset Investment Manager",
					"Asset Fund Administrator",
					"Asset Finance Officer",
					"Asset Compliance Officer",
					"Asset Client Service",
					"Asset Agent",
					"Asset Investor Portal User",
					"Asset Management Admin",
				],
			]
		],
	},
	{
		"dt": "Asset Required Document",
		"filters": [
			[
				"document_code",
				"in",
				[
					"NAT_ID",
					"PASSPORT",
					"PROOF_ADDR",
					"TIN_CERT",
					"CERT_INCORP",
					"MEM_ARTICLES",
					"BOARD_RESOL",
					"TRUST_DEED",
				],
			]
		],
	},
	{"dt": "Asset Risk Profile", "filters": [["code", "in", ["LOW_RISK", "MED_RISK", "HIGH_RISK"]]]},
	{"dt": "Asset PEP Sanction Setup", "filters": [["rule_code", "in", ["PEP_MATCH", "SANCTION_MATCH"]]]},
	{
		"dt": "Asset Suspicious Transaction Rule",
		"filters": [["rule_id", "in", ["AML_LARGE_CASH", "AML_RAPID_EXIT"]]],
	},
	{
		"dt": "Asset CRM SLA Setup",
		"filters": [
			[
				"code",
				"in",
				[
					"SLA_STATEMENT",
					"SLA_INQUIRY",
					"SLA_SUB_ISSUE",
					"SLA_RED_ISSUE",
					"SLA_SWITCH",
					"SLA_COMPLAINT",
				],
			]
		],
	},
	{
		"dt": "Asset Fund",
		"filters": [["fund_id", "in", ["SBG-MMF", "SBG-BAL", "SBG-EQT", "SBG-BND", "SBG-UMB"]]],
	},
	{"dt": "Asset Agent", "filters": [["agent_code", "in", ["AGT-001", "AGT-002"]]]},
	{
		"dt": "Asset Investment Security",
		"filters": [
			[
				"security_id",
				"in",
				["UG12K2306394", "UG12K0811352", "TBILL-364D-2027", "FD-STANBIC-180D", "EQ-MTNU"],
			]
		],
	},
	{"dt": "Asset Investment Limit Setup", "filters": [["fund", "in", ["SBG-BAL", "SBG-MMF"]]]},
	{
		"dt": "Print Format",
		"filters": [
			[
				"name",
				"in",
				["Unit Trust Contract Note", "Statement of Investment", "Stanbic Custody Instruction"],
			]
		],
	},
	{
		"dt": "Report",
		"filters": [
			[
				"name",
				"in",
				[
					"Unit Holders Register",
					"Daily Fund Valuation Summary",
					"Portfolio Performance and Asset Allocation",
					"Maturity Profile and Cash Flow Projection",
				],
			]
		],
	},
	{
		"dt": "Workspace",
		"filters": [
			[
				"name",
				"in",
				[
					"Asset Management",
					"Asset Operations",
					"Asset Portfolio & Trading",
					"Asset Fund Administration",
					"Asset Compliance & Risk",
					"Asset Client Service",
				],
			]
		],
	},
	{"dt": "Workspace Sidebar", "filters": [["name", "in", ["Asset Management"]]]},
	{"dt": "Desktop Icon", "filters": [["name", "in", ["Asset Management"]]]},
	{
		"dt": "Workflow State",
		"filters": [
			["name", "in", ["Draft", "Pending Approval", "Approved", "Rejected", "Submitted", "Cancelled"]]
		],
	},
	{
		"dt": "Workflow Action Master",
		"filters": [
			[
				"name",
				"in",
				[
					"Submit for Review",
					"Approve",
					"Reject",
					"Resubmit",
					"Post & Issue Units",
					"Post & Liquidate Units",
					"Post & Execute Switch",
					"Submit for Verification",
					"Approve NAV",
					"Reject NAV",
					"Publish & Post NAV",
					"Submit for Authorization",
					"Approve Trade",
					"Reject Trade",
					"Execute & Dispatch Custody",
					"Authorize & Sign",
					"Reject Instruction",
					"Dispatch to Custodian",
					"Submit for Compliance Review",
					"Approve KYC",
					"Reject KYC",
					"Generate Investor Master",
					"Submit Reconciliation",
					"Sign Off Reconciliation",
					"Reject Reconciliation",
					"Post Reconciled Batches",
				],
			]
		],
	},
	{
		"dt": "Workflow",
		"filters": [
			[
				"name",
				"in",
				[
					"Asset Subscription Approval Workflow",
					"Asset Redemption Approval Workflow",
					"Asset Fund Switch Approval Workflow",
					"Asset Fund Valuation Workflow",
					"Asset Trade Order Workflow",
					"Asset Custody Instruction Workflow",
					"Asset Investor Application Workflow",
					"Asset BOL Import Workflow",
				],
			]
		],
	},
]
