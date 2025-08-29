"""
Component tests for ToolOrchestrator.
Tests the integration between ToolOrchestrator and ErrorAnalyzer.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
# TODO: Update for Lily Core
# from llm.tool_orchestrator import ToolOrchestrator
# from llm.error_analyzer import ErrorCategory


class TestToolOrchestratorIntegration:
    """Test cases for ToolOrchestrator component integration."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.mock_llm_client = Mock()
        self.mock_tool_executor = Mock()
        self.mock_history_manager = Mock()
        self.allowed_tools = ["read_file", "write_file", "search_web"]
        
        self.orchestrator = ToolOrchestrator(
            llm_client=self.mock_llm_client,
            tool_executor=self.mock_tool_executor,
            history_manager=self.mock_history_manager,
            allowed_tools=self.allowed_tools
        )

    def test_initialization(self):
        """Test ToolOrchestrator initialization with ErrorAnalyzer."""
        assert self.orchestrator is not None
        assert hasattr(self.orchestrator, 'error_analyzer')
        assert hasattr(self.orchestrator, 'tool_failure_counts')
        assert hasattr(self.orchestrator, 'recent_errors')
        assert self.orchestrator.tool_failure_counts == {}
        assert self.orchestrator.recent_errors == []

    def test_track_tool_failure(self):
        """Test tool failure tracking functionality."""
        tool_name = "read_file"
        error_message = "File not found"
        arguments = {"file_path": "/nonexistent/file.txt"}
        error_category = ErrorCategory.RESOURCE_NOT_FOUND
        
        failure_count = self.orchestrator._track_tool_failure(
            tool_name, error_message, arguments, error_category
        )
        
        assert failure_count == 1
        assert self.orchestrator.tool_failure_counts[tool_name] == 1
        assert len(self.orchestrator.recent_errors) == 1
        
        error_record = self.orchestrator.recent_errors[0]
        assert error_record["tool_name"] == tool_name
        assert error_record["error_category"] == error_category
        assert error_record["error_message"] == error_message

    def test_get_tool_schema_info(self):
        """Test tool schema information extraction."""
        with patch('llm.tool_orchestrator.find_tool') as mock_find_tool:
            # Mock a tool definition
            mock_tool = Mock()
            mock_tool.argument_schema = Mock()
            mock_tool.argument_schema.model_json_schema.return_value = {
                'properties': {
                    'file_path': {
                        'type': 'string',
                        'description': 'Path to the file'
                    }
                },
                'required': ['file_path']
            }
            mock_find_tool.return_value = mock_tool
            
            schema_info = self.orchestrator._get_tool_schema_info("read_file")
            
            assert "read_file" in schema_info
            assert "file_path" in schema_info
            assert "string" in schema_info
            assert "[REQUIRED]" in schema_info

    def test_should_abort_retry_logic(self):
        """Test retry abortion logic."""
        tool_name = "write_file"
        error_message = "Permission denied"
        
        # Test with high retry count
        should_abort = self.orchestrator._should_abort_retry(tool_name, error_message, 5)
        assert should_abort == True
        
        # Test with low retry count
        should_abort = self.orchestrator._should_abort_retry(tool_name, error_message, 1)
        # Should depend on error analysis
        assert isinstance(should_abort, bool)

    def test_generate_retry_message(self):
        """Test enhanced retry message generation."""
        tool_name = "update_memory"
        error_message = "Invalid memory_id provided"
        arguments = {"memory_id": "invalid_id", "new_content": "test"}
        retry_count = 2
        retrieved_facts = "ID: 507f1f77bcf86cd799439011 | Content: Test fact"
        
        retry_message = self.orchestrator._generate_retry_message(
            tool_name, error_message, arguments, retry_count, retrieved_facts
        )
        
        assert "ENHANCED RETRY CONTEXT" in retry_message
        assert tool_name in retry_message
        assert "TOOL SCHEMA" in retry_message
        assert "ERROR ANALYSIS" in retry_message
        assert str(retry_count) in retry_message

    def test_get_tool_examples(self):
        """Test tool examples generation."""
        # Test examples for commonly failing tools
        examples = self.orchestrator._get_tool_examples("update_memory")
        assert "CORRECT EXAMPLE" in examples
        assert "memory_id" in examples
        assert "new_content" in examples
        
        examples = self.orchestrator._get_tool_examples("save_memory")
        assert "CORRECT EXAMPLE" in examples
        assert "content" in examples
        
        # Test for tool without examples
        examples = self.orchestrator._get_tool_examples("unknown_tool")
        assert examples == ""

    def test_recent_errors_limit(self):
        """Test that recent errors list is limited to 10 entries."""
        # Add more than 10 errors
        for i in range(15):
            self.orchestrator._track_tool_failure(
                f"tool_{i}", f"error_{i}", {}, ErrorCategory.UNKNOWN
            )
        
        # Should only keep the last 10
        assert len(self.orchestrator.recent_errors) == 10
        
        # Check that it kept the most recent ones
        assert self.orchestrator.recent_errors[0]["tool_name"] == "tool_5"
        assert self.orchestrator.recent_errors[-1]["tool_name"] == "tool_14"

    @pytest.mark.asyncio
    async def test_execute_tool_cycle_basic_structure(self):
        """Test basic structure of execute_tool_cycle method."""
        # Mock the dependencies
        self.mock_tool_executor.get_all_tool_names.return_value = ["read_file", "write_file"]
        self.mock_history_manager.get_history.return_value = []
        self.mock_history_manager.add_message = AsyncMock()
        
        # Mock LLM response to avoid tool call
        self.mock_llm_client.get_next_action = AsyncMock(return_value={
            "action_type": "text_response",
            "text": "No tools needed"
        })
        
        base_messages = [{"role": "system", "content": "You are a helpful assistant"}]
        
        messages, tool_calls = await self.orchestrator.execute_tool_cycle(
            base_system_messages=base_messages,
            max_tool_calls=3,
            context_name="test_context",
            retrieved_facts_context_string=None
        )
        
        assert isinstance(messages, list)
        assert isinstance(tool_calls, list)
        # Should have at least attempted to get next action
        self.mock_llm_client.get_next_action.assert_called_once()