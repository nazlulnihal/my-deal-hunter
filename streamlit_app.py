"""
Streamlit Entrypoint (`streamlit_app.py`) for the
Autonomous AI Shopping Intelligence & Deal Sniper Platform.

Supports both:
- Root-level deployment (`streamlit_app.py` at repository root)
- Subfolder deployment (`sniper_platform/streamlit_app.py`)
while rendering the polished 12-screen custom consumer UI and providing a live
Python/SQLite backend sidebar bridge for natural-language interest creation,
deal sniping, basket optimisation, and Telegram Bot API alerts.
"""

import json
import os
import sys
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components

# Ensure the directory containing this file (and `app/`) is on sys.path
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from app.orchestrator import PlatformOrchestrator, DEFAULT_SHOPPING_BASKET

st.set_page_config(
    page_title="SniperAU — Autonomous AI Shopping Intelligence & Deal Sniper",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Load secrets from Streamlit Cloud `st.secrets` into environment if configured
try:
    for secret_key in ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "GEMINI_API_KEY", "OPENAI_API_KEY", "SNIPER_DASHBOARD_TOKEN"]:
        if secret_key in st.secrets and st.secrets[secret_key]:
            os.environ[secret_key] = str(st.secrets[secret_key])
except Exception:
    pass


@st.cache_resource
def get_orchestrator() -> PlatformOrchestrator:
    return PlatformOrchestrator()


orch = get_orchestrator()

# Streamlit Sidebar for Live Python Backend Controls, Natural Language Interests & Telegram Dispatch
with st.sidebar:
    st.markdown("### ⚡ SniperAU Live Python Backend")
    st.caption(
        "Direct control bridge to the SQLite WAL database, Deal Sniper engine, and Telegram Bot API."
    )

    if st.button("↻ Run Background Monitoring Cycle", use_container_width=True):
        res = orch.run_background_worker_cycle()
        st.success(f"Completed cycle across {len(res['jobs_updated'])} queues at {res['cycle_completed_at'][:19]}Z")

    st.divider()
    st.markdown("#### ✨ Add Natural-Language Interest (SQLite)")
    with st.form("add_nl_interest_form"):
        nl_query = st.text_input(
            "What do you want to buy?",
            value="Any good Android phone around AUD 750 with excellent battery life"
        )
        nl_submit = st.form_submit_button("Parse & Save Interest", use_container_width=True)
        if nl_submit and nl_query.strip():
            created = orch.add_natural_language_interest(nl_query.strip())
            shortlist = json.loads(created.get("shortlist_json", "[]"))
            st.success(
                f"Saved {created['interest_type'].upper()} interest in '{created['category']}' "
                f"with {len(shortlist)} shortlisted models."
            )

    st.divider()
    st.markdown("#### 🎯 Live Python Deal Sniper Trigger")
    with st.form("live_snipe_form"):
        prod_id = st.selectbox(
            "Product",
            options=[
                "prod_watch7_44mm",
                "prod_s25_ultra_256",
                "prod_pixel9a_256",
                "prod_sony_xm6",
                "prod_breville_bambino",
                "prod_lindt_cornet_333g",
                "prod_lavazza_oro_1kg"
            ],
        )
        retailer = st.selectbox(
            "Australian Retailer",
            options=["Officeworks", "JB Hi-Fi", "Amazon Australia", "The Good Guys", "Appliances Online", "Woolworths", "Coles", "eBay Australia"]
        )
        price_aud = st.number_input("Observed Price (AUD)", min_value=1.0, value=20.0, step=1.0)
        title_override = st.text_input("Optional Title Override (test accessory trap)", value="")
        submitted = st.form_submit_button("Snipe & Dispatch Telegram Alert", use_container_width=True)
        if submitted:
            out = orch.ingest_price_observation_and_snipe(
                product_id=prod_id,
                retailer=retailer,
                listed_price_aud=float(price_aud),
                listing_title_override=title_override.strip() or None
            )
            st.success(
                f"Deal Score: {out['evaluated_deal']['deal_score']}/100 ({out['evaluated_deal']['classification']}) | "
                f"Buy/Wait: {out['buy_wait']['recommendation']} | "
                f"Telegram Alert: {out['notification_result']['status']}"
            )

    st.divider()
    st.info(
        "**Hosting & Always-On Worker Note:** Streamlit Community Cloud sleeps when idle. "
        "To keep monitoring active 24/7 while away from the dashboard, enable the included "
        "`.github/workflows/sniper_cron.yml` GitHub Action (runs every 15 mins for free) or deploy "
        "`docker compose up -d` on an always-on host."
    )

# Render the full 12-screen custom consumer application
html_file = CURRENT_DIR / "index.html"
if html_file.exists():
    html_content = html_file.read_text(encoding="utf-8")
    components.html(html_content, height=1120, scrolling=True)
else:
    st.error(f"index.html not found at {html_file}")
