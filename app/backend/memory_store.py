"""Long-term memory store backed by a Delta table in Unity Catalog.

Table: aia_multi_agent_catalog.default.agent_memories
Columns: id (STRING), user_id (STRING), content (STRING),
         category (STRING), saved_at (TIMESTAMP)

The table is auto-created on first use via Databricks SQL.
"""

import uuid
from datetime import datetime

from databricks.sdk import WorkspaceClient


CATALOG = "aia_multi_agent_catalog"
SCHEMA = "default"
TABLE = "agent_memories"
FULL_TABLE = f"{CATALOG}.{SCHEMA}.{TABLE}"

# Single user mode — no auth
DEFAULT_USER_ID = "default-user"


class DatabricksSQLMemoryStore:
    """CRUD operations for long-term memories stored in a Delta table."""

    def __init__(self):
        self.client = WorkspaceClient()
        self._warehouse_id = None

    @property
    def warehouse_id(self) -> str:
        if self._warehouse_id is None:
            warehouses = self.client.warehouses.list()
            for wh in warehouses:
                if wh.state and wh.state.value in ("RUNNING", "STARTING"):
                    self._warehouse_id = wh.id
                    break
            if self._warehouse_id is None:
                raise RuntimeError(
                    "No running SQL warehouse found. "
                    "Start a warehouse or set DATABRICKS_WAREHOUSE_ID."
                )
        return self._warehouse_id

    def _execute(self, statement: str) -> list[dict]:
        """Execute a SQL statement and return rows as dicts."""
        resp = self.client.statement_execution.execute_statement(
            warehouse_id=self.warehouse_id,
            statement=statement,
            wait_timeout="30s",
        )
        if resp.status and resp.status.state and resp.status.state.value == "FAILED":
            error_msg = resp.status.error.message if resp.status.error else "Unknown"
            raise RuntimeError(f"SQL execution failed: {error_msg}")

        rows = []
        if resp.result and resp.result.data_array:
            columns = [col.name for col in resp.manifest.schema.columns]
            for row in resp.result.data_array:
                rows.append(dict(zip(columns, row)))
        return rows

    def ensure_table(self):
        """Create the memories table if it doesn't exist."""
        self._execute(f"""
            CREATE TABLE IF NOT EXISTS {FULL_TABLE} (
                id STRING,
                user_id STRING,
                content STRING,
                category STRING,
                saved_at TIMESTAMP
            ) USING DELTA
        """)

    def save(
        self,
        content: str,
        category: str = "general",
        user_id: str = DEFAULT_USER_ID,
    ) -> dict:
        memory_id = str(uuid.uuid4())
        saved_at = datetime.now().isoformat()
        # Escape single quotes in content
        safe_content = content.replace("'", "\\'")
        safe_category = category.replace("'", "\\'")

        self._execute(f"""
            INSERT INTO {FULL_TABLE}
            VALUES (
                '{memory_id}',
                '{user_id}',
                '{safe_content}',
                '{safe_category}',
                '{saved_at}'
            )
        """)
        return {
            "id": memory_id,
            "content": content,
            "category": category,
            "saved_at": saved_at,
        }

    def recall(
        self,
        query: str = "",
        category: str = "",
        user_id: str = DEFAULT_USER_ID,
    ) -> list[dict]:
        conditions = [f"user_id = '{user_id}'"]

        if category:
            safe_cat = category.replace("'", "\\'")
            conditions.append(f"category = '{safe_cat}'")

        if query:
            safe_query = query.replace("'", "\\'")
            conditions.append(f"LOWER(content) LIKE LOWER('%{safe_query}%')")

        where = " AND ".join(conditions)
        rows = self._execute(
            f"SELECT id, content, category, saved_at FROM {FULL_TABLE} WHERE {where} ORDER BY saved_at DESC"
        )
        return rows

    def forget(
        self,
        content_substring: str,
        user_id: str = DEFAULT_USER_ID,
    ) -> dict | None:
        safe_sub = content_substring.replace("'", "\\'")
        rows = self._execute(f"""
            SELECT id, content FROM {FULL_TABLE}
            WHERE user_id = '{user_id}'
              AND LOWER(content) LIKE LOWER('%{safe_sub}%')
            LIMIT 1
        """)
        if not rows:
            return None

        memory_id = rows[0]["id"]
        deleted_content = rows[0]["content"]
        self._execute(f"DELETE FROM {FULL_TABLE} WHERE id = '{memory_id}'")
        return {"id": memory_id, "content": deleted_content}

    def list_all(self, user_id: str = DEFAULT_USER_ID) -> list[dict]:
        return self._execute(
            f"SELECT id, content, category, saved_at FROM {FULL_TABLE} "
            f"WHERE user_id = '{user_id}' ORDER BY saved_at DESC"
        )
