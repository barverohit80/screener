# Episodic Pivot & Momentum Stock Screener

An automated stock screening pipeline that:
1. Syncs NSE Bhavcopies (price & delivery volume) into a Supabase PostgreSQL database.
2. Downloads NSE 52-week High/Low reports.
3. Scans historical data for Episodic Pivots (EPs) meeting price, volume, and momentum criteria.
4. Performs AI-driven Momentum Analysis using Google Gemini.
5. Generates Excel/Markdown reports and dispatches notifications to Telegram.
6. Runs automatically via **GitHub Actions every day at 4:00 PM IST**.

---

## 📅 Automated Schedule & Manual Triggers

The GitHub Actions workflow (`.github/workflows/daily_screener.yml`) runs on two triggers:
1. **Automated Cron**: Executes every day at **4:00 PM IST** (`10:30 AM UTC`).
2. **Manual Execution (`workflow_dispatch`)**: Can be manually triggered at any time:

### How to Trigger Manually:
- **Via GitHub Website (UI)**:
  1. Go to [Repository Actions Tab](https://github.com/barverohit80/screener/actions).
  2. Select **Daily Stock Screener Workflow** on the left menu.
  3. Click **Run workflow** on the right side and select **Run workflow**.

- **Via GitHub CLI (`gh`)**:
  ```bash
  gh workflow run daily_screener.yml --repo barverohit80/screener
  ```

---

## 🛠️ Project Setup & Prerequisites

### 1. Requirements
Install dependencies using pip:
```bash
pip install -r requirements.txt
```

### 2. Environment Variables & GitHub Secrets
The following secrets/environment variables are used by the scripts and workflow:

| Secret Name | Description | Default Fallback |
|---|---|---|
| `DB_CONNECTION_STRING` | Supabase PostgreSQL Connection String | Configured |
| `GEMINI_API_KEY` | Google Gemini API Key for AI Analysis | Configured |
| `TELEGRAM_TOKEN` | Telegram Bot Token for notification dispatch | Configured |
| `TELEGRAM_CHAT_ID` | Telegram Chat/Channel ID for reports | Configured |

To run locally with custom keys, copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

---

## 🚀 Running the Master Screener

To execute the complete end-to-end screener locally:
```bash
python master_screener.py
```

### Individual Modules
- **Bhavcopy Sync**: `python download_bhavcopy_to_supabase.py`
- **NSE 52-Week High Downloader**: `python download_nse_52wk.py`
- **Episodic Pivot Database Screener**: `python episodic_pivot_supabase.py`
- **EP D+1 Performance Tracker**: `python ep_d1_performance_tracker.py`
- **LLM Analyzer**: `python run_llm_screener.py`
- **Weekly Screener**: `python weekly_screener.py`

---

## 📁 Repository Structure
```
.
├── .github/
│   └── workflows/
│       └── daily_screener.yml    # GitHub Actions workflow (Runs daily 4 PM IST)
├── Daily_momentom_screener.txt   # Prompt template for Gemini LLM analysis
├── download_bhavcopy_to_supabase.py
├── download_nse_52wk.py
├── ep_d1_performance_tracker.py  # D+1 Performance tracker (50-day data retention)
├── episodic_pivot_supabase.py
├── llm_analyzer.py
├── master_screener.py            # Main pipeline orchestrator
├── run_llm_screener.py
├── telegram_notifier.py
├── weekly_screener.py
├── requirements.txt
├── .env.example
└── README.md
```
