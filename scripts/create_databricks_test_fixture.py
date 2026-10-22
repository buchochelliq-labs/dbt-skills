import base64
import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


CATALOG = "dbt_skills_test"
SCHEMA = "integration"
TABLES = {
    "customers": "customers_pk",
    "orders": "orders_customer_fk",
}
POLL_TIMEOUT_SECONDS = 300


class DatabricksError(RuntimeError):
    pass


def required_env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise DatabricksError(f"Required environment variable {name} is missing")
    return value


def request_json(url, *, method="GET", headers=None, body=None):
    request = Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urlopen(request, timeout=60) as response:
            content = response.read()
    except HTTPError as error:
        raise DatabricksError(
            f"Databricks API request failed with HTTP {error.code}"
        ) from None
    except (TimeoutError, URLError) as error:
        raise DatabricksError(
            f"Databricks API request failed: {type(error).__name__}"
        ) from None
    try:
        return json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise DatabricksError("Databricks API returned invalid JSON") from None


def get_access_token(host, client_id, client_secret):
    credentials = base64.b64encode(
        f"{client_id}:{client_secret}".encode("utf-8")
    ).decode("ascii")
    body = urlencode(
        {"grant_type": "client_credentials", "scope": "sql"}
    ).encode("ascii")
    result = request_json(
        f"{host}/oidc/v1/token",
        method="POST",
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        body=body,
    )
    token = result.get("access_token")
    if not isinstance(token, str) or not token:
        raise DatabricksError("OAuth response did not include an access token")
    return token


def execute_statement(host, token, warehouse_id, statement):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = json.dumps(
        {
            "statement": statement,
            "warehouse_id": warehouse_id,
            "wait_timeout": "30s",
            "on_wait_timeout": "CONTINUE",
            "disposition": "INLINE",
            "format": "JSON_ARRAY",
        }
    ).encode("utf-8")
    result = request_json(
        f"{host}/api/2.0/sql/statements",
        method="POST",
        headers=headers,
        body=payload,
    )
    statement_id = result.get("statement_id")
    if not isinstance(statement_id, str) or not statement_id:
        raise DatabricksError("SQL API did not return a statement ID")

    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while True:
        status = result.get("status", {}).get("state")
        if status == "SUCCEEDED":
            return result
        if status in {"FAILED", "CANCELED", "CLOSED"}:
            error = result.get("status", {}).get("error", {})
            state = error.get("sql_state", "unknown")
            code = error.get("error_code", "unknown")
            message = error.get("message", "No error details returned")
            raise DatabricksError(
                f"SQL statement {status} (SQLSTATE {state}, {code}): {message}"
            )
        if time.monotonic() >= deadline:
            raise DatabricksError("Timed out waiting for SQL statement completion")
        time.sleep(2)
        result = request_json(
            f"{host}/api/2.0/sql/statements/{statement_id}",
            headers=headers,
        )


def verify_constraint(host, token, warehouse_id, table, constraint):
    result = execute_statement(
        host,
        token,
        warehouse_id,
        f"SHOW CREATE TABLE {CATALOG}.{SCHEMA}.{table}",
    )
    rows = result.get("result", {}).get("data_array", [])
    ddl = "\n".join(
        cell
        for row in rows
        if isinstance(row, list)
        for cell in row
        if isinstance(cell, str)
    )
    if constraint.lower() not in ddl.lower():
        raise DatabricksError(
            f"{CATALOG}.{SCHEMA}.{table} exists but is missing "
            f"the expected constraint {constraint}; no table was replaced"
        )


def main():
    host = required_env("DATABRICKS_HOST").rstrip("/")
    if not host.startswith("https://"):
        raise DatabricksError("DATABRICKS_HOST must use HTTPS")
    client_id = required_env("DATABRICKS_CLIENT_ID")
    client_secret = required_env("DATABRICKS_CLIENT_SECRET")
    warehouse_id = required_env("SQL_WAREHOUSE_ID")

    token = get_access_token(host, client_id, client_secret)
    execute_statement(
        host,
        token,
        warehouse_id,
        f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA} "
        "COMMENT 'Synthetic dbt-skills catalog integration fixture'",
    )
    execute_statement(
        host,
        token,
        warehouse_id,
        f"""CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.customers (
            customer_id BIGINT NOT NULL COMMENT 'Synthetic customer identifier',
            customer_name STRING COMMENT 'Synthetic customer name',
            region STRING COMMENT 'Synthetic sales region',
            CONSTRAINT customers_pk PRIMARY KEY (customer_id)
        ) USING DELTA COMMENT 'Synthetic customers for metadata integration tests'""",
    )
    execute_statement(
        host,
        token,
        warehouse_id,
        f"""CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.orders (
            order_id BIGINT NOT NULL COMMENT 'Synthetic order identifier',
            customer_id BIGINT COMMENT 'References the synthetic customer',
            ordered_at TIMESTAMP COMMENT 'Synthetic order timestamp',
            amount DECIMAL(10, 2) COMMENT 'Synthetic order amount',
            status STRING COMMENT 'Synthetic order status',
            CONSTRAINT orders_pk PRIMARY KEY (order_id),
            CONSTRAINT orders_customer_fk FOREIGN KEY (customer_id)
                REFERENCES {CATALOG}.{SCHEMA}.customers
        ) USING DELTA COMMENT 'Synthetic orders for metadata integration tests'""",
    )

    verify_constraint(
        host, token, warehouse_id, "customers", TABLES["customers"]
    )
    verify_constraint(host, token, warehouse_id, "orders", "orders_pk")
    verify_constraint(host, token, warehouse_id, "orders", TABLES["orders"])
    print(
        f"Verified synthetic Unity Catalog fixture: "
        f"{CATALOG}.{SCHEMA}.customers and {CATALOG}.{SCHEMA}.orders"
    )
    print("No data was inserted and no existing table was replaced.")


if __name__ == "__main__":
    try:
        main()
    except (DatabricksError, OSError) as error:
        print(f"Databricks fixture setup failed: {error}", file=sys.stderr)
        sys.exit(1)
