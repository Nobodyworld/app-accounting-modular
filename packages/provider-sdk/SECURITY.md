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

Provider module values must be bounded dotted Python identifiers ending in
`.provider`; path separators, traversal, drives, URIs, control characters, and
empty components fail before import. Builders resolve every source file beneath
the expected ordinary source root and reject symlinks, junctions/reparse points,
special files, and unsafe force-regeneration targets. Artifact inspection rejects
absolute, drive, UNC, traversal, duplicate, overlong, link, device, FIFO, and
oversized archive members. CLI failures use stable path-free categories and do
not render raw operating-system exception text.
