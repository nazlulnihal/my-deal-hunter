# Autonomous AI Shopping Intelligence & Deal Sniper Platform

A personal, autonomous Australian shopping intelligence and extreme-bargain sniping platform built with **Python 3.11, FastAPI, SQLite (PostgreSQL-compatible), and a responsive 12-screen Single-Page Application UI**.

---

## 1. Architecture & Dual-Engine Design

The platform separates deterministic high-frequency execution from selective AI reasoning:

- **Engine A — Personal Wishlist Monitoring (Primary Resource Allocation)**:
  Continuously monitors explicit user shopping interests across **Exact Products (Type A)**, **Multiple Acceptable Products (Type B)**, and **Broad Natural-Language Requirements (Type C)**. Automatically researches qualifying models, creates editable shortlists, tracks historical pricing, and dispatches alerts at a configurable Deal Score threshold (default `>= 70/100`).
- **Engine B — Wider Market Exceptional Deal Discovery**:
  Independently scans Australian retail clearance feeds, structured schemas, and community bargain sources ([OzBargain](https://www.ozbargain.com.au)) across all physical product categories. Enforces a strict unsolicited notification threshold (`>= 90/100` Deal Score) and rolls discoveries into the configurable Daily Summary.

### Open-Source Ecosystem Audit & Architectural Reuse Decisions

| Open-Source Reference | Repository | Stack & License | Australian Coverage & Audit | Architectural Decision |
| :--- | :--- | :--- | :--- | :--- |
| **PriceBuddy** | [jez500/pricebuddy](https://github.com/jez500/pricebuddy) | PHP/Laravel + Scraper Service + Go CLI | Generic CSS selector scraping; requires per-store maintenance | Adopted its per-store selector isolation pattern; replaced manual URL-only entry with natural-language interest shortlisting. |
| **PriceStalker** | [mikeknight85/PriceStalker](https://github.com/mikeknight85/PriceStalker) | Node/Docker (Fork of PriceGhost) | JSON-LD metadata & CSS selector extraction first, stealth browser fallback | Adopted its **JSON-LD / Structured Schema first** extraction hierarchy (`app/connectors_and_basket.py`) to avoid unnecessary headless browser overhead. |
| **changedetection.io** | [dgtlmoon/changedetection.io](https://github.com/dgtlmoon/changedetection.io) | Python (Apache-2.0) | Universal page-diffing & conditional triggers | Adopted its deterministic content-hash / price-stage diffing model for clearance page monitoring without invoking an LLM on unchanged checks. |
| **BuyWhere MCP** | [BuyWhere/buywhere-mcp](https://github.com/buywhere/buywhere-mcp) | Model Context Protocol Server | Primarily Singapore, SEA, and US catalogs (limited native AU supermarket data) | Adopted its structured tool schema (`search_products`, `compare_products`, `find_best_price`, `get_deals`) for the internal Conversational AI Shopping Assistant (`app/orchestrator.py`). |
| **Telegram Price Tracker** | [bernalli/price-tracker-bot](https://github.com/SVM-98/price-tracker-bot) | Python + SQLite + Docker (MIT) | 17 global scrapers; hardened non-root Docker + SQLite migration stability | Adopted its non-root Docker hardening, SQLite WAL migration pattern (`app/database.py`), and interactive Telegram command surface (`app/notifications_and_preferences.py`). |

---

## 2. Operating Cost, Hosting & Free-Tier Transparency

| Component | Recommended Free / Low-Cost Option | What Is Genuinely Free | Usage Limits & Payment Method Notes |
| :--- | :--- | :--- | :--- |
| **Database** | Built-in **SQLite (WAL Mode)** (`./data/sniper_intelligence.db`) | 100% Free, zero external server overhead | Unlimited local reads/writes; seamlessly upgradable to PostgreSQL (Supabase / Neon free tiers offer 0.5 GB storage without a credit card). |
| **Notifications** | **Telegram Bot API** (`@BotFather`) | 100% Free forever | Rate limit of ~30 messages/sec globally (1 msg/sec per chat), no credit card required. |
| **AI Reasoning** | **Local Ollama (`llama3.2:3b`)** + Deterministic Rule Engine | 100% Free on local hardware | Zero API cost. Optional fallback to Gemini API Free Tier (rate-limited RPM/RPD, no billing required on free tier). Routine price polling **never** calls an LLM. |
| **Always-On Hosting** | Self-hosted Docker (Mini PC / Raspberry Pi / NAS) or Oracle Cloud Free Tier ARM VM | 100% Free electricity/hardware or Always-Free VM | Free web PaaS tiers (e.g., Render Free, Vercel, GitHub Pages) spin down idle containers and **cannot** run persistent 24/7 background bots without paid worker tiers. Always use a persistent VM or local Docker host. |

---

## 3. Quick Start & Running the Platform

### Run Automated Acceptance Tests
```bash
PYTHONPATH=. python3 tests/test_acceptance.py
```

### Start the FastAPI Backend & Background Worker Locally
```bash
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Run Standalone Background Monitoring Daemon (Headless / No UI Required)
```bash
PYTHONPATH=. python3 -m app.worker 0
```

### Run with Docker Compose
```bash
docker compose up -d --build
```

---

## 4. Honest Completion & Feature Status Matrix

- **Implemented & Verified via Automated Tests (`tests/test_acceptance.py`)**:
  - SQLite WAL database with automatic schema migrations, backup, and restore (`app/database.py`).
  - Universal 13-category product engine with GTIN/EAN/MPN hardware verification, variant mismatch detection (`40mm` vs `44mm`, `128GB` vs `256GB`), accessory-trap rejection, and grocery unit-price normalisation (`AUD / 100g`, `AUD / kg`, `AUD / 100ml`, `AUD / L`, `AUD / item`) (`app/product_engine.py`).
  - Natural-language shopping interest parser supporting **Exact (A)**, **Multiple Acceptable (B)**, and **Broad Requirements (C)** with automated model research and editable shortlists (`app/interest_engine.py`).
  - Explainable **0–100 Deal Sniper Engine** with separate sub-scores (**Product Suitability**, **Deal Attractiveness**, **Seller/Source Trust**, **Data Confidence**), automatic 8-point verification checklist, and **Deal Stacking Optimiser** keeping delayed cashback strictly separate from immediate checkout price (`app/deal_sniper.py`).
  - **7d / 30d / 90d / 180d Price History & Australian Buy/Wait Engine** tracking observed lows, averages, medians, volatility, and upcoming Australian sale events (Click Frenzy, Black Friday, Cyber Monday, Boxing Day, EOFY, Prime Day) (`app/price_history.py`).
  - **Multi-Retailer Shopping Basket Optimiser** comparing single-supermarket checkout vs split-basket Click & Collect / Home Delivery across [Woolworths](https://www.woolworths.com.au), [Coles](https://www.coles.com.au), [Amazon Australia](https://www.amazon.com.au), [Chemist Warehouse](https://www.chemistwarehouse.com.au), and [Big W](https://www.bigw.com.au) (`app/connectors_and_basket.py`).
  - **Telegram Notification Service** with SHA-256 duplicate suppression, quiet-hours queueing, per-engine score thresholds, and live Bot API HTTP dispatch when `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are provided (`app/notifications_and_preferences.py`).
- **Environment & Credential Boundaries**:
  - Outbound live scraping and live Telegram delivery require an environment with internet access and user-supplied `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` in `.env`. All seeded demonstration items are explicitly flagged with `is_sample_data = 1` (`[SAMPLE DATA]`).
