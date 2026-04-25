import json
import os
import asyncio
from dotenv import load_dotenv

from langchain_openai import AzureChatOpenAI
from langchain_core.messages import ToolMessage
from fastmcp import Client

load_dotenv()

# Environment variables
API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
MCP_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8080/mcp")

# Initialize LLM
llm = AzureChatOpenAI(
    deployment_name=DEPLOYMENT,
    api_version="2025-01-01-preview",
    temperature=0,
    api_key=API_KEY,
    azure_endpoint=ENDPOINT,
)

# Global MCP client
mcp_client = None


async def init_mcp_client():
    """Initialize MCP client connection"""
    global mcp_client
    if mcp_client is None:
        mcp_client = Client(MCP_URL)
        await mcp_client.__aenter__()
    return mcp_client


async def close_mcp_client():
    """Close MCP client connection"""
    global mcp_client
    if mcp_client is not None:
        await mcp_client.__aexit__(None, None, None)
        mcp_client = None


async def call_mcp_tool(tool_name: str, args: dict) -> str:
    """Call a tool through the MCP server"""
    client = await init_mcp_client()
    try:
        result = await client.call_tool(tool_name, args)
        # Result is wrapped in {"content": [{"type": "text", "text": "..."}]}
        if isinstance(result, dict) and "content" in result:
            content = result["content"][0]
            if isinstance(content, dict) and "text" in content:
                return content["text"]
        return str(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ============================================================================
# AGENT TOOLS (defined as dicts for LLM tool calling)
# ============================================================================

list_tables = {
    "type": "function",
    "function": {
        "name": "list_tables",
        "description": "Get all available tables in the database. Returns a JSON string with all table names and schemas. Call this FIRST to see what tables exist.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
}

list_columns = {
    "type": "function",
    "function": {
        "name": "list_columns",
        "description": "Get all columns for a SPECIFIC table. Args: table: The exact table name (must exist in the database). IMPORTANT: Only call this AFTER confirming the table exists from list_tables(). Never guess table names.",
        "parameters": {
            "type": "object",
            "properties": {
                "table": {
                    "type": "string",
                    "description": "The exact table name"
                }
            },
            "required": ["table"]
        }
    }
}

table_not_found = {
    "type": "function",
    "function": {
        "name": "table_not_found",
        "description": "Call this when a requested table does not exist in the database. Args: table: The name of the table that was not found",
        "parameters": {
            "type": "object",
            "properties": {
                "table": {
                    "type": "string",
                    "description": "The name of the table that was not found"
                }
            },
            "required": ["table"]
        }
    }
}

run_sql = {
    "type": "function",
    "function": {
        "name": "run_sql",
        "description": "Execute a SELECT SQL query and return results. Args: query: The SQL SELECT query to execute. IMPORTANT: Only SELECT queries are allowed.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The SQL SELECT query to execute"
                }
            },
            "required": ["query"]
        }
    }
}


# ============================================================================
# AGENT STAGE 1: Table Discovery
# ============================================================================

async def run_stage1_table_discovery(user_question: str) -> str:
    """Stage 1: Discover available tables"""
    tools = [list_tables]
    llm_with_tools = llm.bind_tools(tools)
    
    system_prompt = """You are a database assistant. Your ONLY job in this step is to:
1. Call list_tables() to see what tables exist
2. Based on the user's question, identify which tables are relevant
3. Return a JSON response with the list of matched tables

Example response format:
{"matched_tables": ["customers", "orders"]}

Do NOT try to get column details or write SQL yet.
Do NOT guess or hallucinate table names."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_question},
    ]
    
    for iteration in range(3):
        response = llm_with_tools.invoke(messages)
        #messages.append({"role": "assistant", "content": response.content})
        messages.append(response)
        if hasattr(response, 'tool_calls') and response.tool_calls:
            for tool_call in response.tool_calls:
                tool_name = tool_call['name']
                
                if tool_name == 'list_tables':
                    result = await call_mcp_tool("list_tables", {})
                    print("RAW list_tables result:", result)  # Debug print
                else:
                    result = f"Unknown tool: {tool_name}"
                
                messages.append({
                    "role": "tool",
                    "content": result,
                    "tool_call_id": tool_call['id'],
                    "name": tool_name,
                })
        else:
            # No more tool calls
            return response.content if hasattr(response, 'content') else str(response)
    
    return "Failed to get response from stage 1"


# ============================================================================
# AGENT STAGE 2: Schema Discovery
# ============================================================================

async def run_stage2_schema_discovery(matched_tables: list, user_question: str) -> str:
    """Stage 2: Get schemas for matched tables"""
    tools = [list_columns, table_not_found]
    llm_with_tools = llm.bind_tools(tools)
    
    system_prompt = """You are a database assistant. Your ONLY job in this step is to:
1. For EACH table in the list provided, call list_columns() to get its schema
2. If any table is not found, call table_not_found() and note it
3. Compile all the schemas together and return them

