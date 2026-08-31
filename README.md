# Oyster Kata

This legacy like app prices a month of London Oyster card journeys and renders an HTML invoice.

Your task is to test it using [Constrained Tests](https://lexler.github.io/augmented-coding-patterns/patterns/constrained-tests/)

## Install

Requires Python 3.11+. The app itself has no third-party runtime dependencies,
so a checkout is enough to run it. The test suite needs `pytest` and
`approvaltests`.

Using [uv](https://docs.astral.sh/uv/) (a `uv.lock` is checked in):

```bash
uv sync --extra test   # creates .venv and installs the test dependencies
```

Or with a plain virtual environment and pip:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[test]"          # omit [test] if you only want to run the app
```

Run the tests with:

```bash
pytest
```

## Running it

Requires only Python 3.11+ (no third-party dependencies).

```bash
# Generate one invoice (writes out/<id>_<period>.html)
python -m oyster.cli alice 2026-04

# Generate all four sample invoices
python scripts/generate_all.py
```

Open the generated file in `out/` in a browser to see the rendered invoice.

## A prompt to get started

Stuck on where to begin? Paste something like this to your coding agent:

> I have a data-in method that renders an HTML invoice from a customer, a billing period and a list of trips, without touching the external services. Turn it into a single constrained approval test fed by many scenario files.
> Format:
> One YAML file per scenario, in a scenarios directory. Each file lists only the non-default inputs for that case — the customer fields it varies (home zone, enrolled programmes, commuter-club band and fee), the billing period, and the list of trips (touch-in time, mode, from/to station). Anything omitted falls back to a sensible default the test supplies, so each file stays small and the behaviour under test is obvious at a glance.
> The approved output is the rendered HTML invoice — one .approved.html per scenario, reviewed as a diff. PyYAML as a test-only dependency is fine.
> Build it as the four standard parts: one parametrised test with the scenario name as its id; a provider that loads every YAML file from the directory and builds the plain inputs; a namer mapping each scenario to its approved/received HTML; and a diff reporter that is quiet in CI and opens a diff tool locally. IMPORTANT use an existing approval test package, don't roll your own.
> Keep the test a thin wrapper around the real production code — no pricing logic in it, and the deterministic fare/zone/calendar rules used as-is. Never instantiate the external services. Pin current behaviour exactly; if you spot a quirk, flag it rather than fix it. Get one scenario passing end to end first, then add cases.

## A second prompt: grow coverage from scenario files

Once that data-in method exists, paste this to turn it into a constrained test
driven by many scenario files — so adding a case is just dropping in a file and
reviewing a diff:

> I have a data-in method that renders an HTML invoice from a customer, a billing
> period and a list of trips, without touching the external services. Turn it into
> a single constrained approval test fed by many scenario files.
>
> Format:
> - One YAML file per scenario, in a scenarios directory. Each file lists only the
>   **non-default** inputs for that case — the customer fields it varies (home zone,
>   enrolled programmes, commuter-club band and fee), the billing period, and the
>   list of trips (touch-in time, mode, from/to station). Anything omitted falls
>   back to a sensible default the test supplies, so each file stays small and the
>   behaviour under test is obvious at a glance.
> - The approved output is the rendered HTML invoice — one `.approved.html` per
>   scenario, reviewed as a diff. PyYAML as a test-only dependency is fine.
>
> Build it as the four standard parts: one parametrised test with the scenario
> name as its id; a provider that loads every YAML file from the directory and
> builds the plain inputs; a namer mapping each scenario to its approved/received
> HTML; and a diff reporter that is quiet in CI and opens a diff tool locally.
> **IMPORTANT** use an existing approval test package, don't roll your own.
>
> Keep the test a thin wrapper around the real production code — no pricing logic
> in it, and the deterministic fare/zone/calendar rules used as-is. Never
> instantiate the external services. Pin current behaviour exactly; if you spot a
> quirk, flag it rather than fix it. Get one scenario passing end to end first,
> then add cases.
