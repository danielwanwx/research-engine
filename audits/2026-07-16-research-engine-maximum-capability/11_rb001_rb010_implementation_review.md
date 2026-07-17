# RB-001 / RB-010 Implementation Review

## Outcome

Fable final verdict: **approve**. No unresolved P0-P2 findings.

## Implemented

- Web fetch rows now record HTTP status, content type, final URL, validity, and invalid reasons.
- Login walls, platform error shells, network block pages, HTTP errors, PDF/binary bodies,
  short web shells, and transport failures are observable but cannot support claims.
- Invalid evidence is excluded from generic claims, pack claims, structured-target claims,
  matrices, duplicate preference, and conflict flags.
- Invalid browser-rendered content cannot replace valid static content.
- Short manual/external evidence is not subjected to the web-shell length rule.
- A versioned B1-B8 benchmark plan and deterministic offline connector eval are available
  through make eval.

## Review loop

1. Initial Fable review found structured-target bypass, login heuristics, a shallow eval,
   Playwright replacement, external-row overreach, and external fixture path handling.
2. Second review confirmed those fixes and found a GitHub documentation false positive.
3. Third review confirmed the first refinement and found two remaining login-path/UI
   false positives.
4. Final review confirmed full-path-segment matching and the three-feature UI threshold.
   Verdict: approve.

## Verification

- Python 3.10: 145 tests passed.
- Ruff: all checks passed.
- Offline eval: 9/9 checks; 5/5 invalid probes detected.
- Live B6: X login wall, Reddit network block, HTTP 404, DNS failure, and PDF binary all
  detected; four returned rows were invalid; claim evidence IDs were empty.
- git diff --check: passed.

## Residual risk

Login-wall detection remains deterministic heuristic logic. Add future real failure samples
to the versioned fixture corpus instead of broadening single-word markers.

