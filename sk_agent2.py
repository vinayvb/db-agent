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
        # Call the MCP server's table_not_found tool to get the error message
        return await self._call_tool_and_unwrap("table_not_found", {"table": table})


async def main():
    kernel = Kernel()
    kernel.add_service(
        AzureChatCompletion(
            service_id="chat",
            deployment_name="gpt-4o",
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
        )
    )

    async with MCPPlugin(os.getenv("MCP_SERVER_URL")) as mcp_plugin:
        kernel.add_plugin(mcp_plugin, plugin_name="MCP")

        chat_completion = kernel.get_service(service_id="chat")

        execution_settings = AzureChatPromptExecutionSettings()
        execution_settings.function_choice_behavior = FunctionChoiceBehavior.Auto()
        execution_settings.temperature = 0

        history = ChatHistory()

        # Fetch all tables first (to pass to prompt)
        all_tables_raw = await kernel.get_plugin("MCP").list_tables()
        all_tables = []
        try:
            unwrapped = safe_unwrap(all_tables_raw)
            parsed = json.loads(unwrapped)
            all_tables = [t["table"] for t in parsed["output"]]
        except Exception as e:
            print(f"⛔ Could not parse tables: {e}")
            return

        # Lowercase all tables for case-insensitive comparison
        all_tables_lower = [t.lower() for t in all_tables]

        system_prompt = """
You are a SQL assistant.
You have these tables in the database: {tables}
Only use tables that exist here.
First, match tables only.
If you do not find a table in {tables} that's more than 95% similar in meaning to what the user asks, you must call table_not_found and STOP.
Do not guess table names or default to a table that exists. In such cases, you must call table_not_found and STOP.
Consider words like:
- Parking data and parking to match parking_data table, but something unrelated like billing shouldn't be considered similar to anything in {tables}.
Respond only with JSON: {{"matched_tables": ["..."]}}
""".format(tables=", ".join(all_tables))

        history.add_system_message(system_prompt)

        user_question = input("👉 Enter your question: ")
         #history.add_user_message("What are sample rows in parking data?")
         # Aggregation
         #history.add_user_message("what is the average base price from parking data you have?")
         #history.add_user_message("What is the total amount each customer has spent?")
         #history.add_user_message("What is the average unit price of items ordered?")
         # Joins
         #history.add_user_message("show me all the orders along with customer name")
         #history.add_user_message("list all products in order id 1")
         #history.add_user_message("Determine what items Alice ordered")
         #history.add_user_message("Determine what items Alice Smith ordered")
         # Nested Queries
         #history.add_user_message("List products that have never been ordered");
         #history.add_user_message("Show me customers who ordered more than 1 products in total");
         #history.add_user_message("Give me orders that include a product with price > 20");
         #Mixed
         #history.add_user_message("Show me top 5 expensive orders")
         #history.add_user_message("Give me all orders with more than 3 items")
         #history.add_user_message("Show all customers who have ordered a product costing more than $40, and how many such products they ordered")
        history.add_user_message(user_question)

        print(f"✅ Tables: {all_tables}")
        history.add_assistant_message(json.dumps({"tables": all_tables}))

        # --- Check if user is asking about any tables NOT present ---
        # Extract potential table names from user question (simplified: all words)
        # Extract possible table names appearing after from, join, or in keywords
        # Proceed with matching tables using the LLM
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

        # Check if any matched tables are unknown
        missing_tables = [t for t in matched if t.lower() not in all_tables_lower]

        if missing_tables:
            for missing_table in missing_tables:
                error_msg = await kernel.get_plugin("MCP").table_not_found(missing_table)
                print(error_msg)
            return  # stop if unknown tables requested

        if not matched:
            print("⛔ No matched tables found. Cannot generate SQL.")
            return


        # Proceed with matching tables using the LLM
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

        # Validate matched tables are non-empty and known
        if not matched:
            print("⛔ No matched tables found. Cannot generate SQL.")
            return

        missing_tables = [t for t in matched if t not in all_tables]
        if missing_tables:
            print(f"⛔ Matched tables not in database schema: {missing_tables}")
            return

        # Fetch schemas only for matched tables
        schemas = {}
        for table in matched:
            cols_raw = await kernel.get_plugin("MCP").list_columns(table)
            unwrapped = safe_unwrap(cols_raw)
            try:
                parsed = json.loads(unwrapped)
                schemas[table] = parsed["output"]
            except Exception as e:
                print(f"⛔ Could not parse columns for {table}: {e}")
                schemas[table] = []

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

        # Extract alias.column references
        used_cols = re.findall(r'\b\w+\.(\w+)\b', query)

        # Also catch bare columns in SELECT TOP N ...
        bare_cols = re.findall(r'\bselect\s+top\s+\d+\s+([\w,\s*]+?)\s+from', query, re.IGNORECASE)
        if bare_cols:
            for cols in bare_cols[0].split(','):
                col = cols.strip()
                if '.' in col:
                    used_cols.append(col.split('.')[1].strip())
                else:
                    used_cols.append(col)

        used_cols = set([col.lower() for col in used_cols])

        all_cols = [col["column"].lower() for t in schemas.values() for col in t]

        bad_cols = [c for c in used_cols if c not in all_cols and c != '*']

        print(f"✅ Columns used: {used_cols}")
        print(f"✅ Known columns: {all_cols}")

        if bad_cols:
            print(f"⛔ LLM used unknown columns: {bad_cols}")
            return

        # TABLE SANITY CHECK
        used_tables = set(re.findall(r'\bfrom\s+(\w+)', query, re.IGNORECASE) +
                          re.findall(r'\bjoin\s+(\w+)', query, re.IGNORECASE))

        bad_tables = [t for t in used_tables if t not in all_tables]

        print(f"✅ Tables used in SQL: {used_tables}")
        print(f"✅ Known matched tables: {matched}")

        if bad_tables:
            print(f"⛔ LLM used unknown tables: {bad_tables}")
            return

        print(f"✅ Running SQL: {query}")
        result = await kernel.get_plugin("MCP").run_sql(query)
        print(f"✅ Final result: {result}")


if __name__ == "__main__":
    asyncio.run(main())
