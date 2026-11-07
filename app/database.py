"""
Database Schema, Migrations, and Backup/Restore Engine for
Autonomous AI Shopping Intelligence & Deal Sniper.

Supports SQLite out-of-the-box with zero external dependencies, while maintaining
PostgreSQL-compatible SQL dialect abstractions.
"""

import json
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_DB_PATH = os.environ.get(
    "SNIPER_DB_PATH",
    str(Path(__file__).resolve().parent.parent / "data" / "sniper_intelligence.db")
)

SCHEMA_MIGRATIONS = [
    {
        "version": 1,
        "name": "initial_core_tables",
        "sql": """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT,
            country TEXT DEFAULT 'AU',
            currency TEXT DEFAULT 'AUD',
            preferred_postcodes TEXT DEFAULT '["2150", "2000", "2121"]',
            preferred_retailers TEXT DEFAULT '["Officeworks", "JB Hi-Fi", "Amazon Australia", "The Good Guys", "Woolworths", "Coles", "Chemist Warehouse"]',
            blocked_brands TEXT DEFAULT '[]',
            blocked_retailers TEXT DEFAULT '[]',
            blocked_categories TEXT DEFAULT '[]',
            quiet_hours_start TEXT DEFAULT '22:30',
            quiet_hours_end TEXT DEFAULT '07:00',
            daily_summary_time TEXT DEFAULT '08:00',
            min_deal_score_wishlist INTEGER DEFAULT 70,
            min_deal_score_outside INTEGER DEFAULT 90,
            ai_provider TEXT DEFAULT 'local_ollama_fallback',
            telegram_chat_id TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS shopping_interests (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT 'user_primary',
            name TEXT NOT NULL,
            natural_query TEXT NOT NULL,
            interest_type TEXT NOT NULL CHECK(interest_type IN ('exact', 'multiple', 'broad')),
            category TEXT NOT NULL,
            preferred_brands TEXT DEFAULT '[]',
            excluded_brands TEXT DEFAULT '[]',
            max_budget REAL,
            target_price REAL,
            min_specs_json TEXT DEFAULT '{}',
            acceptable_models_json TEXT DEFAULT '[]',
            shortlist_json TEXT DEFAULT '[]',
            acceptable_conditions TEXT DEFAULT '["New"]',
            preferred_retailers TEXT DEFAULT '[]',
            preferred_postcodes TEXT DEFAULT '["2150", "2000"]',
            priority TEXT DEFAULT 'high' CHECK(priority IN ('critical', 'high', 'normal', 'low')),
            monitoring_frequency_mins INTEGER DEFAULT 15,
            notification_pref TEXT DEFAULT 'immediate',
            status TEXT DEFAULT 'active' CHECK(status IN ('active', 'paused', 'completed', 'archived')),
            engine_source TEXT DEFAULT 'Engine A',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS products (
            id TEXT PRIMARY KEY,
            canonical_name TEXT NOT NULL,
            brand TEXT NOT NULL,
            model_number TEXT,
            gtin_ean TEXT,
            mpn TEXT,
            generation TEXT,
            category TEXT NOT NULL,
            subcategory TEXT,
            variant_signature TEXT NOT NULL,
            attributes_json TEXT NOT NULL DEFAULT '{}',
            pack_quantity REAL DEFAULT 1.0,
            unit_measure TEXT DEFAULT 'item',
            base_unit_type TEXT DEFAULT 'item',
            normal_market_price_aud REAL NOT NULL,
            release_year INTEGER DEFAULT 2025,
            lifecycle_stage TEXT DEFAULT 'current',
            successor_model TEXT,
            image_key TEXT DEFAULT 'tech_watch_phone',
            official_url TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS price_observations (
            id TEXT PRIMARY KEY,
            product_id TEXT NOT NULL,
            retailer TEXT NOT NULL,
            seller_name TEXT NOT NULL,
            is_marketplace INTEGER DEFAULT 0,
            listed_price_aud REAL NOT NULL,
            shipping_cost_aud REAL DEFAULT 0.0,
            coupon_code TEXT,
            coupon_discount_aud REAL DEFAULT 0.0,
            cashback_pct REAL DEFAULT 0.0,
            loyalty_discount_aud REAL DEFAULT 0.0,
            condition TEXT DEFAULT 'New',
            stock_status TEXT DEFAULT 'Available',
            local_postcodes_json TEXT DEFAULT '{}',
            price_stage TEXT DEFAULT 'retailer_listed',
            source_url TEXT NOT NULL,
            source_type TEXT DEFAULT 'connector_poll',
            data_confidence REAL DEFAULT 0.95,
            expiry_date TEXT,
            is_short_dated INTEGER DEFAULT 0,
            is_sample_data INTEGER DEFAULT 0,
            observed_at TEXT NOT NULL,
            FOREIGN KEY(product_id) REFERENCES products(id)
        );

        CREATE TABLE IF NOT EXISTS evaluated_deals (
            id TEXT PRIMARY KEY,
            product_id TEXT NOT NULL,
            observation_id TEXT NOT NULL,
            interest_id TEXT,
            engine_type TEXT NOT NULL CHECK(engine_type IN ('Engine A', 'Engine B')),
            title TEXT NOT NULL,
            retailer TEXT NOT NULL,
            current_price_aud REAL NOT NULL,
            shipping_cost_aud REAL DEFAULT 0.0,
            final_checkout_cost_aud REAL NOT NULL,
            effective_after_cashback_aud REAL NOT NULL,
            normal_market_price_aud REAL NOT NULL,
            lowest_90d_price_aud REAL NOT NULL,
            discount_pct REAL NOT NULL,
            unit_price_display TEXT,
            deal_score INTEGER NOT NULL,
            classification TEXT NOT NULL CHECK(classification IN ('Exceptional', 'Excellent', 'Good', 'Ordinary')),
            suitability_score INTEGER NOT NULL,
            attractiveness_score INTEGER NOT NULL,
            seller_trust_score INTEGER NOT NULL,
            data_confidence_score INTEGER NOT NULL,
            urgency_state TEXT NOT NULL,
            verification_status TEXT NOT NULL,
            verification_checks_json TEXT NOT NULL,
            risk_flags_json TEXT NOT NULL DEFAULT '[]',
            stacking_breakdown_json TEXT NOT NULL DEFAULT '{}',
            buy_wait_recommendation TEXT NOT NULL,
            buy_wait_reasoning TEXT NOT NULL,
            explanation_bullets_json TEXT NOT NULL DEFAULT '[]',
            source_url TEXT NOT NULL,
            is_sample_data INTEGER DEFAULT 0,
            discovered_at TEXT NOT NULL,
            FOREIGN KEY(product_id) REFERENCES products(id)
        );

        CREATE TABLE IF NOT EXISTS watchlist_items (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT 'user_primary',
            product_id TEXT NOT NULL,
            deal_id TEXT,
            lifecycle_status TEXT NOT NULL CHECK(lifecycle_status IN (
                'Exploring', 'Researching', 'Waiting for a better price',
                'Ready to purchase', 'Purchased', 'Paused', 'No longer interested'
            )),
            target_price_aud REAL,
            recorded_purchase_price_aud REAL,
            benchmark_market_price_aud REAL,
            notes TEXT DEFAULT '',
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS notifications_log (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT 'user_primary',
            deal_id TEXT,
            channel TEXT DEFAULT 'telegram',
            notification_type TEXT NOT NULL CHECK(notification_type IN ('immediate_alert', 'daily_summary')),
            title TEXT NOT NULL,
            message_body TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('sent', 'pending_quiet_hours', 'suppressed_duplicate', 'suppressed_threshold', 'dismissed', 'expired')),
            dedup_signature TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS preference_events (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT 'user_primary',
            event_type TEXT NOT NULL CHECK(event_type IN (
                'deal_opened', 'deal_saved', 'deal_dismissed', 'deal_purchased',
                'category_explored', 'brand_blocked', 'retailer_blocked'
            )),
            product_id TEXT,
            category TEXT,
            brand TEXT,
            retailer TEXT,
            price_aud REAL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS saved_baskets (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT 'user_primary',
            name TEXT NOT NULL,
            items_json TEXT NOT NULL,
            preferred_postcode TEXT DEFAULT '2150',
            last_optimised_json TEXT DEFAULT '{}',
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS scheduler_jobs (
            job_id TEXT PRIMARY KEY,
            job_name TEXT NOT NULL,
            interval_seconds INTEGER NOT NULL,
            last_run_at TEXT,
            next_run_at TEXT,
            status TEXT DEFAULT 'healthy',
            run_count INTEGER DEFAULT 0,
            last_error TEXT
        );
        """
    }
]


