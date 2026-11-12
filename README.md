# Kalshi mispricing and arbitrage research

Phase 1 records public Kalshi market metadata and order-book depth for local research. The first series is daily high temperature in New York City (`KXHIGHNY`).

## Run locally

Use Python 3.12 from the repository root. The collector uses the standard library and Kalshi's unauthenticated production REST API.

```sh
python3 -m unittest discover -s tests -v
python3 -m kalshi_engine.collect --once
python3 -m kalshi_engine.collect
```

The last command polls every 60 seconds while the process is running. Press Ctrl+C to stop. Use `--help` to see options. On the development Mac, the Python installation needed the system certificate bundle. If you see a certificate verification error and have the same bundle, prefix the command with `SSL_CERT_FILE=/etc/ssl/cert.pem`.

## Captures and provenance

Each sweep writes its own versioned JSON Lines file under the Git-ignored `captures/` directory. Use that directory for custom paths as well, for example `--output captures/experiment`. Keep API captures local pending a redistribution review. Keep credentials outside the repository.

- `sweep_start` records the series, requested depth, and local UTC start time.
- `series`, `markets`, and `event` record the original JSON payloads, including contract rules and source links. Market discovery follows all cursors for the open-market filter.
- `book` records the original YES and NO bid ladders for each discovered market. The default requests all available price levels. Prices and quantities retain their fixed-point strings. A bid on one side implies an ask on the other at one dollar minus the bid, with the same size.
- Each request stores its URL, ticker, local UTC start time and receipt or failure time, and HTTP status when available. Empty ladders are valid. Request failures and unavailable books are counted separately from empty books.
- `sweep_end` records completion time and coverage counts. Missing summary records indicate an interrupted sweep. A summary can also report request or discovery failures. `--once` exits with status 1 on detected failures or when it receives no books.
- Receipt times measure when the collector had each response. The REST responses provide snapshots without per-level exchange timestamps. A sweep spans multiple requests, and activity between polls is unobserved.

Official references are the [public market-data guide](https://docs.kalshi.com/getting_started/quick_start_market_data), [market listing endpoint](https://docs.kalshi.com/api-reference/market/get-markets), and [order-book endpoint](https://docs.kalshi.com/api-reference/market/get-market-orderbook).

See the [Phase 1 review](docs/phase-1-weather.md) for live coverage and the settlement map.

## Phase 2 snapshot scanner

Scan one complete capture from the Phase 1 review. The command evaluates all candidates at the capture's sweep end and prints JSON with the payout floors, simulated fills, fees, and decision for each candidate.

```sh
python3 -m kalshi_engine.scan captures/20261109T000433Z-KXHIGHNY-c05cb392.jsonl --event KXHIGHNY-26NOV09
```

Use a local capture containing the selected event. The scanner defaults to one whole contract per leg and a 10-second maximum age measured from the start of each book request. See the [Phase 2 review](docs/phase-2-weather.md) for the worked example and limits.

## Phase 3 live scanner and replay

From the project folder, run the live scanner once or let it poll every 60 seconds. On the development Mac, use the certificate bundle prefix shown below.

```sh
SSL_CERT_FILE=/etc/ssl/cert.pem python3 -m kalshi_engine.live --once
SSL_CERT_FILE=/etc/ssl/cert.pem python3 -m kalshi_engine.live
```

Each sweep saves a local capture and prints a JSON summary. The scanner checks the full six-strike NYC template and skips events with changed rules, fees, or settlement metadata outside the supported profile. Press Ctrl+C to stop polling.

Replay the three local checkpoint captures with the same parameters used in the review:

```sh
python3 -m kalshi_engine.replay captures/20261110T2055*.jsonl \
  --event KXHIGHNY-26NOV11 --delay 12 --max-age 15 --quantity 100
```

For other captures, pass the sweep paths and the event ticker they contain. See the [Phase 3 review](docs/phase-3-replay.md) for the execution assumptions and measured results.

## Phase 4 economics checkpoint

The scanner and replay support the reviewed December 2026 Fed funds target-rate event. From the project folder:

```sh
python3 -m unittest discover -s tests -v
python3 -m kalshi_engine.scan captures/20261110T210247Z-KXFED-c73bbfb8.jsonl --event KXFED-26DEC
SSL_CERT_FILE=/etc/ssl/cert.pem python3 -m kalshi_engine.live --series KXFED --once
```

The Fed live mode limits collection to the reviewed meeting. See the [economics review](docs/phase-4-economics.md) for the settlement source, exception handling and measured book coverage.

## Phase 4 sports checkpoint

Scan the local Miami–Utah full-game winner capture or take a fresh sweep while the reviewed event is open:

```sh
python3 -m unittest discover -s tests -v
python3 -m kalshi_engine.scan captures/20261110T211202Z-KXNBAGAME-ce4954a4.jsonl --event KXNBAGAME-26NOV10MIAUTA
SSL_CERT_FILE=/etc/ssl/cert.pem python3 -m kalshi_engine.live --series KXNBAGAME --once
```

The capture works with the same replay command using the NBA event ticker. The [sports review](docs/phase-4-sports.md) records the settlement cases and measured depth.

## Phase 5 statistical mispricing

Reproduce the fixed NBA study from the saved local request log and compare against any local depth captures:

```sh
python3 -m unittest discover -s tests -v
python3 -m kalshi_engine.model captures/phase-5/requests.jsonl \
  --depth captures/*KXNBAGAME*.jsonl > captures/phase-5/report.json
```

Omit the `--depth` argument if you have no NBA book captures. To fetch the same date window while it is still in Kalshi's recent-data tier, use `SSL_CERT_FILE=/etc/ssl/cert.pem python3 -m kalshi_engine.model_data --output captures/phase-5-download`. The downloader creates a new request log and requires an unused output filename. Once the recent-data cutoff moves past the cohort, replay the saved request log.

See the [Phase 5 research review](docs/phase-5-model.md) for the forecast design, holdout scores, calibration, and execution coverage.

## Portfolio dashboard

[Open the public dashboard](https://annikamattioli.github.io/kalshi-mispricing-and-arbitrage-engine/) · [Research write-up and reproducible setup](docs/portfolio-release.md)

The public demo uses fictional inputs. It can also open replay and model reports locally in the browser. The tracked dashboard data can be regenerated with `python3 scripts/build_demo.py`.

### Local dashboard for saved sweeps

From the repository root, start the dashboard on your Mac:

```sh
python3 -m kalshi_engine.dashboard
```

Open [the local dashboard](http://127.0.0.1:8765/?local=1). It checks the latest saved sweep for each series every five seconds and shows the capture time, age, book coverage, scanner decisions, and quote age at sweep end. A sweep older than 120 seconds is marked stale. Adjust that threshold with `--stale-after`, or use `--captures` to point at another capture folder. The dashboard reads existing files on this Mac. A refresh checks for saved sweeps and makes no exchange request. Press Ctrl+C to stop the server.
