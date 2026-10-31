# 🔎 CostLens

**Find out why your data platform's cost is growing faster than its usage, and exactly what to switch off.**

Hackathon submission · Track 04 *The Work Behind the Work* · Problem: *platform cost growing faster than usage*

![CostLens overview](docs/screenshots/overview.png)

## Overview

Cloud bills say what you were charged. They don't say whether that money bought anything. CostLens
puts **cost next to usage** for every resource (warehouses, clusters, buckets, databases, SaaS seats),
finds the resources where the two have come apart, and turns each one into a ticket-ready finding:
**evidence, owner, action, dollars saved**.

On the included demo platform (13 resources, 5 teams, 180 days), cost grew **+38%** while usage
moved **-2%**. CostLens explains the gap and finds **$22.5k/month ($270k/year, 37% of spend)** in
fixable waste.

| What it does | How |
|---|---|
| **Cost vs usage gap** | Cost index vs a cost-weighted usage index (each resource indexed to its own usage: queries, task runs, reads, active users). The shaded gap is spend usage does not explain. |
| **7 waste detectors** | Idle resources · cost-per-unit jumps (e.g. warehouse resized, queries flat) · non-prod running 24/7 · over-provisioning · cold data on hot storage · unused licences · no owner tag |
| **Spike detection** | Robust rolling median/MAD per resource, weekdays and weekends compared separately; permanent step-changes are routed to the cost-per-unit check instead of raising false alarms |
| **Showback** | Spend, cost growth, usage growth and savings available per team |
| **Forecast** | 90-day projection "if nothing changes" vs "with CostLens fixes" |
| **AI narrative** | Executive summary and *Ask CostLens* chat powered by Claude, grounded only in computed numbers. **Works fully offline** with a rule-based fallback when no API key is set. |
| **Runs nightly** | CLI writes `report.md`, `findings.csv`, `snapshot.json`, posts to Slack, and can fail a CI job when waste passes a threshold |

Every number is produced by a plain, readable rule in [`costlens/detectors.py`](costlens/detectors.py),
so finance and platform leads can check the reasoning. The LLM only explains; it never invents figures.

See [docs/PROBLEM_STATEMENT.md](docs/PROBLEM_STATEMENT.md) for who has this problem and why it matters.

## Screenshots

| Findings with evidence and actions | Showback by team |
|---|---|
| ![Findings](docs/screenshots/findings.png) | ![Teams](docs/screenshots/teams.png) |
| **Spike detection** | **Forecast with and without fixes** |
| ![Spikes](docs/screenshots/spikes.png) | ![Forecast](docs/screenshots/forecast.png) |

## Setup

Requirements: **Python 3.10+**. No database, no cloud account and no API key needed to try it.