class DatabaseManager:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.run_migrations()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def run_migrations(self) -> List[int]:
        applied = []
        with self.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                );
            """)
            cur = conn.execute("SELECT version FROM schema_migrations;")
            existing_versions = {row["version"] for row in cur.fetchall()}

            for migration in SCHEMA_MIGRATIONS:
                if migration["version"] not in existing_versions:
                    conn.executescript(migration["sql"])
                    conn.execute(
                        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                        (migration["version"], migration["name"], datetime.now(timezone.utc).isoformat())
                    )
                    applied.append(migration["version"])
            conn.commit()
        return applied

    def create_backup(self, backup_dir: Optional[str] = None) -> str:
        target_dir = Path(backup_dir) if backup_dir else Path(self.db_path).parent / "backups"
        target_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_file = target_dir / f"sniper_backup_{ts}.db"
        with self.get_connection() as src_conn:
            dst_conn = sqlite3.connect(str(backup_file))
            with dst_conn:
                src_conn.backup(dst_conn)
            dst_conn.close()
        return str(backup_file)

    def restore_backup(self, backup_file: str) -> bool:
        if not os.path.exists(backup_file):
            raise FileNotFoundError(f"Backup file not found: {backup_file}")
        shutil.copy2(backup_file, self.db_path)
        return True
