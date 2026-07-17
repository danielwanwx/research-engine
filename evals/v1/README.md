# Research Engine Eval v1

This directory freezes the B1-B8 benchmark taxonomy from the 2026-07-16
maximum-capability audit.

Run the deterministic offline gate:

    make eval

The command writes eval-results/scorecard.json and exits nonzero when a required
check fails. It performs no network calls.

Current CI gate:

- B6 adversarial evidence validity: valid HTML remains usable; login walls,
  network block pages, HTTP error bodies, unsupported binary content, and a
  simulated DNS/transport failure are detected through the connector path.
  Invalid rows remain observable but cannot support generic claims, pack claims,
  matrices, or conflict flags.

B1, B2, B4, and B5 remain optional live smoke profiles because public web results
are non-deterministic. B3, B7, and B8 are frozen as planned fixture profiles and
become CI gates when their corresponding backlog items are implemented.

A pull request changing collection, quality, or synthesis must keep the offline
scorecard passing. New fixtures should reproduce an observed failure and include
a deterministic acceptance threshold.