```bash
git clone https://github.com/<your-username>/costlens.git
cd costlens
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Optional, for AI summaries and open-ended chat:

```bash
cp .env.example .env               # then put your key in .env, or:
export ANTHROPIC_API_KEY=sk-ant-...
```

You can also paste a key into the app sidebar; it is kept only for that browser session.

## Usage

### Web app

```bash
streamlit run app.py
```

Open http://localhost:8501. The demo platform loads immediately.

1. **Overview**: the cost vs usage gap, the executive summary, savings by type.
2. **Findings**: filter by severity, team and type; open *Show the data behind this* to see cost and usage for that resource; download CSV or a Markdown report.
3. **Teams**: showback table, weekly spend by team, top resources.
4. **Spikes**: daily spend with anomalies marked.
5. **Forecast**: next 90 days with and without the fixes.
6. **Ask CostLens**: e.g. *"Where can we save the most?"*, *"What about the ML team?"*, *"Tell me about ANALYTICS_WH"*.
7. **Data**: the input table and the expected format.

To analyse your own platform choose **Upload my CSV** in the sidebar.

### Command line (for nightly runs)

```bash
python -m costlens.cli --demo --out reports/
python -m costlens.cli --input my_costs.csv --out reports/ --no-llm
python -m costlens.cli --input my_costs.csv --slack-webhook "$SLACK_WEBHOOK_URL" --fail-above 5000
```

Exit codes: `0` success, `1` bad input, `2` savings above `--fail-above`.

### Input format

One row per resource per day. Only the first four columns are required.

| Column | Required | Example |
|---|---|---|
| `date` | yes | `2026-10-01` |
| `resource_id` | yes | `wh-analytics` |
| `service` | yes | `Snowflake` |
| `cost_usd` | yes | `482.10` |
| `resource_name` | no | `ANALYTICS_WH` |
| `category` | no | `compute`, `warehouse`, `storage`, `database`, `saas`, `other` |
| `team` | no | `Analytics` (blank = untagged) |
| `environment` | no | `prod`, `staging`, `dev` |
| `usage_units` | no | `9120` |
| `usage_unit_name` | no | `queries` |
| `utilization_pct` | no | `63.5` |

FOCUS-style billing columns (`ChargePeriodStart`, `ResourceId`, `ServiceName`, `BilledCost`) are
mapped automatically. A sample is in [`data/demo_cost_usage.csv`](data/demo_cost_usage.csv).
Typical sources: AWS CUR / Azure / GCP billing exports joined with `SNOWFLAKE.ACCOUNT_USAGE`,
CloudWatch utilisation, Airflow task counts or SaaS seat reports.

## Project structure

```
costlens/
├── app.py                  Streamlit web app
├── costlens/
│   ├── data.py             load, validate, map columns, demo data generator
│   ├── analysis.py         KPIs, cost/usage index, team view, spikes, forecast
│   ├── detectors.py        the 7 waste detectors and savings estimates
│   ├── narrator.py         Claude summaries and Q&A + offline fallback
│   ├── pipeline.py         runs everything in one call
│   ├── report.py           Markdown, JSON and Slack output
│   └── cli.py              command-line entry point
├── data/demo_cost_usage.csv
├── tests/                  pytest suite (20 tests)
├── docs/                   problem statement, deployment guide, demo script, screenshots
├── pitch/                  pitch deck (PPTX + PDF)
├── Dockerfile
└── LICENSE                 MIT
```

## How the savings are estimated

| Finding | Saving assumed | Why |
|---|---|---|
| Idle resource (0 usage for 14+ days) | 95% of its cost | stop/delete; 5% kept for snapshots |
| Cost per unit jumped >50% | 85% of the excess over the old unit cost | size back to what usage needs |
| Non-prod running 24/7 | ~64% × 0.9 | stop nights and weekends |
| Over-provisioned (<25% avg utilisation) | 22–45% | one size down, or half if p95 < 40% |
| Cold storage growth | 45% | lifecycle to infrequent/archive tiers |
| Unused licences | seats above busy-day use + 15% | reclaim at renewal |
| Spikes, missing tags | $0 | reported for root cause and ownership, not counted as savings |

Only one saving is counted per resource, so nothing is double counted. All thresholds can be tuned in
the sidebar (**Detection settings**) or in `Thresholds` in code.

## Tests

```bash
pytest
```

The suite checks that every planted problem in the demo data is found, that healthy resources stay
quiet, that permanent resizes are not reported as spikes, that savings never exceed cost, and that
the CLI and offline answers work.

## Deployment

See **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** for Streamlit Community Cloud, Docker, a Linux VM, and
nightly runs with cron or GitHub Actions.

## Limitations and next steps

* Usage must be supplied alongside cost. Connectors for Snowflake `ACCOUNT_USAGE`, AWS CUR + CloudWatch
  and Databricks system tables would remove this step.
* Forecast is a deliberately simple linear trend.
* Next: one-click Jira/GitHub tickets per finding, and tracking realised savings after a fix.

## Licence

[MIT](LICENSE)
