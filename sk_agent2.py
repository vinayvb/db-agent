import asyncio
import json
import re
import os
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai import FunctionChoiceBehavior
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion, AzureChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory
from semantic_kernel.functions import kernel_function, KernelPlugin
from fastmcp import Client
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
MCP_URL = os.getenv("MCP_SERVER_URL")


def safe_unwrap(result):
    if isinstance(result, dict) and "content" in result:
        content = result["content"][0]
        if isinstance(content, dict) and "text" in content:
            return content["text"]
    elif hasattr(result, "text"):
        return result.text
    elif isinstance(result, list) and len(result) > 0 and hasattr(result[0], "text"):
        return result[0].text
    return result


class MCPPlugin(KernelPlugin):
    def __init__(self, base_url: str):
        super().__init__(name="MCP")
        self._base_url = base_url
        self._mcp_client = None

    async def __aenter__(self):
        self._mcp_client = Client(self._base_url)
        await self._mcp_client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._mcp_client:
            await self._mcp_client.__aexit__(exc_type, exc_val, exc_tb)

    async def _call_tool_and_unwrap(self, tool_name: str, args: dict):
        result = await self._mcp_client.call_tool(tool_name, args)
        return safe_unwrap(result)

    @kernel_function()
    async def list_tables(self) -> str:
        return await self._call_tool_and_unwrap("list_tables", {})

    @kernel_function()
    async def list_columns(self, table: str) -> str:
        return await self._call_tool_and_unwrap("list_columns", {"table": table})

    @kernel_function()
    async def run_sql(self, query: str) -> str:
        return await self._call_tool_and_unwrap("run_sql", {"query": query})

    @kernel_function()
    async def table_not_found(self, table: str) -> str:
        return await self._call_tool_and_unwrap("table_not_found", {"table": table})


def create_system_prompt(tables):
    return f"""
You are a SQL assistant.
You have these tables in the database: {', '.join(tables)}
Only use tables that exist here.
First, match tables only.
If you do not find a table in {tables} that's more than 95% similar in meaning to what the user asks, you must call table_not_found and STOP.
Do not guess table names or default to a table that exists. In such cases, you must call table_not_found and STOP.
Consider words like:
- Parking data and parking to match parking_data table, but something unrelated like billing shouldn't be considered similar to anything in {tables}.
Respond only with JSON: {{"matched_tables": ["..."]}}
"""


async def fetch_tables(mcp_plugin):
    raw = await mcp_plugin.list_tables()
    unwrapped = safe_unwrap(raw)
    parsed = json.loads(unwrapped)
    return [t["table"] for t in parsed["output"]]


async def fetch_schemas(mcp_plugin, matched_tables):
    schemas = {}
    for table in matched_tables:
        raw = await mcp_plugin.list_columns(table)
        unwrapped = safe_unwrap(raw)
        try:
            parsed = json.loads(unwrapped)
            schemas[table] = parsed["output"]
        except Exception:
            schemas[table] = []
    return schemas


def validate_matched_tables(matched, all_tables_lower):
    missing = [t for t in matched if t.lower() not in all_tables_lower]
    return missing


def extract_used_columns(query):
    used_cols = re.findall(r'\b\w+\.(\w+)\b', query)
    bare_cols = re.findall(r'\bselect\s+top\s+\d+\s+([\w,\s*]+?)\s+from', query, re.IGNORECASE)
    if bare_cols:
        for cols in bare_cols[0].split(','):
            col = cols.strip()
            if '.' in col:
                used_cols.append(col.split('.')[1].strip())
            else:
                used_cols.append(col)
    return set(col.lower() for col in used_cols)


def extract_used_tables(query):
    from_tables = re.findall(r'\bfrom\s+(\w+)', query, re.IGNORECASE)
    join_tables = re.findall(r'\bjoin\s+(\w+)', query, re.IGNORECASE)
    return set(from_tables + join_tables)


