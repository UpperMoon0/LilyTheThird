# LilyTheThird Tool Orchestrator Logging System

## Overview

The LilyTheThird project now includes a comprehensive logging system specifically designed to capture and analyze tool orchestrator behavior, error patterns, and LLM decision-making processes. This system provides detailed insights into why tool calls fail and how the retry logic responds to different error scenarios.

## Features

### 1. Structured JSON Logging
- All logs are output in structured JSON format for easy parsing and analysis
- Includes contextual information like tool names, error categories, retry counts, and execution times
- Supports custom fields for tool orchestrator specific events

### 2. Log Rotation
- Automatic log file rotation to prevent excessive disk usage
- Configurable file sizes and backup counts per logger
- Default settings: 5-20MB per log file with 3-5 backup files

### 3. Specialized Loggers
- **Tool Orchestrator**: Main orchestration logic, cycle management
- **Tool Execution**: Individual tool execution attempts and results
- **Error Analysis**: Error pattern detection and categorization
- **LLM Decisions**: LLM reasoning and decision tracking
- **Retry Logic**: Detailed retry attempt logging and strategy decisions

### 4. Custom Log Levels
- `TOOL_DECISION` (25): Tool selection decisions and reasoning
- `TOOL_RETRY` (23): Retry attempts with context
- `ERROR_PATTERN` (35): Detected repeated error patterns

## Log Files

All log files are created in the `logs/` directory:

- `tool_orchestrator.log` - Main orchestration flow (10MB, 5 backups)
- `tool_execution.log` - Tool execution details (5MB, 3 backups)
- `error_analysis.log` - Error patterns and analysis (5MB, 3 backups)
- `llm_decisions.log` - LLM reasoning and choices (20MB, 5 backups)
- `retry_logic.log` - Retry strategy and attempts (5MB, 3 backups)

## Key Logging Points

### Tool Selection Phase
```json
{
  "timestamp": "2025-05-31T08:19:00.000Z",
  "level": "TOOL_DECISION",
  "logger": "llm_decisions",
  "message": "Tool decision: search_web - Action type: tool_call",
  "tool_name": "search_web",
  "decision_reason": "Action type: tool_call",
  "context_name": "chatbox",
  "arguments": {"query": "latest AI developments"}
}
```

### Tool Execution Tracking
```json
{
  "timestamp": "2025-05-31T08:19:01.250Z",
  "level": "INFO",
  "logger": "tool_execution",
  "message": "Tool 'search_web' executed successfully in 1.250s",
  "tool_name": "search_web",
  "arguments": {"query": "latest AI developments"},
  "execution_time": 1.250
}
```

### Error Pattern Detection
```json
{
  "timestamp": "2025-05-31T08:19:05.000Z",
  "level": "ERROR_PATTERN",
  "logger": "error_analysis",
  "message": "Repeated error pattern detected for 'update_memory' - invalid_argument (count: 3)",
  "tool_name": "update_memory",
  "error_category": "invalid_argument",
  "pattern_count": 3
}
```

### Retry Logic Analysis
```json
{
  "timestamp": "2025-05-31T08:19:03.500Z",
  "level": "TOOL_RETRY",
  "logger": "retry_logic",
  "message": "Retry 2 for 'update_memory' - invalid_argument: Error: Invalid memory_id format",
  "tool_name": "update_memory",
  "retry_count": 2,
  "error_category": "invalid_argument",
  "arguments": {"memory_id": "invalid_id", "new_content": "test"}
}
```

## Usage

### Initialization
```python
from llm.logging_config import setup_logging, get_logging_manager

# Initialize the logging system
logging_manager = setup_logging()

# Get specific loggers
orchestrator_logger = logging_manager.get_logger('tool_orchestrator')
execution_logger = logging_manager.get_logger('tool_execution')
```

### Logging Tool Decisions
```python
logging_manager.log_tool_decision(
    'llm_decisions', tool_name, 
    decision_reason, context_name, 
    arguments
)
```

### Logging Tool Execution
```python
logging_manager.log_tool_execution(
    'tool_execution', tool_name, arguments, 
    result, execution_time, success=True
)
```

### Logging Retry Attempts
```python
logging_manager.log_retry_attempt(
    'retry_logic', tool_name, retry_count, 
    error_category, error_message, arguments
)
```

### Logging Error Patterns
```python
logging_manager.log_error_pattern(
    'error_analysis', tool_name, error_category, 
    pattern_count, recent_errors
)
```

## Debugging Tool Call Failures

### Common Error Patterns to Look For

1. **Repeated Argument Errors**
   - Look for `ERROR_PATTERN` level logs with `invalid_argument` category
   - Check the `arguments` field in retry logs to see what the LLM is providing
   - Review the enhanced retry messages being generated

2. **Memory ID Issues**
   - Search for `memory_id_error` category in error logs
   - Check if retrieved facts are being properly provided to the LLM
   - Look for argument regeneration attempts

3. **Tool Selection Failures**
   - Review `llm_decisions.log` for invalid decision formats
   - Check retry counts for tool selection phase
   - Look for LLM responses that don't match expected format

4. **Execution Timeouts**
   - Monitor `execution_time` values in tool execution logs
   - Look for network-related errors in web search tools
   - Check for rate limit patterns

### Log Analysis Queries

Using `jq` to analyze JSON logs:

```bash
# Find all failed tool executions
jq 'select(.level == "ERROR" and .logger == "tool_execution")' logs/tool_execution.log

# Count error patterns by tool
jq -r 'select(.level == "ERROR_PATTERN") | "\(.tool_name): \(.error_category)"' logs/error_analysis.log | sort | uniq -c

# Find tools with high retry counts
jq 'select(.retry_count >= 3)' logs/retry_logic.log

# Track LLM decision success rate
jq 'select(.logger == "llm_decisions")' logs/llm_decisions.log | jq -s 'group_by(.decision_type) | map({decision_type: .[0].decision_type, count: length})'
```

## Configuration

### Adjusting Log Levels
```python
# Change log level for specific logger
logging_manager.get_logger('tool_execution').setLevel(logging.DEBUG)
```

### Custom Log Directory
```python
# Use custom log directory
logging_manager = setup_logging(base_log_dir="custom_logs")
```

### Disabling Console Output
Console output is limited to WARNING level and above by default. To disable:
```python
# Remove console handlers from loggers
for logger_name in ['tool_orchestrator', 'tool_execution', 'error_analysis', 'llm_decisions', 'retry_logic']:
    logger = logging_manager.get_logger(logger_name)
    logger.handlers = [h for h in logger.handlers if not isinstance(h, logging.StreamHandler)]
```

## Testing

Run the logging system test:
```bash
python test_logging_system.py
```

This will verify that all loggers are working correctly and create sample log entries in each log file.

## Benefits for Debugging

1. **Root Cause Analysis**: Trace the exact sequence of events leading to tool failures
2. **Pattern Recognition**: Identify repeated mistakes and improve error messages
3. **Performance Monitoring**: Track execution times and identify slow tools
4. **LLM Behavior Analysis**: Understand how the LLM responds to different prompts and errors
5. **Retry Strategy Optimization**: Analyze which retry strategies are most effective
6. **Error Message Effectiveness**: See if enhanced retry messages actually help the LLM

## Best Practices

1. **Regular Log Review**: Periodically analyze logs to identify improvement opportunities
2. **Log Rotation Monitoring**: Ensure log files don't consume excessive disk space
3. **Error Pattern Tracking**: Use error pattern logs to improve tool documentation
4. **Performance Baselines**: Establish normal execution time ranges for each tool
5. **Integration Testing**: Use logs to verify that tool orchestrator improvements work as expected