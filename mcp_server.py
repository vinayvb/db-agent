import logging
import os
import asyncio
import json
import pyodbc
from dotenv import load_dotenv
from fastmcp import FastMCP, Context, tools

load_dotenv()
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def get_connection():
    server = os.getenv("HOST")
    database = os.getenv("DATABASE")
    username = os.getenv("APP_USER")
    password = os.getenv("APP_PASSWORD")

    if not all([server, database, username, password]):
        raise RuntimeError("Missing SQL connection environment variables")

    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={server};DATABASE={database};UID={username};PWD={password}"
    )
    return pyodbc.connect(conn_str)

mcp = FastMCP(
    name="SQL Tools to query an Azure SQL database",
    instructions="""
    This server provides SQL access tools.

    Use:
    - list_tables: to get available tables
    - list_columns: to view columns in a table
    - run_sql: to run a SELECT SQL query
    - table_not_found: to return a message when a table isnt found that matches user input
    """
)

@mcp.tool()
def list_tables() -> dict:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'")
        results = [{"schema": row.TABLE_SCHEMA, "table": row.TABLE_NAME} for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        logger.debug(f"Tables: {results}")
        # Wrap in expected format:
        return {"tool_result": "list_tables", "output": results}
    except Exception as e:
        logger.error(f"Error in list_tables: {e}")
        raise

@mcp.tool()
def list_columns(table: str) -> dict:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ?", table)
        results = [{"column": row.COLUMN_NAME, "type": row.DATA_TYPE} for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        logger.debug(f"Columns for table {table}: {results}")
        return {"tool_result": "list_columns", "output": results}
    except Exception as e:
        logger.error(f"Error in list_columns: {e}")
        raise

@mcp.tool()
def run_sql(query: str) -> dict:
    logger.info("IN RUN_SQL TOOL")
    try:
        if not query.strip().lower().startswith("select"):
            raise ValueError("Only SELECT queries are allowed.")
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(query)
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
        results = [dict(zip(columns, row)) for row in rows]
        cursor.close()
        conn.close()
        logger.debug(f"Query: {query} | Result: {results}")
        # Return JSON string wrapped in dict
        return {"tool_result": "run_sql", "output": results}
    except Exception as e:
        logger.error(f"Error in run_sql: {e}")
        raise

@mcp.tool()
def table_not_found(table: str) -> dict:
    return {
        "tool_result": "table_not_found",
        "output": f"Error: Table '{table}' not found in the database."
    }

if __name__ == "__main__":
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8080"))
    transport = os.environ.get("MCP_TRANSPORT", "streamable-http")

    print(f"Starting server with transport={transport}, host={host}, port={port}")
    mcp.run(transport=transport, host=host, port=port)
