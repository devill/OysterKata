# Oyster Kata

This legacy like app prices a month of London Oyster card journeys and renders an HTML invoice.

Your task is to test it using [Constrained Tests](https://lexler.github.io/augmented-coding-patterns/patterns/constrained-tests/)

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

> Please create a method that generates a single invoice from data passed
> straight into it, so it can back a Constrained Test. The test should render the
> real HTML invoice and assert on that HTML — the template is part of what I want
> to cover — without ever touching the external services (the customer directory
> and the journey-history store), which are non-deterministic and unavailable
> from a test.
>
> Things to consider:
> - The system is untested and business-critical. Keep production changes minimal
>   and easy to validate — a behaviour-preserving extraction, with no change to
>   pricing logic, rounding or ordering, and no change to public signatures or
>   existing callers.
> - The test must be a thin wrapper around the real production code — don't
>   duplicate any pricing logic in it.
> - Use an approval test so the rendered HTML is the snapshot. Pin the current
>   behaviour exactly, quirks included; if you spot one, flag it rather than fix
>   it here.
> - Use atomic commits with clear messages.
> - Explore the code first. If such a method already exists, stop and point me to
>   it. Otherwise show me a short plan before changing anything.
