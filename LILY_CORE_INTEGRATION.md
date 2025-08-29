# Lily-Core Integration Guide

This document explains how LilyTheThird has been refactored to use Lily-Core for LLM orchestration instead of its own complex orchestration system.

## Overview

LilyTheThird has been updated to leverage Lily-Core, a clean architecture LLM service that provides:
- HTTP API for chat functionality
- Advanced agent loop system for multi-step reasoning
- Web search integration via Web-Scout
- Conversation memory management
- Tool orchestration

## Key Changes

### Before
- Complex orchestration system with `BaseLLMOrchestrator`, `ToolOrchestrator`, `LLMClient`
- Individual LLM API key management
- Custom error handling and retry logic
- Complex personality and context management

### After
- Simple HTTP client to Lily-Core API
- Centralized LLM management (providers, API keys, models)
- Streamlined error handling
- Consistent tool integration via Lily-Core

## Configuration

### Required Environment Variables

Add these to your `.env` file:

```bash
# Lily-Core service URL
LILY_CORE_URL=http://localhost:8000

# Optional: Enable agent loop system (default: false)
CHATBOX_USE_AGENT_LOOP=false
DISCORD_USE_AGENT_LOOP=false

# Personality settings (unchanged)
PERSONALITY_TO_MASTER="You are a helpful AI assistant."
PERSONALITY_TO_STRANGER_1="You are a polite AI. I'm "
PERSONALITY_TO_STRANGER_2=", you will talk to me politely."
```

### Lily-Core Service

Make sure Lily-Core is running and accessible. You can:

1. **Run Lily-Core locally:**
   ```bash
   cd ../Lily-Core
   docker-compose up --build
   ```

2. **Or deploy Lily-Core to a server** and update `LILY_CORE_URL` accordingly.

3. **Health check:**
   ```bash
   curl http://localhost:8000/health
   ```

## New Components

### LilyCoreClient
- `LilyTheThird/llm/lily_core_client.py`
- HTTP client for Lily-Core API
- Handles authentication, requests, and responses
- Compatible interface for existing code

### LilyCoreChatOrchestrator
- Wrapper around LilyCoreClient
- Maintains compatibility with existing orchestrator interfaces
- Handles personality injection

### Updated Orchestrators
- `ChatBoxLLMOrchestrator` - Now uses Lily-Core
- `DiscordLLMOrchestrator` - Now uses Lily-Core
- Much simpler and more reliable

## API Endpoints Used

Lily-Core provides several endpoints:

- `POST /chat` - Send messages with optional agent loop
- `GET /conversation/{user_id}` - Get conversation history
- `DELETE /conversation/{user_id}` - Clear conversation
- `GET /tools` - List available tools
- `GET /health` - Service health check

## Agent Loop System

LilyTheThird can now leverage Lily-Core's advanced agent loop system:

```python
# Enable in environment variables
CHATBOX_USE_AGENT_LOOP=true
DISCORD_USE_AGENT_LOOP=true

# Or programmatically
orchestrator = LilyCoreChatOrchestrator(use_agent_loop=True)
```

The agent loop provides:
- Multi-step reasoning and planning
- Iterative tool execution
- Context updates between steps
- Sophisticated problem solving

## Testing Integration

Run the integration test:

```bash
python LilyTheThird/test_lily_core_integration.py
```

This will verify:
- Lily-Core connectivity
- ChatBox orchestrator functionality
- Discord orchestrator functionality

## Migration Notes

### Removed Components
- Complex orchestration logic (`base_llm_orchestrator.py`)
- Individual LLM clients (`llm_client.py`)
- Custom tool orchestration (`tool_orchestrator.py`)
- Error analysis system (`error_analyzer.py`)
- History management (`history_manager.py`)

### Compatibility Maintained
- `ChatBoxLLMOrchestrator.get_response()` interface
- `DiscordLLMOrchestrator.get_response()` interface
- Return value formats
- Error handling patterns

## Benefits

1. **Simplified Architecture**: Removed ~1000+ lines of complex orchestration code
2. **Centralized Management**: LLM configuration and API keys managed in Lily-Core
3. **Better Tool Integration**: Leverages Lily-Core's improved tool system
4. **Advanced Features**: Access to agent loop system and improved web search
5. **Easier Maintenance**: Single point of LLM management
6. **Better Error Handling**: Lily-Core's robust error management
7. **Conversation Memory**: Persistent conversation history across sessions

## Troubleshooting

### Connection Issues
```bash
# Check if Lily-Core is running
curl http://localhost:8000/health

# Test connectivity
python LilyTheThird/test_lily_core_integration.py
```

### Common Errors

1. **"Cannot connect to Lily-Core"**
   - Ensure Lily-Core service is running
   - Check `LILY_CORE_URL` in `.env`
   - Verify network connectivity

2. **"Tool execution failed"**
   - Tools are now handled by Lily-Core
   - Check Lily-Core logs for tool issues
   - Ensure Web-Scout is configured and running

3. **"Personality not working"**
   - Personalities are injected as metadata
   - Check Lily-Core conversation history
   - Verify personality environment variables

## Future Enhancements

This refactoring enables:
- Distributed deployment (Lily-Core on separate infrastructure)
- Advanced agent loop capabilities
- Better scaling with multiple LilyTheThird instances
- Centralized monitoring and logging
- Easy A/B testing with different LLM configurations

## Rollback Plan

If needed, the old orchestration system is preserved in git history:
```bash
git log --oneline --grep="refactor"
```

To rollback to old system (not recommended):
1. Revert this commit
2. Restore deprecated files
3. Reconfigure API keys and LLM settings