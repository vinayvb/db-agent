import logging
import os
import asyncio
import json
import pyodbc
from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
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

mcp = FastMCP(name="SQL Database Agent MCP Server")

@mcp.tool()
def list_tables() -> dict:
    """List all available tables in the database"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_SCHEMA, TABLE_NAME"
        )
        tables = [{"schema": row.TABLE_SCHEMA, "table": row.TABLE_NAME} for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        logger.info(f"Listed {len(tables)} tables")
        return {"tables": tables}
    except Exception as e:
        logger.error(f"Error in list_tables: {e}")
        return {"error": str(e)}

@mcp.tool()
def list_columns(table: str) -> dict:
    """Get all columns for a specific table"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE "
            "FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_NAME = ? "
            "ORDER BY ORDINAL_POSITION",
            table
        )
        columns = [
            {"column": row.COLUMN_NAME, "type": row.DATA_TYPE, "nullable": row.IS_NULLABLE}
            for row in cursor.fetchall()
        ]
        cursor.close()
        conn.close()
        logger.info(f"Listed {len(columns)} columns for table {table}")
        return {"table": table, "columns": columns}
    except Exception as e:
        logger.error(f"Error in list_columns: {e}")
        return {"error": str(e)}

@mcp.tool()
def run_sql(query: str) -> dict:
    """Execute a SELECT SQL query and return results"""
    try:
        if not query.strip().lower().startswith("select"):
            return {"error": "Only SELECT queries are allowed"}
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(query)
        columns = [col[0] for col in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        results = [dict(zip(columns, row)) for row in rows]
        cursor.close()
        conn.close()
        logger.info(f"Executed query, returned {len(results)} rows")
        return {"rows": results, "count": len(results)}
    except Exception as e:
        logger.error(f"Error in run_sql: {e}")
        return {"error": str(e)}

@mcp.tool()
def table_not_found(table: str) -> dict:
    """Return an error message when a table is not found"""
    return {"error": f"Table '{table}' not found in the database"}

if __name__ == "__main__":
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8080"))
    transport = os.environ.get("MCP_TRANSPORT", "stdio")

    print(f"🚀 Starting MCP Server")
    print(f"📡 Transport: {transport}, Host: {host}, Port: {port}")
    mcp.run(transport=transport, host=host, port=port)