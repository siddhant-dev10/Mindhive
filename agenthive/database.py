"""AgentHive SQLite Persistence Layer.
Thread-safe, robust SQLite database engine with WAL mode enabled.
"""

import sqlite3
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from agenthive.config import settings

logger = logging.getLogger("agenthive.database")

class Database:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # Extract file path from sqlite:///...
            url = settings.database_url
            if url.startswith("sqlite:///"):
                db_path = url[len("sqlite:///"):]
            else:
                db_path = "data/agenthive.db"
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def init_db(self):
        """Initializes tables according to SYSTEM_DESIGN.md specifications."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Projects Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL,
                current_state TEXT NOT NULL DEFAULT 'DRAFT',
                switch_room_id TEXT,
                owner_discord_id TEXT,
                project_md_path TEXT NOT NULL,
                discord_channel_id TEXT,
                discord_thread_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # Independent Analysis Table (Phase 4 engine)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS independent_analyses (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                agent_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                understanding TEXT NOT NULL,
                architecture TEXT NOT NULL,
                tech_stack TEXT NOT NULL,
                implementation_plan TEXT NOT NULL,
                risks TEXT NOT NULL,
                missing_requirements TEXT NOT NULL,
                complexity TEXT NOT NULL,
                raw_payload TEXT,
                runtime_evidence_json TEXT NOT NULL DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # Discussion Messages Table (Phase 5 Switch Room)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS discussion_messages (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                turn_index INTEGER NOT NULL,
                sender_id TEXT NOT NULL,
                sender_name TEXT NOT NULL,
                sender_role TEXT NOT NULL,
                reply_to_agent TEXT,
                content TEXT NOT NULL,
                switch_event_id TEXT,
                switch_message_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # Additive migration for databases created before Switch event IDs were stored.
            discussion_columns = {
                row["name"] for row in cursor.execute("PRAGMA table_info(discussion_messages)").fetchall()
            }
            if "switch_event_id" not in discussion_columns:
                cursor.execute("ALTER TABLE discussion_messages ADD COLUMN switch_event_id TEXT")
            if "switch_message_id" not in discussion_columns:
                cursor.execute("ALTER TABLE discussion_messages ADD COLUMN switch_message_id TEXT")
            if "switch_room_id" not in discussion_columns:
                cursor.execute("ALTER TABLE discussion_messages ADD COLUMN switch_room_id TEXT")
            project_columns = {row["name"] for row in cursor.execute("PRAGMA table_info(projects)").fetchall()}
            if "owner_discord_id" not in project_columns:
                cursor.execute("ALTER TABLE projects ADD COLUMN owner_discord_id TEXT")
            analysis_columns = {row["name"] for row in cursor.execute("PRAGMA table_info(independent_analyses)").fetchall()}
            if "runtime_evidence_json" not in analysis_columns:
                cursor.execute("ALTER TABLE independent_analyses ADD COLUMN runtime_evidence_json TEXT NOT NULL DEFAULT '{}'")
            if "runtime_evidence_json" not in discussion_columns:
                cursor.execute("ALTER TABLE discussion_messages ADD COLUMN runtime_evidence_json TEXT NOT NULL DEFAULT '{}'")

            # Tasks Table (Phase 6 & 7 WBS)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                task_code TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                assigned_agent TEXT NOT NULL,
                priority TEXT NOT NULL DEFAULT 'MEDIUM',
                status TEXT NOT NULL DEFAULT 'PENDING_APPROVAL',
                human_approved INTEGER DEFAULT 0,
                dependencies TEXT DEFAULT '[]',
                acceptance_criteria TEXT DEFAULT '[]',
                completion_report TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            task_columns = {row["name"] for row in cursor.execute("PRAGMA table_info(tasks)").fetchall()}
            for column, declaration in (
                ("approved_by", "TEXT"),
                ("approved_at", "TEXT"),
                ("approved_task_hash", "TEXT"),
            ):
                if column not in task_columns:
                    cursor.execute(f"ALTER TABLE tasks ADD COLUMN {column} {declaration}")

            # Task Execution Logs (Phase 8 Execution & Sandbox)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_execution_logs (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                container_id TEXT,
                exit_code INTEGER,
                stdout TEXT,
                stderr TEXT,
                diff_patch TEXT,
                executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # Audit Log Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                event_name TEXT NOT NULL,
                actor TEXT NOT NULL,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            conn.commit()
            logger.info("Database initialized successfully at %s", self.db_path)

db = Database()
