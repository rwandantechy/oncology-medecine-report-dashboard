# Oncology Medicine Report Dashboard

CLI scrapers for oncology medicine recalls from FDA Ghana, FDA USA, NAFDAC, and Health Canada. Results are stored in SQLite and exported to CSV.

## Run locally

From this directory, install the locked dependencies with [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

Run all scrapers using the default start date (`2020-01-01`):

```bash
PYTHONPATH=.:src uv run python src/main.py
```

To use a different start date:

```bash
PYTHONPATH=.:src uv run python src/main.py --start-date 2024-01-01
```

To refresh the oncology drug list from the NCI instead:

```bash
PYTHONPATH=src uv run python src/main.py --update-drug-database
```

The scraper writes:

- `data/recalls.db` — SQLite database
- `data/recalls.csv` — exported recall report
- `src/data/nci_oncology_drugs.json` — updated by `--update-drug-database`

Set `LOG_LEVEL` to change logging verbosity, for example:

```bash
LOG_LEVEL=DEBUG PYTHONPATH=.:src uv run python src/main.py
```

## Run tests

```bash
uv run pytest
```
