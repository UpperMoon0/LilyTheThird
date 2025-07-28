import json
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone

from dotenv import load_dotenv

from .history_manager import HistoryManager
from .llm_client import LLMClient
from .tool_executor import ToolExecutor
from .error_analyzer import ErrorAnalyzer, ErrorCategory
from .tool_orchestrator import ToolOrchestrator
from .logging_config import setup_logging
from .schemas import ToolCallDetails 
from memory.mongo_handler import MongoHandler
from tools.tools import find_tool

load_dotenv()

TOOL_SELECT_RETRY = 5
TOOL_USE_RETRY = 10
FINAL_MEMORY_RETRY = 10
TOOL_RETRY_DELAY_SECONDS = 2
MAX_SAME_ERROR_RETRIES = 3
ESCALATING_DELAY_FACTOR = 1.5
MAX_RETRY_DELAY = 10
MAX_ARG_SUMMARY_LEN = 150
MAX_RESULT_SUMMARY_LEN = 250

class BaseLLMOrchestrator(ABC):
    """
    Abstract base class for LLM orchestration, handling common logic like
    history management, tool execution, memory retrieval, and response generation.
    """
    def __init__(self,
                 provider: Optional[str] = None,
                 model_name: Optional[str] = None,
                 tool_use_enabled: bool = True,      
                 allowed_tools: Optional[List[str]] = None): 
        """
        Initializes common components. Subclasses might override provider/model defaults.
        """
        self.logging_manager = setup_logging()
        self.orchestrator_logger = self.logging_manager.get_logger('tool_orchestrator')
        
        self.orchestrator_logger.info("Initializing BaseLLMOrchestrator", extra={
            'provider': provider,
            'model_name': model_name,
            'tool_use_enabled': tool_use_enabled,
            'allowed_tools': allowed_tools
        })
        
        self.history_manager = HistoryManager()
        self.mongo_handler = MongoHandler()
        if not self.mongo_handler.is_connected():
            self.orchestrator_logger.warning("MongoDB connection failed. Memory tools will not function.")

        self.llm_client = LLMClient(provider=provider, model_name=model_name)
        self.tool_executor = ToolExecutor(mongo_handler=self.mongo_handler, llm_client=self.llm_client)
        
        self.tool_use_enabled = tool_use_enabled
        self.allowed_tools = allowed_tools
        self.tool_orchestrator = None

        if self.tool_use_enabled:
            print(f"[{self.__class__.__name__}] Tool use enabled. Initializing ToolOrchestrator.")
            self._initialize_tool_orchestrator()
        else:
            print(f"[{self.__class__.__name__}] Tool use disabled. ToolOrchestrator not initialized.")

        self.error_analyzer = ErrorAnalyzer()
        self.recent_errors = []

        self.provider = self.llm_client.provider
        self.model = self.llm_client.get_model_name()
        
        self.history_manager.set_llm_client(self.llm_client)
        
        print(f"BaseLLMOrchestrator initialized with Provider: {self.provider}, Model: {self.model}")

    def _initialize_tool_orchestrator(self, retry_count=0):
        """
        Initialize ToolOrchestrator with retry logic and proper error handling.
        """
        max_retries = 3
        try:
            self.tool_orchestrator = ToolOrchestrator(
                llm_client=self.llm_client,
                tool_executor=self.tool_executor,
                history_manager=self.history_manager, # Shared history manager
                allowed_tools=self.allowed_tools # Pass the list of allowed tool names
            )
            print(f"[{self.__class__.__name__}] ✅ ToolOrchestrator successfully initialized.")
            if self.allowed_tools:
                print(f"[{self.__class__.__name__}] ToolOrchestrator initialized with specific allowed tools: {self.allowed_tools}")
            else:
                print(f"[{self.__class__.__name__}] ToolOrchestrator initialized. All tools known to ToolExecutor will be considered (before internal exclusions).")
        except Exception as e:
            print(f"[{self.__class__.__name__}] ❌ ToolOrchestrator initialization FAILED (attempt {retry_count + 1}): {e}")
            self.tool_orchestrator = None
            
            if retry_count < max_retries:
                print(f"[{self.__class__.__name__}] Retrying ToolOrchestrator initialization in 1 second...")
                import time
                time.sleep(1)
                self._initialize_tool_orchestrator(retry_count + 1)
            else:
                print(f"[{self.__class__.__name__}] ❌ CRITICAL: ToolOrchestrator initialization FAILED after {max_retries + 1} attempts. Tool use will be disabled.")

    def reinitialize_tool_orchestrator(self):
        """
        Public method to reinitialize ToolOrchestrator, useful after settings changes.
        """
        if self.tool_use_enabled:
            print(f"[{self.__class__.__name__}] Reinitializing ToolOrchestrator...")
            self._initialize_tool_orchestrator()
        else:
            print(f"[{self.__class__.__name__}] Tool use disabled, clearing ToolOrchestrator.")
            self.tool_orchestrator = None

    @property
    @abstractmethod
    def context_name(self) -> str:
        """Returns a string identifier for the current context (e.g., 'chatbox', 'discord')."""
        pass

    @abstractmethod
    def _get_base_system_messages(self, **kwargs) -> List[Dict[str, str]]:
        """
        Subclasses must implement this to provide context-specific base system messages.
        kwargs can be used to pass context like user_id, user_name, etc.
        """
        pass

    @abstractmethod
    def _get_allowed_tools(self) -> Optional[List[str]]:
        """
        Subclasses must implement this to specify which tools are allowed.
        Return None to allow all tools.
        """
        pass

    @abstractmethod
    def _get_max_tool_calls(self) -> int:
        """
        Subclasses must implement this to specify the maximum number of tool calls per turn.
        """
        pass

    def _get_tools_to_exclude_from_main_loop(self) -> List[str]:
        """
        Returns a list of tool names to be excluded from the main tool interaction loop.
        Memory tools like fetch_memory and save_memory are typically excluded here
        as they are handled at specific stages (initial retrieval, final save).
        Subclasses can override this to exclude additional tools (e.g., update_memory for Discord).
        """
        return ['fetch_memory', 'save_memory']

    def _should_perform_final_memory_step(self) -> bool:
        """
        Determines if the final memory operation step (save/update memory) should be performed.
        Defaults to True. Subclasses (like DiscordLLM) can override to skip this step.
        """
        return True

    def _summarize_for_history(self, data: any, max_len: int) -> str:
        """Helper to summarize data for concise history logging."""
        if data is None:
            return "N/A"
        try:
            if isinstance(data, (dict, list)):
                s_data = json.dumps(data, separators=(',', ':'))
            else:
                s_data = str(data)
        except TypeError:
            s_data = str(data)
        if len(s_data) > max_len:
            return s_data[:max_len-3] + "..."
        return s_data

    def _prepare_user_message_for_history(self, user_message: str, **kwargs) -> str:
        """
        Optional hook for subclasses to modify the user message before adding to history.
        Default implementation returns the message as is.
        kwargs can receive context like user_name.
        """
        return user_message

    def _track_error_pattern(self, tool_name: str, error_message: str, arguments: dict, error_category: ErrorCategory) -> bool:
        """
        Track error patterns to detect repeated mistakes.
        Returns True if this is a repeated pattern that should receive enhanced guidance.
        """
        error_record = {
            "tool_name": tool_name,
            "error_category": error_category,
            "error_message": error_message,
            "arguments": arguments,
            "timestamp": datetime.now(timezone.utc)
        }
        
        self.recent_errors.append(error_record)
        if len(self.recent_errors) > 10:
            self.recent_errors.pop(0)
        
        same_pattern_count = sum(1 for error in self.recent_errors
                               if error["tool_name"] == tool_name and
                                  error["error_category"] == error_category)
        
        return same_pattern_count >= 3

    def _generate_enhanced_retry_context(self, tool_name: str, error_message: str, arguments: dict, 
                                       retry_count: int, retrieved_facts: Optional[str] = None) -> str:
        """
        Generate enhanced retry context using error analysis and pattern detection.
        """
        error_category, specific_guidance = self.error_analyzer.analyze_error(error_message, tool_name, arguments)
        
        is_repeated_pattern = self._track_error_pattern(tool_name, error_message, arguments, error_category)
        
        base_context = (
            f"RETRY CONTEXT (Attempt {retry_count}): Tool '{tool_name}' failed. "
            f"Error Category: {error_category.value.upper()}\n\n"
            f"SPECIFIC GUIDANCE: {specific_guidance}\n\n"
        )
        
        if is_repeated_pattern:
            base_context += (
                "⚠️ REPEATED MISTAKE DETECTED: You have made this same type of error multiple times. "
                "Please carefully review the guidance above and ensure you understand the requirements "
                "before proceeding. Take extra care with the argument format and values.\n\n"
            )
        
        if error_category == ErrorCategory.MEMORY_ID_ERROR and retrieved_facts:
            base_context += (
                "MEMORY ID REFERENCE: Here are the available memory facts you can update:\n"
                f"{retrieved_facts}\n\n"
                "IMPORTANT: Only use memory_id values that appear in the facts above.\n\n"
            )
        
        if retry_count >= 3:
            base_context += (
                "PROGRESSIVE GUIDANCE: This is your third or later attempt. Consider:\n"
                "1. Double-check the tool's parameter requirements and data types\n"
                "2. Verify that all required arguments are provided\n"
                "3. Ensure argument values match the expected format exactly\n"
                "4. Review any error-specific guidance provided above\n\n"
            )
        
        if retry_count >= 2 and tool_name in ["update_memory", "save_memory"]:
            base_context += self._get_tool_examples(tool_name)
        
        return base_context
    
    def _get_tool_examples(self, tool_name: str) -> str:
        """Provide concrete examples for complex tools that frequently fail."""
        examples = {
            "update_memory": (
                "EXAMPLE: For update_memory, use:\n"
                '{"memory_id": "507f1f77bcf86cd799439011", "new_content": "Updated information"}\n'
                "Make sure the memory_id is EXACTLY as shown in the retrieved facts.\n\n"
            ),
            "save_memory": (
                "EXAMPLE: For save_memory, use:\n"
                '{"content": "New information to remember"}\n'
                "Content should be descriptive and self-contained.\n\n"
            ),
            "write_file": (
                "EXAMPLE: For write_file, use:\n"
                '{"file_path": "/full/path/to/file.txt", "content": "File content here"}\n'
                "Ensure the path is absolute and directory exists.\n\n"
            )
        }
        return examples.get(tool_name, "")
    
    def _should_abort_retry_sequence(self, tool_name: str, error_message: str, retry_count: int) -> bool:
        """
        Determine if retry sequence should be aborted due to futile attempts.
        """
        exact_same_errors = sum(1 for error in self.recent_errors[-5:]
                                  if error.get("tool_name") == tool_name and
                                     error.get("error_message") == error_message)
        
        if exact_same_errors >= MAX_SAME_ERROR_RETRIES:
            return True
        
        error_category, _ = self.error_analyzer.analyze_error(error_message, tool_name, {})
        non_retryable_on_high_count = [
            ErrorCategory.INVALID_ARGUMENT,
            ErrorCategory.MISSING_ARGUMENT,
            ErrorCategory.RESOURCE_NOT_FOUND,
            ErrorCategory.PERMISSION_DENIED
        ]
        
        if retry_count >= 4 and error_category in non_retryable_on_high_count:
            return True
        
        return False

    async def _summarize_tool_result_for_final_response(self, tool_name: str, tool_result: str) -> str:
        """
        Summarizes a tool's result using an LLM call for a concise, human-readable statement.
        """
        if not tool_result:
            return "The tool returned no specific result."

        if len(tool_result) < 100 and "\n" not in tool_result:
            return f"The {tool_name} tool provided the following: {tool_result}"

        prompt_template = (
            "The following is the raw output from a tool named '{tool_name}':\n"
            "--- TOOL OUTPUT START ---\n"
            "{tool_output}\n"
            "--- TOOL OUTPUT END ---\n"
            "Briefly summarize this information in a natural, concise, human-readable sentence or two. "
            "This summary will be used to inform a user about what was found or done. "
            "Focus on the key outcome or information. Do not say 'The tool output shows...' or 'The summary is...'. "
            "Just state the fact or action directly. "
            "For example, if the tool output was a list of files, a good summary might be 'Several files were found in the directory.' "
            "Or if it was a weather API result, 'The weather forecast is sunny with a high of 25°C.' "
            "If the tool performed an action like saving a file, 'The file was saved successfully.'"
        )
        
        summarization_prompt_content = prompt_template.format(tool_name=tool_name, tool_output=tool_result)
        
        messages_for_summarization = [
            {'role': 'system', 'content': "You are an expert at summarizing technical tool outputs into natural language facts or action statements."},
            {'role': 'user', 'content': summarization_prompt_content}
        ]
        
        try:
            summary = await self.llm_client.generate_final_response(
                messages_for_summarization,
                personality_prompt="You are a summarizer."
            )

            if summary and not summary.startswith("Error:"):
                return summary.strip()
            else:
                self.orchestrator_logger.error(f"LLM summarization failed or returned error for {tool_name}: {summary}")
                return f"Tool {tool_name} was used. (Result summarization failed, raw result: {self._summarize_for_history(tool_result, 100)})"
        except Exception as e:
            self.orchestrator_logger.error(f"Exception during LLM summarization for {tool_name}: {e}", exc_info=True)
            return f"Tool {tool_name} was used. (Exception during result summarization, raw result: {self._summarize_for_history(tool_result, 100)})"

    async def _retrieve_and_add_memory_context(self, query_text: str) -> Optional[str]:
        """
        Retrieves relevant facts from memory based on query_text and returns
        a formatted string containing the facts and a prioritization instruction,
        or None if no relevant facts are found or an error occurs.
        """
        if not self.mongo_handler.is_connected() or not self.mongo_handler.embedding_model:
            print(f"[{self.__class__.__name__}] Memory retrieval skipped: MongoDB not connected or embedding model not loaded.")
            return None

        try:
            relevant_facts = self.mongo_handler.retrieve_memories_by_similarity(query_text, limit=3)
            if relevant_facts:
                print(f"[{self.__class__.__name__}] Retrieved {len(relevant_facts)} relevant facts from memory:")
                for i, fact in enumerate(relevant_facts):
                    print(f"  Fact {i+1}: {fact}")
                facts_context = (
                    "CRITICAL INSTRUCTION: The following information was retrieved from memory and is highly relevant to the user's query. "
                    "You MUST prioritize using these facts in your response if they directly answer the query. "
                    "Do NOT rely solely on your general knowledge if these facts provide the specific answer.\n\n"
                    "Relevant information from memory:\n" +
                    "\n".join([f"- {fact}" for fact in relevant_facts])
                )
                print(f"[{self.__class__.__name__}] Prepared facts context WITH integrated prioritization instruction.")
                return facts_context
            else:
                print(f"[{self.__class__.__name__}] No relevant facts found in memory for query: '{query_text[:50]}...'")
                return None
        except Exception as e:
            print(f"Error retrieving memories by similarity: {e}")
            return None

    async def _process_message(self, user_message: str, **kwargs) -> Tuple[str, List[Dict]]:
        """
        Core logic for processing a user message.
        """
        base_system_messages = self._get_base_system_messages(**kwargs)

        prepared_user_message = self._prepare_user_message_for_history(user_message, **kwargs)
        await self.history_manager.add_message('user', prepared_user_message)

        successful_tool_calls = []
        final_message = ""

        if self.tool_use_enabled and self.tool_orchestrator is not None:
            retrieved_facts_context_string = await self._retrieve_and_add_memory_context(user_message)
            
            max_tool_calls = self._get_max_tool_calls()
            text_response_from_cycle, executed_tool_calls_details = await self.tool_orchestrator.execute_tool_cycle(
                base_system_messages=base_system_messages,
                max_tool_calls=max_tool_calls,
                context_name=self.context_name,
                retrieved_facts_context_string=retrieved_facts_context_string
            )
            
            if executed_tool_calls_details:
                successful_tool_calls.extend(executed_tool_calls_details)

            if text_response_from_cycle:
                final_message = text_response_from_cycle
            else:
                if not executed_tool_calls_details and self._should_perform_final_memory_step():
                    await self._execute_final_memory_operation(base_system_messages, retrieved_facts_context_string, successful_tool_calls)
                
                final_message = await self._generate_optimized_final_response(base_system_messages, successful_tool_calls)
                
                if final_message and not final_message.startswith("Error:"):
                    await self.history_manager.add_message('assistant', final_message)
        else:
            final_message = await self._generate_optimized_final_response(base_system_messages, successful_tool_calls)
            if final_message and not final_message.startswith("Error:"):
                await self.history_manager.add_message('assistant', final_message)
        
        return final_message, successful_tool_calls

    async def _execute_final_memory_operation(self, base_system_messages: List[Dict],
                                            retrieved_facts_context_string: Optional[str],
                                            successful_tool_calls: List[Dict]):
        """Streamlined final memory operation without redundant LLM calls."""
        current_history = self.history_manager.get_history()
        messages_for_save = base_system_messages + current_history

        if retrieved_facts_context_string:
            messages_for_save.append({'role': 'system', 'content': retrieved_facts_context_string})

        save_or_update_decision = await self.llm_client.get_next_action(
            messages_for_save,
            allowed_tools=self.allowed_tools,
            context_type=self.context_name,
            force_tool_options=['save_memory', 'update_memory']
        )

        chosen_tool_name = save_or_update_decision.get("tool_name") if save_or_update_decision else None
        
        if chosen_tool_name in ['save_memory', 'update_memory']:
            tool_definition = find_tool(chosen_tool_name)
            if tool_definition:
                argument_decision = await self.llm_client.get_tool_arguments(tool_definition, messages_for_save)
                if argument_decision and argument_decision.get("action_type") == "tool_arguments":
                    arguments = argument_decision.get("arguments", {})
                    tool_result = await self.tool_executor.execute(chosen_tool_name, arguments)
                    
                    if not (isinstance(tool_result, str) and tool_result.startswith("Error:")):
                        successful_tool_call_details_obj = ToolCallDetails(
                            tool_name=chosen_tool_name,
                            arguments=arguments,
                            result=str(tool_result),
                            execution_time=0.0,
                            tool_call_id=None
                        )
                        successful_tool_calls.append(successful_tool_call_details_obj)

    async def _generate_optimized_final_response(self, base_system_messages: List[Dict],
                                               successful_tool_calls: List[Dict]) -> str:
        """
        Generates the final response using a structured user message format, including a simplified conversation history.
        """
        final_history = self.history_manager.get_history()
        
        personality_prompt = base_system_messages[0]['content'] if base_system_messages else "You are a helpful assistant."

        last_user_message = ""
        history_for_formatting = list(final_history)
        if history_for_formatting and history_for_formatting[-1].get('role') == 'user':
            last_user_message = history_for_formatting.pop().get('content', '')

        history_str = ""
        for msg in history_for_formatting:
            role = msg.get('role')
            content = msg.get('content', '')
            if role == 'user':
                history_str += f"User: {content}\n"
            elif role == 'assistant':
                if content and not msg.get('tool_calls'):
                    history_str += f"Assistant: {content}\n"
        
        history_tag = f"<conversation_history>\n{history_str.strip()}\n</conversation_history>" if history_str.strip() else ""

        try:
            current_time_str = datetime.now().astimezone().isoformat()
        except Exception as e:
            self.orchestrator_logger.error(f"Could not get current time: {e}")
            current_time_str = "Time not available"

        new_prompt_content = (
            f"<user_message>{last_user_message}</user_message>\n"
            f"<personality_instruction>{personality_prompt}</personality_instruction>\n"
            f"<time>{current_time_str}</time>\n"
            f"{history_tag}"
        ).strip()

        messages_for_llm = [{'role': 'user', 'content': new_prompt_content}]

        final_message = await self.llm_client.generate_final_response(
            messages_for_llm,
            personality_prompt=""
        )

        if final_message is None or final_message.startswith("Error:"):
            return final_message if final_message else "Sorry, I encountered an error generating the final response."
        
        return final_message

    def _filter_history_optimally(self, final_history: List[Dict], successful_tool_calls: List[Dict]) -> List[Dict]:
        """
        Optimally filter history to remove tool scaffolding while preserving essential context.
        Dramatically reduces context size.
        """
        filtered_history = []
        
        tool_summaries = {}
        for tool_call_detail in successful_tool_calls:
            if hasattr(tool_call_detail, 'tool_call_id') and tool_call_detail.tool_call_id:
                tool_summaries[tool_call_detail.tool_call_id] = f"Used {tool_call_detail.tool_name} successfully"
        
        for msg in final_history:
            msg_role = msg.get('role', '')
            msg_content = msg.get('content', '')
            
            if msg_role == 'user':
                filtered_history.append(msg)
                continue
            
            if msg_role == 'assistant' and 'tool_calls' not in msg:
                filtered_history.append(msg)
                continue
                
            if (msg_role == 'system' and
                (msg_content.startswith("System: Calling tool") or
                 msg_content.startswith("System: Tool ") or
                 msg_content.startswith("RETRY CONTEXT") or
                 msg_content.startswith("ENHANCED RETRY CONTEXT") or
                 "tool" in msg_content.lower())):
                continue
                
            if msg_role == 'tool':
                continue
                
            if msg_role == 'system' and not any(skip_word in msg_content.lower()
                                               for skip_word in ['tool', 'retry', 'calling', 'schema']):
                filtered_history.append(msg)
        
        return filtered_history

    def close(self):
        """Closes resources, like the MongoDB connection."""
        if hasattr(self, 'mongo_handler') and self.mongo_handler:
            self.mongo_handler.close_connection()
            print(f"[{self.__class__.__name__}] MongoDB connection closed via explicit close().")
