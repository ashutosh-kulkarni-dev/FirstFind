# FirstFind backend

FastAPI + SQLAlchemy. Everything the live server needs is inside `app/`; the
Docker image copies only that folder.

## Layout

| Folder | What lives there |
|---|---|
| `app/routers/` | HTTP endpoints, one file per area (stores, auth, lists, chat, metro, zones). |
| `app/chat/` | The assistant: understanding a message, finding stores, trip planning. |
| `app/ml/` | Models only: sentiment, AI score, zones, recommender, store descriptions. |
| `app/google/` | Google Places client, daily store verification, candidate-store checks. |
| `app/data/` | Loading data into the database: stores CSV, reviews CSV, first-time seed. |
| `app/jobs/` | Scheduled work: the daily job and the scoring pipeline it runs. |
| `app/common/` | Small shared helpers: distance, opening hours, area names, API shapes. |
| `app/assets/` | JSON files the running server reads (metro stations, place names, advice). |
| `app/config.py`, `database.py`, `models.py`, `schemas.py`, `auth*.py` | Settings, DB session, tables, request shapes, login. |
| `tests/` | Pytest suite. `tests/smoke/` holds two end-to-end walkthroughs that pytest also runs. |

Rules that keep it tidy:

- A file the live server reads at runtime goes in `app/assets/`, never in the
  repo's `data/` folder (that folder is not deployed).
- `app/ml/` does not talk to Google or read CSV files; `app/data/` and
  `app/google/` do not contain model code.
- `app/common/` imports nothing from the other folders except `models`.

## Commands (run from `app/backend`)

```bash
python -m pytest -q                      # tests (every test starts with empty tables)
python -m ruff check .                   # lint
python -m vulture                        # unused code
python -m app.jobs.daily --no-google     # score reviews, rebuild zones and recommendations
python -m app.jobs.daily --import-csv    # load data/import/*.csv first
python -m app.data.importer              # dry-run report of the stores CSV
python -m app.google.candidates          # candidate-store status (no API calls)
python -m app.ml.eval_sentiment          # sentiment accuracy on data/sentiment_eval.csv
```

`python -m app.data.seed` DROPS every table and rebuilds from `data/stores.json`.
Never run it against the production database.
