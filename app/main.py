"""
FastAPI REST API & Background Worker Service for the
Autonomous AI Shopping Intelligence & Deal Sniper Platform.
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .orchestrator import PlatformOrchestrator, DEFAULT_SHOPPING_BASKET
from .connectors_and_basket import AUSTRALIAN_RETAILER_CONNECTORS
from .product_engine import UNIVERSAL_CATEGORIES

orchestrator = PlatformOrchestrator()
DASHBOARD_API_TOKEN = os.environ.get("SNIPER_DASHBOARD_TOKEN", "").strip()


def verify_optional_auth(x_sniper_token: Optional[str] = Header(default=None)) -> bool:
    if DASHBOARD_API_TOKEN and x_sniper_token != DASHBOARD_API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Sniper-Token header")
    return True


async def background_monitoring_loop():
    """
    Persistent background worker coroutine that executes scheduled monitoring ticks
    independently of whether any browser UI is connected.
    """
    interval = int(os.environ.get("SNIPER_WORKER_TICK_SECONDS", "60"))
    while True:
        try:
            orchestrator.run_background_worker_cycle()
        except Exception as exc:
            print(f"[BackgroundWorker] Error during cycle: {exc}")
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    worker_task = asyncio.create_task(background_monitoring_loop())
    yield
    worker_task.cancel()


app = FastAPI(
    title="Autonomous AI Shopping Intelligence & Deal Sniper API",
    version="2.0.0",
    description="Australian Multi-Category Deal Sniper, Natural-Language Wishlist Engine, Historical Price Intelligence & Basket Optimiser",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AddInterestRequest(BaseModel):
    natural_query: str
    max_budget: Optional[float] = None
    target_price: Optional[float] = None
    priority: Optional[str] = None


class StatusUpdateRequest(BaseModel):
    status: str


class LiveSnipeRequest(BaseModel):
    product_id: str
    retailer: str
    listed_price_aud: float
    shipping_cost_aud: float = 0.0
    coupon_code: Optional[str] = None
    coupon_discount_aud: float = 0.0
    cashback_pct: float = 0.0
    stock_status: str = "Available"
    condition: str = "New"
    source_url: str = "https://www.officeworks.com.au"
    listing_title_override: Optional[str] = None
    interest_id: Optional[str] = None
    simulated_time_hhmm: str = "14:00"


class AssistantQueryRequest(BaseModel):
    message: str
    confirm_destructive: bool = False


class BasketOptimiseRequest(BaseModel):
    fulfilment_mode: str = "click_and_collect"
    items: Optional[List[Dict[str, Any]]] = None


@app.get("/api/health")
def get_health():
    with orchestrator.db.get_connection() as conn:
        jobs = [dict(r) for r in conn.execute("SELECT * FROM scheduler_jobs").fetchall()]
        deals_count = conn.execute("SELECT COUNT(*) as c FROM evaluated_deals").fetchone()["c"]
        interests_count = conn.execute("SELECT COUNT(*) as c FROM shopping_interests WHERE status = 'active'").fetchone()["c"]
    return {
        "status": "operational",
        "background_worker": "active_independent",
        "active_interests_count": interests_count,
        "evaluated_deals_count": deals_count,
        "scheduler_jobs": jobs,
        "retailer_connectors_count": len(AUSTRALIAN_RETAILER_CONNECTORS)
    }


@app.get("/api/overview", dependencies=[Depends(verify_optional_auth)])
def get_overview():
    with orchestrator.db.get_connection() as conn:
        interests = [dict(r) for r in conn.execute("SELECT * FROM shopping_interests ORDER BY created_at DESC").fetchall()]
        deals = [dict(r) for r in conn.execute("SELECT * FROM evaluated_deals ORDER BY deal_score DESC, discovered_at DESC").fetchall()]
        products = [dict(r) for r in conn.execute("SELECT * FROM products").fetchall()]
        watchlist = [dict(r) for r in conn.execute("SELECT * FROM watchlist_items ORDER BY updated_at DESC").fetchall()]
        notifications = [dict(r) for r in conn.execute("SELECT * FROM notifications_log ORDER BY created_at DESC LIMIT 30").fetchall()]
        jobs = [dict(r) for r in conn.execute("SELECT * FROM scheduler_jobs").fetchall()]
        user = dict(conn.execute("SELECT * FROM users WHERE id = 'user_primary'").fetchone())

    return {
        "user": user,
        "categories": UNIVERSAL_CATEGORIES,
        "connectors": AUSTRALIAN_RETAILER_CONNECTORS,
        "interests": interests,
        "deals": deals,
        "products": products,
        "watchlist": watchlist,
        "notifications": notifications,
        "scheduler_jobs": jobs,
        "savings_summary": orchestrator.preference_engine.compute_savings_tracker(),
        "preference_profile": orchestrator.preference_engine.compute_preference_profile(),
        "default_basket_optimisation": orchestrator.basket_optimiser.optimise_basket(DEFAULT_SHOPPING_BASKET, "click_and_collect")
    }


@app.post("/api/interests", dependencies=[Depends(verify_optional_auth)])
def create_interest(req: AddInterestRequest):
    overrides = {}
    if req.max_budget is not None:
        overrides["max_budget"] = req.max_budget
    if req.target_price is not None:
        overrides["target_price"] = req.target_price
    if req.priority is not None:
        overrides["priority"] = req.priority
    return orchestrator.add_natural_language_interest(req.natural_query, overrides)


@app.patch("/api/interests/{interest_id}/status", dependencies=[Depends(verify_optional_auth)])
def patch_interest_status(interest_id: str, req: StatusUpdateRequest):
    return orchestrator.update_interest_status(interest_id, req.status)


@app.delete("/api/interests/{interest_id}", dependencies=[Depends(verify_optional_auth)])
def remove_interest(interest_id: str, confirm: bool = False):
    return orchestrator.delete_interest(interest_id, confirmed=confirm)


@app.post("/api/snipe", dependencies=[Depends(verify_optional_auth)])
def trigger_live_snipe(req: LiveSnipeRequest):
    return orchestrator.ingest_price_observation_and_snipe(
        product_id=req.product_id,
        retailer=req.retailer,
        listed_price_aud=req.listed_price_aud,
        shipping_cost_aud=req.shipping_cost_aud,
        coupon_code=req.coupon_code,
        coupon_discount_aud=req.coupon_discount_aud,
        cashback_pct=req.cashback_pct,
        stock_status=req.stock_status,
        condition=req.condition,
        source_url=req.source_url,
        listing_title_override=req.listing_title_override,
        interest_id=req.interest_id,
        simulated_time_hhmm=req.simulated_time_hhmm
    )


@app.get("/api/products/{product_id}/history", dependencies=[Depends(verify_optional_auth)])
def get_product_price_history(product_id: str):
    with orchestrator.db.get_connection() as conn:
        prod_row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        if not prod_row:
            raise HTTPException(status_code=404, detail="Product not found")
        prod = dict(prod_row)
        obs = [dict(r) for r in conn.execute("SELECT * FROM price_observations WHERE product_id = ? ORDER BY observed_at ASC", (product_id,)).fetchall()]

    hist = orchestrator.history_engine.compute_history_summary(obs, prod["normal_market_price_aud"])
    latest_price = obs[-1]["listed_price_aud"] if obs else prod["normal_market_price_aud"]
    bw = orchestrator.history_engine.evaluate_buy_or_wait(prod, latest_price, hist)
    return {"product": prod, "history": hist, "buy_wait": bw}


@app.post("/api/basket/optimise", dependencies=[Depends(verify_optional_auth)])
def optimise_shopping_basket(req: BasketOptimiseRequest):
    items = req.items if req.items else DEFAULT_SHOPPING_BASKET
    return orchestrator.basket_optimiser.optimise_basket(items, req.fulfilment_mode)


@app.post("/api/assistant", dependencies=[Depends(verify_optional_auth)])
def query_ai_assistant(req: AssistantQueryRequest):
    return orchestrator.handle_conversational_assistant(req.message, req.confirm_destructive)


@app.post("/api/backup", dependencies=[Depends(verify_optional_auth)])
def create_db_backup():
    path = orchestrator.db.create_backup()
    return {"backup_created": True, "backup_path": path}
