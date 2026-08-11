# Security policy

Metrbot Lab is a local research and testing tool, not a hosted service or broker connector. The MVP
does not accept credentials, call external services, persist data in a database, or execute live
orders.

## Trusted custom code

Custom strategies are imported and executed in the same Python process as the caller. This is a
deliberate MVP contract, not a sandbox. A strategy can technically access the machine with the
caller’s permissions, so users must run only code they trust and should use an isolated environment
for untrusted experiments. The same rule applies inside Docker: a strategy can access any host path
mounted into its container.

## Reporting a vulnerability

Please do not publish credentials, tokens, private datasets, or an exploitable proof containing
sensitive information in a public issue. If this project is hosted on GitHub, use its private
vulnerability-reporting or security-advisory channel. Otherwise, contact the project maintainer
through the private channel associated with the project host.

Include the affected version or commit, a minimal reproduction using synthetic data, impact, and any
safe mitigation. Do not include credentials, private datasets, or other sensitive material.

## Supported release expectations

Before a public release, maintainers must review dependencies and licenses, run a secret scan, inspect
wheel contents, review source provenance, and verify that documentation does not imply live execution
or future-performance guarantees. The complete maintainer gate is recorded in
[CONTRIBUTING.md](CONTRIBUTING.md#maintainer-release-checklist).
