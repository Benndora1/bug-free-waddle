### Asset Management

A generic, multi-fund investment management and unit-registry platform for asset managers (unit trusts / collective investment schemes). It provides client onboarding and KYC, fund definitions, unit registry transactions (subscriptions, redemptions, switches, transfers, liens, distributions), daily NAV valuations, fixed income and equity portfolio accounting, investment compliance limits, and client statement generation integrated with ERPNext.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI. Note that ERPNext is required and must be installed prior to installing `asset_management`:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app erpnext --branch version-16
bench get-app https://github.com/benndora1/asset_management.git --branch main
bench --site <site-name> install-app erpnext
bench --site <site-name> install-app asset_management
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/asset_management
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

GNU General Public License v3.0 (see [license.txt](license.txt))
