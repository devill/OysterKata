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
