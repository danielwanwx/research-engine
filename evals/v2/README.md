# Research Engine Eval v2

This suite freezes the offline B1-B10 acceptance gates for the M2 general-research
runtime. It performs no network calls and keeps the complete M0 adversarial validity
scorecard embedded in the v2 result.

Run:

    make eval

The command writes `eval-results/scorecard.json` and exits nonzero unless B1-B10 and
the nested M0 9/9, 5/5 validity gate all pass.

