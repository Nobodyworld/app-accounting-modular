# Provider SDK Security Boundary

Report suspected vulnerabilities through the repository security process.
Do not include credentials, tokens, provider response bodies, tenant data, or
private environment values in reports or conformance evidence.

The SDK performs structural inspection. It does not certify providers, validate
remote credentials, sandbox imported Python, authorize application execution,
install packages, discover entry points, or approve production use. Inspect and
install provider artifacts only in controlled environments. The application
will execute a provider only after explicit operator allowlisting, structural
conformance, tenant authorization, and v0.4 governance policy.

