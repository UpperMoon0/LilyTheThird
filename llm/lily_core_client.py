#!/usr/bin/env python3
"""
Lily-Core Client for LilyTheThird

Client for communicating with Lily-Core service via HTTP API.
Provides a simple interface to Lily-Core's chat and conversation management capabilities.
"""

import os
import asyncio
import aiohttp
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


class LilyCoreClient:
    """
    HTTP client for Lily-Core API.
    Handles chat requests, conversation management, and tool integration.
    """

    def __init__(self,
                 base_url: Optional[str] = None,
                 timeout: int = 30,
                 use_agent_loop: bool = False):
        """
        Initialize Lily-Core client.

        Args:
            base_url: Base URL for Lily-Core service. Defaults to env var or localhost.
            timeout: Request timeout in seconds. Default 30.
            use_agent_loop: Whether to use advanced agent loop system. Default False.
        """
        self.base_url = base_url or os.getenv('LILY_CORE_URL', 'http://localhost:8000')
        self.base_url = self.base_url.rstrip('/')
        self.timeout = timeout
        self.use_agent_loop = use_agent_loop
        self.session: Optional[aiohttp.ClientSession] = None

        print(f"LilyCoreClient initialized. Base URL: {self.base_url}")
        print(f"Agent loop enabled: {self.use_agent_loop}")

    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.cleanup()

    async def initialize(self):
        """Initialize HTTP session"""
        if self.session is None:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )

    async def cleanup(self):
        """Clean up HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None

    async def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        Make HTTP request to Lily-Core.

        Args:
            method: HTTP method (GET, POST, DELETE)
            endpoint: API endpoint path (without leading slash)
            **kwargs: Additional arguments for request

        Returns:
            Response JSON as dictionary

        Raises:
            Exception: On request failure
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        # Use context manager to ensure session cleanup
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout)
        ) as session:
            try:
                async with session.request(method, url, **kwargs) as response:
                    if response.status >= 400:
                        error_text = await response.text()
                        raise Exception(f"Lily-Core API error {response.status}: {error_text}")

                    return await response.json()

            except aiohttp.ClientError as e:
                raise Exception(f"Failed to connect to Lily-Core at {url}: {str(e)}")
            except Exception as e:
                raise Exception(f"Lily-Core request failed: {str(e)}")

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on Lily-Core service.

        Returns:
            Health status information
        """
        return await self._request('GET', 'health')

    async def chat(self,
                   message: str,
                   user_id: str,
                   use_agent_loop: Optional[bool] = None,
                   metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Send chat message to Lily-Core.

        Args:
            message: User message
            user_id: Unique user identifier
            use_agent_loop: Override default agent loop setting
            metadata: Additional metadata for the request

        Returns:
            Chat response with response text, user_id, timestamp, and metadata
        """
        request_data = {
            'message': message,
            'user_id': user_id
        }

        if metadata:
            request_data['metadata'] = metadata

        # Use agent loop setting
        agent_loop = use_agent_loop if use_agent_loop is not None else self.use_agent_loop
        params = {'use_agent_loop': 'true'} if agent_loop else {}

        # Make the request
        response = await self._request(
            'POST',
            'chat',
            json=request_data,
            params=params
        )

        # Add tool_used flag for compatibility
        if response.get('tool_used') is None:
            response['tool_used'] = 'web_search' if response.get('metadata', {}).get('agent_loop', {}).get('used') else None

        return response

    async def get_conversation_history(self, user_id: str, limit: Optional[int] = None) -> Dict[str, Any]:
        """
        Get conversation history for a user.

        Args:
            user_id: User identifier
            limit: Maximum number of messages to return

        Returns:
            Conversation data with messages and metadata
        """
        params = {}
        if limit:
            params['limit'] = limit

        return await self._request('GET', f'conversation/{user_id}', params=params)

    async def clear_conversation(self, user_id: str) -> Dict[str, str]:
        """
        Clear conversation history for a user.

        Args:
            user_id: User identifier

        Returns:
            Success confirmation
        """
        response = await self._request('DELETE', f'conversation/{user_id}')
        return response

    async def get_available_tools(self) -> Dict[str, Any]:
        """
        Get information about available tools.

        Returns:
            Available tools information
        """
        return await self._request('GET', 'tools')

    async def get_conversation_summary(self, user_id: str) -> Dict[str, Any]:
        """
        Get summary information about a user's conversation.

        Args:
            user_id: User identifier

        Returns:
            Conversation summary
        """
        return await self._request('GET', f'conversation-summary/{user_id}')

    async def get_agent_loop_status(self) -> Dict[str, Any]:
        """
        Get status of the agent loop system.

        Returns:
            Agent loop system status
        """
        return await self._request('GET', 'agent-loop/status')

    def set_agent_loop_enabled(self, enabled: bool):
        """Enable or disable agent loop for subsequent requests."""
        self.use_agent_loop = enabled


class LilyCoreChatOrchestrator:
    """
    Simple orchestrator that wraps LilyCoreClient for compatibility with LilyTheThird.
    """

    def __init__(self,
                 base_url: Optional[str] = None,
                 use_agent_loop: bool = False,
                 personality: Optional[str] = None):
        """
        Initialize the Lily-Core chat orchestrator.

        Args:
            base_url: Lily-Core service URL
            use_agent_loop: Enable advanced agent loop system
            personality: Personality/system prompt (will be handled by Lily-Core)
        """
        self.client = LilyCoreClient(base_url=base_url, use_agent_loop=use_agent_loop)
        self.personality = personality or "You are a helpful AI assistant."
        self.initialized = False

    async def initialize(self):
        """Initialize the orchestrator and check Lily-Core health."""
        if not self.initialized:
            await self.client.initialize()

            # Check health
            try:
                health = await self.client.health_check()
                print(f"Lily-Core health: {health.get('status', 'unknown')}")
            except Exception as e:
                print(f"Warning: Could not connect to Lily-Core: {e}")

            self.initialized = True

    async def close(self):
        """Close the orchestrator and cleanup resources."""
        if self.initialized:
            await self.client.cleanup()
            self.initialized = False

    async def get_response(self, user_message: str, user_id: str = "default_user") -> Tuple[str, List[Dict]]:
        """
        Get response from Lily-Core.

        Args:
            user_message: User input message
            user_id: User identifier

        Returns:
            Tuple of (response_text, tool_calls_list)
        """
        if not self.initialized:
            await self.initialize()

        try:
            response = await self.client.chat(
                message=user_message,
                user_id=user_id,
                metadata={
                    'personality': self.personality,
                    'timestamp': datetime.now().isoformat()
                }
            )

            # Extract response text
            response_text = response.get('response', '')

            # Extract tool information
            tool_calls = []
            if response.get('tool_used'):
                tool_info = {
                    'name': response.get('tool_used'),
                    'success': True,
                    'response': response_text,
                    'metadata': response.get('metadata', {})
                }
                tool_calls.append(tool_info)

            return response_text, tool_calls

        except Exception as e:
            error_msg = f"Error communicating with Lily-Core: {str(e)}"
            print(error_msg)
            return error_msg, []


# Global client instance
_lily_core_client = None


def get_lily_core_client() -> LilyCoreClient:
    """Get global Lily-Core client instance."""
    global _lily_core_client
    if _lily_core_client is None:
        _lily_core_client = LilyCoreClient()
    return _lily_core_client


async def test_lily_core_connection():
    """Test connection to Lily-Core service."""
    async with LilyCoreClient() as client:
        try:
            health = await client.health_check()
            print(f"✅ Lily-Core connection successful: {health}")
            return True
        except Exception as e:
            print(f"❌ Lily-Core connection failed: {e}")
            return False


if __name__ == "__main__":
    # Test when run directly
    asyncio.run(test_lily_core_connection())