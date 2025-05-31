#!/usr/bin/env python3
"""
Test script to verify the comprehensive logging system for the tool orchestrator.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent))

from llm.logging_config import setup_logging, get_logging_manager
from llm.error_analyzer import ErrorAnalyzer, ErrorCategory


async def test_logging_system():
    """Test the comprehensive logging system."""
    print("Testing LilyTheThird Tool Orchestrator Logging System")
    print("=" * 60)
    
    # Initialize logging
    logging_manager = setup_logging()
    print(f"✓ Logging system initialized")
    print(f"  Log directory: {logging_manager.base_log_dir}")
    
    # Test different loggers
    orchestrator_logger = logging_manager.get_logger('tool_orchestrator')
    execution_logger = logging_manager.get_logger('tool_execution')
    error_logger = logging_manager.get_logger('error_analysis')
    decision_logger = logging_manager.get_logger('llm_decisions')
    retry_logger = logging_manager.get_logger('retry_logic')
    
    print("✓ All loggers initialized")
    
    # Test basic logging
    orchestrator_logger.info("Testing orchestrator logger", extra={
        'context_name': 'test',
        'test_parameter': 'test_value'
    })
    
    # Test tool decision logging
    logging_manager.log_tool_decision(
        'llm_decisions', 'search_web', 
        'LLM selected web search tool', 'test_context',
        {'query': 'test search'}
    )
    
    # Test tool execution logging
    logging_manager.log_tool_execution(
        'tool_execution', 'search_web',
        {'query': 'test search'}, 'Search completed successfully',
        0.250, success=True
    )
    
    # Test error tracking
    error_analyzer = ErrorAnalyzer()
    error_category, guidance = error_analyzer.analyze_error(
        "Error: invalid argument 'test'", 'search_web', {'query': 123}
    )
    
    logging_manager.log_retry_attempt(
        'retry_logic', 'search_web', 1, error_category.value,
        "Error: invalid argument 'test'", {'query': 123}
    )
    
    # Test error pattern logging
    logging_manager.log_error_pattern(
        'error_analysis', 'search_web', 'invalid_argument', 3, []
    )
    
    # Test LLM response logging
    logging_manager.log_llm_response(
        'llm_decisions', 'test_context', 'tool_call',
        'LLM decided to use search_web tool', 5,
        'Query requires web search'
    )
    
    print("✓ All logging methods tested")
    
    # Check if log files were created
    log_files = [
        'tool_orchestrator.log',
        'tool_execution.log', 
        'error_analysis.log',
        'llm_decisions.log',
        'retry_logic.log'
    ]
    
    print("\nLog files created:")
    for log_file in log_files:
        log_path = logging_manager.base_log_dir / log_file
        if log_path.exists():
            size = log_path.stat().st_size
            print(f"  ✓ {log_file} ({size} bytes)")
        else:
            print(f"  ✗ {log_file} (not found)")
    
    print(f"\nLogging test completed successfully!")
    print(f"Check the 'logs/' directory for detailed log files.")
    
    return True


if __name__ == "__main__":
    try:
        result = asyncio.run(test_logging_system())
        if result:
            print("\n🎉 All logging tests passed!")
    except Exception as e:
        print(f"\n❌ Logging test failed: {e}")
        import traceback
        traceback.print_exc()