async def process_user_question(
        user_question, kernel, chat_completion, execution_settings, all_tables, all_tables_lower, mcp_plugin
):
    history = ChatHistory()
    system_prompt = create_system_prompt(all_tables)
    history.add_system_message(system_prompt)
    history.add_user_message(user_question)
    history.add_assistant_message(json.dumps({"tables": all_tables}))

    # Get matched tables from LLM
    match_result = await chat_completion.get_chat_message_content(
        chat_history=history,
        settings=execution_settings,
        kernel=kernel,
    )
    try:
        matched = json.loads(match_result.content)["matched_tables"]
    except Exception as e:
        print(f"⛔ Could not parse matched tables: {e}")
        return

    print(f"✅ Matched: {matched}")

    missing_tables = validate_matched_tables(matched, all_tables_lower)
    if missing_tables:
        for missing_table in missing_tables:
            error_msg = await mcp_plugin.table_not_found(missing_table)
            print(error_msg)
        return

    if not matched:
        print("⛔ No matched tables found. Cannot generate SQL.")
        return

    schemas = await fetch_schemas(mcp_plugin, matched)
    print(f"✅ Schemas: {schemas}")

    if not schemas or all(len(cols) == 0 for cols in schemas.values()):
        print("⛔ No schemas fetched or schemas are empty, aborting.")
        return

    history.add_system_message("""
Now generate the final SQL Server SELECT query using only columns you actually have.
Use TOP N syntax.
If a product has `name` not `product_name` use what exists.
ALWAYS match to real schema.
Respond ONLY with JSON: {"query": "..."}
""")
    history.add_assistant_message(
        json.dumps({
            "question": user_question,
            "matched_tables": matched,
            "schemas": schemas
        })
    )

    sql_plan = await chat_completion.get_chat_message_content(
        chat_history=history,
        settings=execution_settings,
        kernel=kernel,
    )
    print(f"🔍 Final SQL plan: {sql_plan.content}")

    try:
        query = json.loads(sql_plan.content)["query"]
    except Exception as e:
        print(f"⛔ Could not parse final SQL: {e}")
        return

    #used_cols = extract_used_columns(query)
    #all_cols = [col["column"].lower() for t in schemas.values() for col in t]
    #bad_cols = [c for c in used_cols if c not in all_cols and c != '*']

    #print(f"✅ Columns used: {used_cols}")
    #print(f"✅ Known columns: {all_cols}")

    #if bad_cols:
    #    print(f"⛔ LLM used unknown columns: {bad_cols}")
    #    return

    #used_tables = extract_used_tables(query)
    #bad_tables = [t for t in used_tables if t not in all_tables]

    #print(f"✅ Tables used in SQL: {used_tables}")
    #print(f"✅ Known matched tables: {matched}")

    #if bad_tables:
    #    print(f"⛔ LLM used unknown tables: {bad_tables}")
    #    return

    print(f"✅ Running SQL: {query}")
    result = await mcp_plugin.run_sql(query)
    print(f"✅ Final result: {result}\n")


async def main():
    kernel = Kernel()
    kernel.add_service(
        AzureChatCompletion(
            service_id="chat",
            deployment_name="gpt-4o",
            api_key=API_KEY,
            endpoint=ENDPOINT,
        )
    )

    async with MCPPlugin(MCP_URL) as mcp_plugin:
        kernel.add_plugin(mcp_plugin, plugin_name="MCP")

        chat_completion = kernel.get_service(service_id="chat")

        execution_settings = AzureChatPromptExecutionSettings()
        execution_settings.function_choice_behavior = FunctionChoiceBehavior.Auto()
        execution_settings.temperature = 0

        try:
            all_tables = await fetch_tables(mcp_plugin)
        except Exception as e:
            print(f"⛔ Could not fetch tables: {e}")
            return

        all_tables_lower = [t.lower() for t in all_tables]

        print("✅ Ready! Press Ctrl+C to exit.\n")

        try:
            while True:
                user_question = input("👉 Enter your question: ").strip()
                if not user_question:
                    print("⛔ Please enter a non-empty question.")
                    continue
                await process_user_question(
                    user_question,
                    kernel,
                    chat_completion,
                    execution_settings,
                    all_tables,
                    all_tables_lower,
                    mcp_plugin,
                )
        except KeyboardInterrupt:
            print("\n👋 Exiting. Goodbye!")


if __name__ == "__main__":
    asyncio.run(main())

#Sample questions
# Your original commented example questions for easy reference
# history.add_user_message("What are sample rows in parking data?")
# history.add_user_message("what is the average base price from parking data you have?")
# history.add_user_message("What is the total amount each customer has spent?")
# history.add_user_message("What is the average unit price of items ordered?")
# history.add_user_message("show me all the orders along with customer name")
# history.add_user_message("list all products in order id 1")
# history.add_user_message("Determine what items Alice ordered")
# history.add_user_message("Determine what items Alice Smith ordered")
# history.add_user_message("List products that have never been ordered")
# history.add_user_message("Show me customers who ordered more than 1 products in total")
# history.add_user_message("Give me orders that include a product with price > 20")
# history.add_user_message("Show me top 5 expensive orders")
# history.add_user_message("Give me all orders with more than 3 items")
# history.add_user_message("Show all customers who have ordered a product costing more than $40, and how many such products they ordered")
