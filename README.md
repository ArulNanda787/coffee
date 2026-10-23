# ☕ Coffee Price Comparison

Scrapes coffee powder listings from Amazon India (Nescafe, Nescafe Gold, Bru Gold, Davidoff), works out the cost per gram, and shows everything in a Streamlit dashboard.

## What's in this folder

| File | Purpose |
|------|---------|
| `main.py` | **Main scraper.** Searches Amazon India for each brand, uses Groq to extract weight from titles, writes `coffee_data.csv`. |
| `app.py` | **Streamlit dashboard.** Reads `coffee_data.csv`. |
| `coffee.py` | Alternate scraper. Scrapes the product URLs listed in `coffee_links.md` and writes `amazon_coffee_prices.csv` / `.json`. The dashboard does not read this output. |
| `coffee_data.csv` | Latest scraped data (overwritten on every `main.py` run). |
| `coffee_prices_*.csv/.xlsx` | Older exports kept for reference. |
| `pyproject.toml`, `uv.lock` | Dependency definitions (used by uv). |
| `requirements.txt` | Pinned dependencies for pip (see the note under Setup). |

## Requirements

- Python 3.9 or newer
- A free Groq API key from https://console.groq.com (only needed for scraping, not for viewing the dashboard)
- Run everything on your own computer. Amazon often blocks cloud servers.

## Setup (one time)

### Option A: uv (recommended)

Install uv from https://docs.astral.sh/uv/, then:

```bash
cd Co
uv sync
uv run playwright install chromium
```

### Option B: pip

```bash
cd Co
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install groq pandas playwright python-dotenv streamlit
playwright install chromium
```

> `requirements.txt` does not include `streamlit`, so install the packages above rather than `pip install -r requirements.txt`.

### Add your Groq API key

Create a file named `.env` in the `Co` folder with one line:

```
GROQ_API_KEY=your_key_here
```

## Usage

### 1. View the dashboard with the existing data

```bash
uv run streamlit run app.py        # or: streamlit run app.py
```

Opens at http://localhost:8501.

### 2. Re-scrape fresh data

```bash
cp coffee_data.csv coffee_data_backup.csv   # optional: keep the old data
uv run python main.py                       # or: python main.py
```

This runs a headless browser, searches each brand, and overwrites `coffee_data.csv`. When it finishes it prints a summary (number of products, how many have cost per gram, how many have reviews). Then start the dashboard (step 1) to see the new data.

Without uv, drop the `uv run` prefix and run the commands inside your activated virtual environment.

### 3. Scrape specific product URLs (optional)

Put Amazon product links in `coffee_links.md`, then:

```bash
uv run python coffee.py
```

This opens a visible browser window and writes `amazon_coffee_prices.csv` and `amazon_coffee_prices.json`.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `KeyError: 'GROQ_API_KEY'` | The `.env` file is missing, is not in the `Co` folder, or the key name is wrong. |
| `Executable doesn't exist` (Playwright) | Run `playwright install chromium`. |
| `ModuleNotFoundError: streamlit` | Install it: `pip install streamlit` (or `uv sync`). |
| Dashboard says the CSV is missing | Run it from inside the `Co` folder, or run `main.py` first. |
| Scrape returns few or no products | Amazon probably showed a CAPTCHA. Wait a while and retry. |
| Warning about "suspiciously short titles" | Amazon's page layout changed and the scraper's selectors need updating. |

## Notes

- Scraping Amazon may go against its terms of service. Use it for personal price comparison and keep request volumes low.
- Prices change often, so re-scrape before relying on the numbers.