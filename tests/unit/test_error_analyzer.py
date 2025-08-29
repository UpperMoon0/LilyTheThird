"""
Unit tests for ErrorAnalyzer component.
Tests the error categorization and guidance generation functionality.
"""

import pytest
# TODO: Update for Lily Core
# from llm.error_analyzer import ErrorAnalyzer, ErrorCategory


class TestErrorAnalyzer:
    """Test cases for ErrorAnalyzer class."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.analyzer = ErrorAnalyzer()

    def test_init(self):
        """Test ErrorAnalyzer initialization."""
        assert self.analyzer is not None
        assert hasattr(self.analyzer, 'error_patterns')
        assert hasattr(self.analyzer, 'analyze_error')

    def test_invalid_argument_detection(self):
        """Test detection of invalid argument errors."""
        error_message = "Invalid argument: file_path is required"
        tool_name = "read_file"
        arguments = {}
        
        category, guidance = self.analyzer.analyze_error(error_message, tool_name, arguments)
        
        assert category == ErrorCategory.INVALID_ARGUMENT
        assert "Invalid argument" in guidance
        assert tool_name in guidance

    def test_missing_argument_detection(self):
        """Test detection of missing argument errors."""
        error_message = "Missing required argument: content"
        tool_name = "write_file"
        arguments = {"file_path": "/test/path"}
        
        category, guidance = self.analyzer.analyze_error(error_message, tool_name, arguments)
        
        assert category == ErrorCategory.MISSING_ARGUMENT
        assert "Required argument" in guidance

    def test_memory_id_error_detection(self):
        """Test detection of memory ID errors."""
        error_message = "Memory replacement failed. The provided memory_id '123' was not found"
        tool_name = "update_memory"
        arguments = {"memory_id": "123", "new_content": "test"}
        
        category, guidance = self.analyzer.analyze_error(error_message, tool_name, arguments)
        
        assert category == ErrorCategory.MEMORY_ID_ERROR
        assert "memory_id" in guidance

    def test_unknown_error_fallback(self):
        """Test fallback to unknown category for unrecognized errors."""
        error_message = "Some completely unexpected error"
        tool_name = "test_tool"
        arguments = {}
        
        category, guidance = self.analyzer.analyze_error(error_message, tool_name, arguments)
        
        assert category == ErrorCategory.UNKNOWN
        assert tool_name in guidance

    def test_should_retry_with_same_arguments(self):
        """Test retry decision logic for different error categories."""
        # Network errors should be retryable
        assert self.analyzer.should_retry_with_same_arguments(ErrorCategory.NETWORK_ERROR) == True
        
        # Invalid arguments should not be retryable with same args
        assert self.analyzer.should_retry_with_same_arguments(ErrorCategory.INVALID_ARGUMENT) == False
        
        # Missing arguments should not be retryable with same args
        assert self.analyzer.should_retry_with_same_arguments(ErrorCategory.MISSING_ARGUMENT) == False

    def test_get_retry_strategy(self):
        """Test retry strategy generation."""
        # Test rate limit strategy
        strategy = self.analyzer.get_retry_strategy(ErrorCategory.RATE_LIMIT, 1)
        assert strategy["should_retry"] == True
        assert strategy["delay_multiplier"] > 1.0
        
        # Test invalid argument strategy with high retry count
        strategy = self.analyzer.get_retry_strategy(ErrorCategory.INVALID_ARGUMENT, 3)
        assert strategy["should_retry"] == False
        
        # Test network error strategy
        strategy = self.analyzer.get_retry_strategy(ErrorCategory.NETWORK_ERROR, 1)
        assert strategy["should_retry"] == True
        assert "delay_multiplier" in strategy

    def test_extract_invalid_arguments(self):
        """Test extraction of invalid argument names from error messages."""
        error_message = "Invalid value for file_path: must be absolute path"
        arguments = {"file_path": "relative/path", "content": "test"}
        
        invalid_args = self.analyzer._extract_invalid_arguments(error_message, arguments)
        
        assert "file_path" in invalid_args
        assert "content" not in invalid_args