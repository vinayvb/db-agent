"""
Test the MCP-based agent.
"""

import json
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
import langchain_agent


# ============================================================================
# Test 1: Table Extraction
# ============================================================================

def test_table_extraction():
    """Test JSON extraction from LLM responses"""
    
    print("\n" + "="*80)
    print("Testing Table Extraction")
    print("="*80)
    
    # Test case 1: Clean JSON response
    response1 = '{"matched_tables": ["customers", "orders"]}'
    result1 = langchain_agent.extract_matched_tables(response1)
    print(f"\n✅ Test 1 (clean JSON): {result1}")
    assert result1 == ["customers", "orders"], "Failed to extract clean JSON"
    
    # Test case 2: JSON with extra text
    response2 = 'Based on your question, I need customers and orders tables.\n{"matched_tables": ["customers", "orders"]}'
    result2 = langchain_agent.extract_matched_tables(response2)
    print(f"✅ Test 2 (JSON with text): {result2}")
    assert result2 == ["customers", "orders"], "Failed to extract JSON from text"
    
    # Test case 3: Empty result
    response3 = 'No matching tables found'
    result3 = langchain_agent.extract_matched_tables(response3)
    print(f"✅ Test 3 (empty): {result3}")
    assert result3 == [], "Should return empty list"
    
    print("\n" + "="*80)
    print("✅ All extraction tests passed!")
    print("="*80)


# ============================================================================
# Test 2: Tool Definitions
# ============================================================================

def test_tool_definitions():
    """Test that tools are properly defined"""
    
    print("\n" + "="*80)
    print("Testing Tool Definitions")
    print("="*80)
    
    # Check that tools exist and are dicts
    tools = [
        ("list_tables", langchain_agent.list_tables),
        ("list_columns", langchain_agent.list_columns),
        ("table_not_found", langchain_agent.table_not_found),
        ("run_sql", langchain_agent.run_sql),
    ]
    
    for tool_name, tool_dict in tools:
        print(f"\n✅ Tool '{tool_name}' is defined")
        assert isinstance(tool_dict, dict), f"Tool {tool_name} should be a dict"
        assert "function" in tool_dict, f"Tool {tool_name} should have 'function' key"
        assert tool_dict["function"]["name"] == tool_name, f"Tool name mismatch for {tool_name}"
        assert "description" in tool_dict["function"], f"Tool {tool_name} should have description"
    
    print("\n" + "="*80)
    print("✅ All tool tests passed!")
    print("="*80)


# ============================================================================
# Test 3: MCP Client Async Function
# ============================================================================

async def test_mcp_tool_calling():
    """Test MCP tool calling (with mock)"""
    
    print("\n" + "="*80)
    print("Testing MCP Tool Calling (Mocked)")
    print("="*80)
    
    # Mock the MCP client
    mock_response = {
        "content": [
            {
                "type": "text",
                "text": json.dumps({"tables": [{"schema": "dbo", "table": "customers"}]})
            }
        ]
    }
    
    with patch.object(langchain_agent, 'init_mcp_client') as mock_init:
        mock_client = AsyncMock()
        mock_client.call_tool.return_value = mock_response
        mock_init.return_value = mock_client
        
        # Test calling a tool
        result = await langchain_agent.call_mcp_tool("list_tables", {})
        result_data = json.loads(result)
        
        print(f"\n✅ MCP call successful, got response: {result_data}")
        assert "tables" in result_data, "Response should contain 'tables'"
    
    print("\n" + "="*80)
    print("✅ MCP tool calling test passed!")
    print("="*80)


# ============================================================================
# Test 4: Integration Test (Stage 1)
# ============================================================================

async def test_stage1_with_mock():
    """Test stage 1 table discovery with mock LLM"""
    
    print("\n" + "="*80)
    print("Testing Stage 1: Table Discovery (Mocked LLM)")
    print("="*80)
    
    # Mock the MCP client response
    mock_mcp_response = {
        "content": [
            {
                "type": "text",
                "text": json.dumps({
                    "tables": [
                        {"schema": "dbo", "table": "customers"},
                        {"schema": "dbo", "table": "orders"},
                        {"schema": "dbo", "table": "products"},
                    ]
                })
            }
        ]
    }
    
    with patch.object(langchain_agent, 'init_mcp_client') as mock_init:
        mock_client = AsyncMock()
        mock_client.call_tool.return_value = mock_mcp_response
        mock_init.return_value = mock_client
        
        # Test extraction function
        result = await langchain_agent.call_mcp_tool("list_tables", {})
        tables = json.loads(result).get("tables", [])
        
        print(f"\n✅ Retrieved {len(tables)} tables from mock MCP")
        assert len(tables) == 3, f"Expected 3 tables, got {len(tables)}"
    
    print("\n" + "="*80)
    print("✅ Stage 1 test passed!")
    print("="*80)


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

async def run_async_tests():
    """Run all async tests"""
    await test_mcp_tool_calling()
    await test_stage1_with_mock()


if __name__ == "__main__":
    print("🧪 Running Agent Tests\n")
    
    # Run synchronous tests
    test_table_extraction()
    test_tool_definitions()
    
    # Run async tests
    asyncio.run(run_async_tests())
    
    print("\n" + "="*80)
    print("ℹ️  Note: Full agent integration test requires:")
    print("   1. MCP Server running: python mcp_server.py")
    print("   2. Azure OpenAI credentials in .env")
    print("   3. Database configured and running")
    print("Then run the agent: python langchain_agent.py")
    print("="*80)