Do NOT attempt to write SQL yet. Return the schema information clearly."""

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": f"Get the schema for these tables: {', '.join(matched_tables)}\n\nOriginal question: {user_question}"
        },
    ]
    
    for iteration in range(10):
        response = llm_with_tools.invoke(messages)
        #messages.append({"role": "assistant", "content": response.content})
        messages.append(response)
        if hasattr(response, 'tool_calls') and response.tool_calls:
            for tool_call in response.tool_calls:
                tool_name = tool_call['name']
                tool_input = tool_call['args']
                
                if tool_name == 'list_columns':
                    result = await call_mcp_tool("list_columns", {"table": tool_input.get('table', '')})
                elif tool_name == 'table_not_found':
                    result = await call_mcp_tool("table_not_found", {"table": tool_input.get('table', '')})
                else:
                    result = f"Unknown tool: {tool_name}"
                
                messages.append({
                    "role": "tool",
                    "content": result,
                    "tool_call_id": tool_call['id'],
                    "name": tool_name,
                })
        else:
            # No more tool calls
            return response.content if hasattr(response, 'content') else str(response)
    
    return "Failed to get response from stage 2"


# ============================================================================
# AGENT STAGE 3: Query Generation & Execution
# ============================================================================

async def run_stage3_query_execution(user_question: str, schemas_str: str) -> str:
    """Stage 3: Generate and execute SQL query"""
    tools = [run_sql]
    llm_with_tools = llm.bind_tools(tools)
    
    system_prompt = """You are a SQL expert. Your job is to:
1. Based on the user's question and the provided schemas, construct an accurate SQL SELECT query
2. Only use tables and columns that actually exist in the provided schema
3. Use TOP N syntax when appropriate
4. Call run_sql() with the query
5. Return the results in a clear, readable format

Important rules:
- ALWAYS match column names exactly to the schema provided
- Do NOT guess or assume column names
- Use proper SQL Server syntax
- Allow sql query logging for debugging
- Only SELECT queries allowed"""

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": f"""Available schemas:
{schemas_str}

User question: {user_question}

Generate the appropriate SQL query and execute it."""
        },
    ]
    
    for iteration in range(5):
        response = llm_with_tools.invoke(messages)
        #messages.append({"role": "assistant", "content": response.content})
        messages.append(response)
        
        if hasattr(response, 'tool_calls') and response.tool_calls:
            for tool_call in response.tool_calls:
                tool_name = tool_call['name']
                tool_input = tool_call['args']
                
                if tool_name == 'run_sql':
                    query = tool_input.get('query', '')

                    #print("\n🧠 Generated SQL:")
                    #print(query)
                    result = await call_mcp_tool("run_sql", {"query": tool_input.get('query', '')})
                else:
                    result = f"Unknown tool: {tool_name}"
                
                messages.append({
                    "role": "tool",
                    "content": result,
                    "tool_call_id": tool_call['id'],
                    "name": tool_name,
                })
        else:
            # No more tool calls
            return response.content if hasattr(response, 'content') else str(response)
    
    return "Failed to get response from stage 3"


# ============================================================================
# MAIN ORCHESTRATION
# ============================================================================

async def process_question(user_question: str):
    """Process a natural language question through the three-stage pipeline"""
    
    print("\n" + "="*80)
    print(f"👉 Question: {user_question}")
    print("="*80)
    
    # STAGE 1: Get tables
    print("\n📊 STAGE 1: Discovering relevant tables...")
    print("-" * 80)
    
    try:
        table_result = await run_stage1_table_discovery(user_question)
        print(f"\n✅ Stage 1 response:\n{table_result}")
        
        # Parse matched tables from the response
        matched_tables = extract_matched_tables(table_result)
        
        if not matched_tables:
            print("⛔ No relevant tables found. Please try another question.")
            return
            
    except Exception as e:
        print(f"⛔ Error in table discovery: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # STAGE 2: Get schemas
    print(f"\n🔍 STAGE 2: Fetching schema for tables: {matched_tables}")
    print("-" * 80)
    
    try:
        schema_result = await run_stage2_schema_discovery(matched_tables, user_question)
        print(f"\n✅ Stage 2 response:\n{schema_result}")
        schemas_str = schema_result
    except Exception as e:
        print(f"⛔ Error in schema discovery: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # STAGE 3: Generate and execute query
    print(f"\n⚙️  STAGE 3: Generating and executing SQL query...")
    print("-" * 80)
    
    try:
        query_result = await run_stage3_query_execution(user_question, schemas_str)
        print(f"\n✅ Final result:")
        print(query_result)
    except Exception as e:
        print(f"⛔ Error in query generation/execution: {e}")
        import traceback
        traceback.print_exc()
        return


def extract_matched_tables(response: str) -> list:
    """Extract matched table names from LLM response"""
    try:
        # Try to find JSON in the response
        import re
        json_match = re.search(r'\{[^{}]*"matched_tables"[^{}]*\}', response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return data.get("matched_tables", [])
    except Exception:
        pass
    
    # Fallback: try direct JSON parse
    try:
        tables = json.loads(response).get("matched_tables", [])
        return tables if tables else []
    except Exception:
        pass
    
    return []


async def main():
    """Main interactive loop"""
    print("✅ DB Agent Ready! (Using LangChain with MCP Server)")
    print("📝 Press Ctrl+C to exit\n")
    
    try:
        while True:
            user_input = input("👉 Enter your question: ").strip()
            if not user_input:
                print("⛔ Please enter a non-empty question.")
                continue
            
            await process_question(user_input)
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    finally:
        await close_mcp_client()


if __name__ == "__main__":
    asyncio.run(main())
