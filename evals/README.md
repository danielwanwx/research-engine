# Research Engine offline evaluation

This suite freezes the current B1-B10 acceptance gates for the general
research runtime and includes the M0 adversarial evidence-validity fixture.
It performs no network calls.

Run:

    make eval

The command writes `eval-results/scorecard.json` and exits nonzero unless all
offline gates pass. The single `fixtures/` directory is the source of truth for
both benchmark and adversarial rows.
