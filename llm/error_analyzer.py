"""
Error analysis module for LLM orchestration.
Categorizes errors and provides targeted guidance for LLM retries.
"""

import re
from typing import Dict, Optional, Tuple
from enum import Enum


class ErrorCategory(Enum):
    INVALID_ARGUMENT = "invalid_argument"
    MISSING_ARGUMENT = "missing_argument"
    TOOL_EXECUTION = "tool_execution"
    PERMISSION_DENIED = "permission_denied"
    RESOURCE_NOT_FOUND = "resource_not_found"
    VALIDATION_ERROR = "validation_error"
    MEMORY_ID_ERROR = "memory_id_error"
    NETWORK_ERROR = "network_error"
    RATE_LIMIT = "rate_limit"
    UNKNOWN = "unknown"


class ErrorAnalyzer:
    """Analyzes tool execution errors and provides targeted guidance for LLM retries."""
    
    def __init__(self):
        self.error_patterns = {
            ErrorCategory.INVALID_ARGUMENT: [
                r"invalid argument",
                r"invalid value",
                r"argument.*invalid",
                r"validation failed",
                r"invalid.*parameter"
            ],
            ErrorCategory.MISSING_ARGUMENT: [
                r"missing.*argument",
                r"required.*argument",
                r"argument.*required",
                r"missing.*parameter"
            ],
            ErrorCategory.MEMORY_ID_ERROR: [
                r"memory_id.*not found",
                r"invalid.*memory_id",
                r"Memory replacement failed.*memory_id",
                r"ObjectId.*not found"
            ],
            ErrorCategory.PERMISSION_DENIED: [
                r"permission denied",
                r"access denied",
                r"unauthorized",
                r"forbidden"
            ],
            ErrorCategory.RESOURCE_NOT_FOUND: [
                r"file not found",
                r"path.*not found",
                r"resource.*not found",
                r"does not exist"
            ],
            ErrorCategory.NETWORK_ERROR: [
                r"network error",
                r"connection failed",
                r"timeout",
                r"unreachable"
            ],
            ErrorCategory.RATE_LIMIT: [
                r"rate limit",
                r"too many requests",
                r"quota exceeded"
            ]
        }
    
    def analyze_error(self, error_message: str, tool_name: str, arguments: dict) -> Tuple[ErrorCategory, str]:
        """
        Analyze an error message and return category with specific guidance.
        
        Args:
            error_message: The error message from tool execution
            tool_name: Name of the tool that failed
            arguments: Arguments that were used
            
        Returns:
            Tuple of (ErrorCategory, specific_guidance_message)
        """
        error_lower = error_message.lower()
        
        # Check each category
        for category, patterns in self.error_patterns.items():
            for pattern in patterns:
                if re.search(pattern, error_lower):
                    guidance = self._get_specific_guidance(category, error_message, tool_name, arguments)
                    return category, guidance
        
        # Default to unknown
        guidance = self._get_specific_guidance(ErrorCategory.UNKNOWN, error_message, tool_name, arguments)
        return ErrorCategory.UNKNOWN, guidance
    
    def _get_specific_guidance(self, category: ErrorCategory, error_message: str, tool_name: str, arguments: dict) -> str:
        """Generate specific guidance based on error category."""
        
        base_guidance = f"Tool '{tool_name}' failed. "
        
        if category == ErrorCategory.INVALID_ARGUMENT:
            invalid_args = self._extract_invalid_arguments(error_message, arguments)
            if invalid_args:
                return (base_guidance + 
                       f"Invalid argument(s) detected: {', '.join(invalid_args)}. "
                       f"Check the tool's schema and ensure values match the expected format and constraints. "
                       f"Previous arguments: {arguments}")
            else:
                return (base_guidance + 
                       "Invalid argument format detected. Review the tool's parameter requirements and "
                       "ensure all arguments match the expected data types and constraints.")
        
        elif category == ErrorCategory.MISSING_ARGUMENT:
            return (base_guidance + 
                   "Required argument(s) missing. Check the tool definition for all required parameters. "
                   f"You provided: {list(arguments.keys()) if arguments else 'no arguments'}")
        
        elif category == ErrorCategory.MEMORY_ID_ERROR:
            return (base_guidance + 
                   "Invalid memory_id provided. The ID doesn't exist in the database. "
                   "If updating memory, use a valid ID from previously retrieved facts. "
                   "If saving new information, use 'save_memory' instead of 'update_memory'.")
        
        elif category == ErrorCategory.PERMISSION_DENIED:
            return (base_guidance + 
                   "Permission denied. Check if the file/resource exists and you have access rights. "
                   "Consider using a different path or checking file permissions.")
        
        elif category == ErrorCategory.RESOURCE_NOT_FOUND:
            return (base_guidance + 
                   "Resource not found. Verify the path/filename is correct and the resource exists. "
                   f"You tried to access: {arguments.get('file_path', arguments.get('path', 'unknown resource'))}")
        
        elif category == ErrorCategory.NETWORK_ERROR:
            return (base_guidance + 
                   "Network error occurred. This may be temporary. If retrying, ensure the URL is correct. "
                   f"Target: {arguments.get('url', arguments.get('query', 'unknown target'))}")
        
        elif category == ErrorCategory.RATE_LIMIT:
            return (base_guidance + 
                   "Rate limit exceeded. This is a temporary issue with the external service. "
                   "Consider waiting or using alternative approaches.")
        
        else:  # UNKNOWN or TOOL_EXECUTION
            return (base_guidance + 
                   f"Execution error: {error_message}. "
                   "Review the error message carefully and adjust your approach accordingly. "
                   f"Arguments used: {arguments}")
    
    def _extract_invalid_arguments(self, error_message: str, arguments: dict) -> list:
        """Try to extract which specific arguments were invalid from the error message."""
        invalid_args = []
        
        if not arguments:
            return invalid_args
        
        error_lower = error_message.lower()
        
        # Look for argument names mentioned in the error
        for arg_name in arguments.keys():
            if arg_name.lower() in error_lower:
                invalid_args.append(arg_name)
        
        return invalid_args

    def should_retry_with_same_arguments(self, category: ErrorCategory) -> bool:
        """Determine if retrying with the same arguments might succeed."""
        non_retryable = {
            ErrorCategory.INVALID_ARGUMENT,
            ErrorCategory.MISSING_ARGUMENT, 
            ErrorCategory.MEMORY_ID_ERROR,
            ErrorCategory.RESOURCE_NOT_FOUND,
            ErrorCategory.PERMISSION_DENIED
        }
        return category not in non_retryable
    
    def get_retry_strategy(self, category: ErrorCategory, retry_count: int) -> Dict[str, any]:
        """Get recommended retry strategy based on error category and attempt count."""
        strategy = {
            "should_retry": True,
            "delay_multiplier": 1.0,
            "regenerate_args": True,
            "specific_instructions": []
        }
        
        if category == ErrorCategory.RATE_LIMIT:
            strategy["delay_multiplier"] = 2.0 * retry_count  # Exponential backoff
            strategy["regenerate_args"] = False  # Same args, just wait
            strategy["specific_instructions"].append("Rate limited - waiting longer before retry")
        
        elif category == ErrorCategory.NETWORK_ERROR:
            strategy["delay_multiplier"] = 1.5
            strategy["regenerate_args"] = False if retry_count < 2 else True
        
        elif category in [ErrorCategory.INVALID_ARGUMENT, ErrorCategory.MISSING_ARGUMENT]:
            strategy["specific_instructions"].append("Must carefully review and fix argument structure")
            if retry_count >= 3:
                strategy["should_retry"] = False  # Probably won't succeed
        
        elif category == ErrorCategory.MEMORY_ID_ERROR:
            strategy["specific_instructions"].append("Must use valid memory_id from retrieved facts")
            if retry_count >= 2:
                strategy["should_retry"] = False  # ID issue unlikely to resolve
        
        return strategy
