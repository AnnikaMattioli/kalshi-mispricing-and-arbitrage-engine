# Prediction Market Research Lab

A Python research project for inspecting settlement-based relationships in prediction markets, replaying their execution, and measuring forecast calibration. The public dashboard is a static browser app using generated examples. The simulator models buys and fees and does not place orders.

## Research questions

1. Which combinations have a positive minimum payout over a verified outcome set?
2. How much depth can each leg consume at the signal, and what is left unpaired after delayed attempts?
3. Does a market-derived probability model improve on the midpoint on a later cohort?

The project uses the same depth and payout engine for NYC daily highs, a Fed funds threshold ladder, and an NBA full-game winner market. The review notes document source precision, fallback settlements, and why an ordinary payout floor can differ from the conservative floor. The research model compares logistic recalibration and price changes against a midpoint baseline. Its execution check reports quote-only results separately from entries with recorded depth. [Phase 5 method and results](phase-5-model.md)

## Reproduce the public examples

Use Python 3.12 and Node 22 from the repository root.

```sh
python3 -m unittest discover -s tests -v
python3 scripts/build_demo.py
python3 -m http.server 8765 --bind 127.0.0.1 --directory docs
```

Open http://127.0.0.1:8765/ in a browser. Stop the server with Ctrl+C before running the browser suite, which starts its own server on the same port.

```sh
npm ci
npx playwright install chromium
npm run test:e2e
```

The generator uses the same Python replay and probability evaluation as the research commands. The dashboard includes four fictional book snapshots, three execution assumptions, and a seeded synthetic model holdout. On the first basket, the instant scenario fills 10 contracts per leg. Under the delayed 50% depth scenario, one leg fills three and the other fills ten, leaving seven unpaired. Use the timeline and assumption selector to reproduce the result.

The dashboard accepts a JSON report emitted by `kalshi_engine.replay` or `kalshi_engine.model`. The file is read in the browser and stays there. The release contains synthetic data, source code, and research notes. Captures and per-game forecasts stay in the local ignored directory. Review applicable terms before collecting, modeling, or redistributing exchange data. [Kalshi data terms](https://kalshi-public-docs.s3.amazonaws.com/kalshi-data-terms-of-service.pdf)

## CV bullet

- Built a Python prediction-market research engine covering weather, Fed rates, and NBA contracts. Reused one settlement and depth simulator across all three, verified the pipeline with 26 Python tests, and published a browser-tested dashboard for replay, partial-fill inspection, and forecast calibration.
