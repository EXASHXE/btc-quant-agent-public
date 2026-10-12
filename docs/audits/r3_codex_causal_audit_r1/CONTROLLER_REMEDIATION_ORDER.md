# Implementation-team remediation order

This review proposes contracts and acceptance cases; it supplies no application
patch and changes no independent implementation branch.

1. Fix producer and C timestamp semantics together. Keep settlement time in
   provider/payload fields and actual receive time in observed/available fields.
   C must accept T+200ms, T+30s and T+3h receipts while rejecting decisions before
   receipt. Retain a distinct historical settlement-position basis.
2. Replace the scalar Mark cash basis with an immutable witness containing
   finite positive Decimal price, relevant settlement time, actual ingress,
   source digest, quality and route/session identity. Missing, stale,
   post-settlement-only and prior-epoch references must return explicit unknown
   realized-cash status. Reset references on route/session changes.
3. Validate fields, finite values and dispatch schemas before journal mutation.
   Infinity and NaN must produce explicit failures with no committed VERIFIED
   entry. Missing Mark and missing rate must expose incompleteness. Specify
   recovery when consumer publication fails after an entry has been stored.
4. Define one settlement identity per symbol/time. Equivalent rate strings must
   deduplicate; a conflicting rate needs explicit reconciliation, not two fees.
   Preserve the verified cash signs, HALF_EVEN behavior and identical replay.
5. Load exact B/C source through an explicit portable cache/artifact contract.
   Require full SHA/file-hash checks, isolated module origins and hard failure
   for unavailable objects. Remove development-path probing from existing test
   preambles. The review's staging/worker functions are executable examples;
   no CI configuration was changed and no CI success was asserted.

Minimum regression suite: the 20 synthetic scenarios in the review harness,
converted by the implementation team to invariant assertions against its own
exact candidate SHA. Baseline defect probes are observation tests and should
not be interpreted as engineering acceptance tests.
