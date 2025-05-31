"""
Comprehensive logging configuration for LilyTheThird tool orchestrator and LLM components.
Provides structured logging with rotation, context tracking, and debugging capabilities.
"""

import logging
import logging.handlers
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional
from enum import Enum


class LogLevel(Enum):
    """Custom log levels for tool orchestrator specific events."""
    TOOL_DECISION = 25    # Between INFO(20) and WARNING(30)
    TOOL_RETRY = 23       # Between INFO(20) and TOOL_DECISION(25)
    ERROR_PATTERN = 35    # Between WARNING(30) and ERROR(40)


class ToolOrchestratorFormatter(logging.Formatter):
    """Custom formatter for tool orchestrator logs with structured output."""
    
    def format(self, record):
        # Create base log entry
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add extra context if available
        if hasattr(record, 'tool_name'):
            log_entry['tool_name'] = record.tool_name
        if hasattr(record, 'error_category'):
            log_entry['error_category'] = record.error_category
        if hasattr(record, 'retry_count'):
            log_entry['retry_count'] = record.retry_count
        if hasattr(record, 'arguments'):
            log_entry['arguments'] = record.arguments
        if hasattr(record, 'execution_time'):
            log_entry['execution_time'] = record.execution_time
        if hasattr(record, 'context_name'):
            log_entry['context_name'] = record.context_name
        if hasattr(record, 'decision_reason'):
            log_entry['decision_reason'] = record.decision_reason
        if hasattr(record, 'pattern_count'):
            log_entry['pattern_count'] = record.pattern_count
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry, ensure_ascii=False, separators=(',', ':'))


class LoggingManager:
    """Centralized logging manager for the tool orchestrator system."""
    
    def __init__(self, base_log_dir: str = "logs"):
        self.base_log_dir = Path(base_log_dir)
        self.base_log_dir.mkdir(exist_ok=True)
        self._loggers = {}
        self._setup_custom_levels()
        self._setup_loggers()
    
    def _setup_custom_levels(self):
        """Add custom log levels for tool orchestrator events."""
        for level in LogLevel:
            logging.addLevelName(level.value, level.name)
    
    def _setup_loggers(self):
        """Set up specialized loggers for different components."""
        
        # Tool orchestrator main logger
        self._setup_logger(
            'tool_orchestrator',
            'tool_orchestrator.log',
            level=logging.DEBUG,
            max_bytes=10*1024*1024,  # 10MB
            backup_count=5
        )
        
        # Tool execution logger
        self._setup_logger(
            'tool_execution',
            'tool_execution.log', 
            level=logging.INFO,
            max_bytes=5*1024*1024,   # 5MB
            backup_count=3
        )
        
        # Error pattern analysis logger
        self._setup_logger(
            'error_analysis',
            'error_analysis.log',
            level=logging.WARNING,
            max_bytes=5*1024*1024,   # 5MB
            backup_count=3
        )
        
        # LLM decision tracking logger
        self._setup_logger(
            'llm_decisions',
            'llm_decisions.log',
            level=logging.INFO,
            max_bytes=20*1024*1024,  # 20MB
            backup_count=5
        )
        
        # Retry logic logger
        self._setup_logger(
            'retry_logic',
            'retry_logic.log',
            level=logging.DEBUG,
            max_bytes=5*1024*1024,   # 5MB
            backup_count=3
        )
    
    def _setup_logger(self, name: str, filename: str, level: int, 
                     max_bytes: int, backup_count: int) -> logging.Logger:
        """Set up an individual logger with rotation."""
        logger = logging.getLogger(name)
        logger.setLevel(level)
        
        # Prevent duplicate handlers
        if logger.handlers:
            return logger
        
        # File handler with rotation
        log_file = self.base_log_dir / filename
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(ToolOrchestratorFormatter())
        
        # Console handler for important messages
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)  # Only warnings and above to console
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        # Prevent propagation to root logger
        logger.propagate = False
        
        self._loggers[name] = logger
        return logger
    
    def get_logger(self, name: str) -> logging.Logger:
        """Get a logger by name."""
        return self._loggers.get(name, logging.getLogger(name))
    
    def log_tool_decision(self, logger_name: str, tool_name: Optional[str], 
                         decision_reason: str, context_name: str, 
                         arguments: Optional[Dict] = None):
        """Log tool selection decisions."""
        logger = self.get_logger(logger_name)
        extra = {
            'tool_name': tool_name,
            'decision_reason': decision_reason,
            'context_name': context_name,
            'arguments': arguments
        }
        logger.log(LogLevel.TOOL_DECISION.value, 
                  f"Tool decision: {tool_name or 'null'} - {decision_reason}", 
                  extra=extra)
    
    def log_tool_execution(self, logger_name: str, tool_name: str, 
                          arguments: Dict, result: Any, execution_time: float,
                          success: bool = True):
        """Log tool execution results."""
        logger = self.get_logger(logger_name)
        extra = {
            'tool_name': tool_name,
            'arguments': arguments,
            'execution_time': execution_time
        }
        
        if success:
            logger.info(f"Tool '{tool_name}' executed successfully in {execution_time:.3f}s", 
                       extra=extra)
        else:
            logger.error(f"Tool '{tool_name}' execution failed: {result}", extra=extra)
    
    def log_retry_attempt(self, logger_name: str, tool_name: str, 
                         retry_count: int, error_category: str, 
                         error_message: str, arguments: Dict):
        """Log retry attempts with detailed context."""
        logger = self.get_logger(logger_name)
        extra = {
            'tool_name': tool_name,
            'retry_count': retry_count,
            'error_category': error_category,
            'arguments': arguments
        }
        logger.log(LogLevel.TOOL_RETRY.value,
                  f"Retry {retry_count} for '{tool_name}' - {error_category}: {error_message[:200]}",
                  extra=extra)
    
    def log_error_pattern(self, logger_name: str, tool_name: str,
                         error_category: str, pattern_count: int,
                         recent_errors: list):
        """Log detected error patterns."""
        logger = self.get_logger(logger_name)
        extra = {
            'tool_name': tool_name,
            'error_category': error_category,
            'pattern_count': pattern_count
        }
        logger.log(LogLevel.ERROR_PATTERN.value,
                  f"Repeated error pattern detected for '{tool_name}' - "
                  f"{error_category} (count: {pattern_count})",
                  extra=extra)
    
    def log_llm_response(self, logger_name: str, context_name: str,
                        response_type: str, content: str, 
                        message_count: int, reasoning: Optional[str] = None):
        """Log LLM responses and reasoning."""
        logger = self.get_logger(logger_name)
        extra = {
            'context_name': context_name,
            'response_type': response_type,
            'message_count': message_count,
            'reasoning': reasoning
        }
        logger.info(f"LLM response ({response_type}): {content[:100]}...", extra=extra)


# Global logging manager instance
_logging_manager = None

def get_logging_manager() -> LoggingManager:
    """Get the global logging manager instance."""
    global _logging_manager
    if _logging_manager is None:
        _logging_manager = LoggingManager()
    return _logging_manager

def setup_logging(base_log_dir: str = "logs") -> LoggingManager:
    """Initialize the logging system."""
    global _logging_manager
    _logging_manager = LoggingManager(base_log_dir)
    return _logging_manager