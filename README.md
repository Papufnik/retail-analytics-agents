# Retail Analytics Agents

Anonymized portfolio version of three single-domain "analyst" scripts I directed the AI-assisted development of for a real small retail business's reporting pipeline -- each one reads live inventory and sales data and answers exactly one operational question well, rather than trying to be a do-everything dashboard. Business name, real file paths, and specific data are illustrative, not real; the logic and structure are unchanged from what runs in production.

These are the "Layer 2" analysts that feed a larger executive-synthesis pipeline (a separate portfolio piece, [`digital-org-chart-reporting-pipeline`](../digital-org-chart-reporting-pipeline)) -- each one is expert in one thing and never cross-references another analyst's territory.

## The three agents

- **`margin_erosion_agent.py`** -- matches the POS system's current item cost against the most recent wholesale price actually paid per SKU, and flags anything where the wholesale price has risen without the POS system's cost field being updated to match. Catches silent margin erosion before it shows up as "why did this month's margin dip" three weeks later.
- **`stockout_prevention_agent.py`** -- computes real daily sales velocity per SKU from a trailing sales window, flags anything projected to run out within 14 days, and recommends a reorder quantity sized off actual demand.
- **`markdown_optimization_agent.py`** -- flags SKUs sitting on real stock with near-zero sales velocity, and recommends a tiered discount (15% / 25% / 35%) sized to protect a target gross margin band rather than a flat markdown.

## A real bug this caught (see `margin_erosion_agent.py`'s own header)

An earlier version of this agent tracked the **highest** wholesale price ever paid per SKU as "current cost" -- reasoning that vendor price hikes are what matter. Checked against the real wholesale order history, several SKUs had more than one price on record, and for at least two of them the price had actually come **down** over time. The old logic would report a stale, inflated cost for those SKUs and could manufacture a margin-erosion alert that wasn't real -- flagging a price drop as if it were a price problem. The fix tracks the cost from the **most recent order date** per SKU, which is what "what are we paying right now" actually means. This repo's sample data reproduces that exact scenario (a SKU whose wholesale price dropped between two real orders) specifically so the fixed behavior -- correctly *not* alerting on it -- is visible when you run the demo, alongside a second SKU with a genuine price increase that correctly does alert.

## Other real engineering notes preserved in the code

- **Data-source migration, not just a rewrite.** All three scripts originally read directly from timestamped CSV export filenames (`retail-items-2026-08-31.csv`, glob-and-sort-by-date logic to find "the latest" export). They were later migrated to read from a small SQL warehouse instead (`item_current`, a view that already resolves to the single latest export) -- and the migration notes in each script's header document a real subtlety this surfaced: the COGS table holds *multiple* overlapping report windows (a year-to-date cumulative window and several shorter partial windows), so a naive "give me the latest window" query would silently pick the wrong one. Each script explicitly filters to the same report-window start date the original CSV-filename convention used, rather than trusting a generic "latest" view.
- **Known column-naming quirks preserved deliberately, not "cleaned up."** The POS export never had a real `sku` column -- only `item id` -- and a separate `sales category` column that should be preferred over `category` when present. An earlier version silently fell back to the wrong field in both cases; the fix (and the comment explaining exactly why) is preserved in the code rather than quietly smoothed over, because the failure mode it prevents is specific and worth knowing about if this logic is ever touched again.
- **Bad rows are skipped and logged, never allowed to crash the whole agent.** All three scripts feed a daily executive email; one malformed CSV row silently killing an entire section's output is worse than one bad row being skipped with a `[WARN]` and the rest of the run completing.

## My role

I specified what "at risk of stockout," "markdown candidate," and "real margin erosion" should actually mean in business terms, reviewed the AI-assisted implementation against real exported data, and caught the highest-price-vs-most-recent-price bug in `margin_erosion_agent.py` before it shipped further -- the kind of bug that looks completely reasonable in isolation and only breaks once you check it against a SKU whose price actually went the other direction.

## Run it

```bash
pip install -r requirements.txt   # stdlib only -- nothing to install
python build_sample_data.py        # builds an illustrative SQLite warehouse + sample CSV
python demo.py                     # runs all three agents end to end
```

No real business data is required or included.

## Stack

Python, `sqlite3` (stdlib) for the warehouse read pattern, `csv` (stdlib) for the wholesale order history, JSON as the output format each agent writes for downstream consumption.
