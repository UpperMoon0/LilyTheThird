#!/usr/bin/env python3
"""
Test Lily-Core integration for LilyTheThird

This script tests that LilyTheThird can successfully communicate with Lily-Core.
"""

import asyncio
import sys
import os

# Add the parent directory to path so we can import from LLM module
sys.path.insert(0, os.path.dirname(__file__))

from llm.lily_core_client import LilyCoreChatOrchestrator
# TODO: Replace with Lily Core equivalents
# from llm.chatbox_llm_orchestrator import ChatBoxLLMOrchestrator
# from llm.discord_llm_orchestrator import DiscordLLMOrchestrator


async def test_lily_core_direct():
    """Test Lily-Core client directly."""
    print("🔍 Testing Lily-Core client directly...")

    try:
        orchestrator = LilyCoreChatOrchestrator(
            base_url="http://localhost:8000",
            use_agent_loop=False,
            personality="You are a helpful test assistant."
        )

        await orchestrator.initialize()

        # Test basic chat
        response, tools = await orchestrator.get_response(
            "Hello! Can you tell me what 2+2 equals?",
            user_id="test_user"
        )

        print("✅ Direct client test successful!"        print(f"   Response: {response[:100]}...")
        print(f"   Tools used: {len(tools)}")

        await orchestrator.close()
        return True

    except Exception as e:
        print(f"❌ Direct client test failed: {e}")
        return False


async def test_chatbox_orchestrator():
    """Test ChatBox orchestrator with Lily-Core."""
    print("🔍 Testing ChatBox orchestrator...")

    try:
        orchestrator = ChatBoxLLMOrchestrator(
            tool_use_enabled=False  # Disable agent loop for simple test
        )

        await orchestrator.initialize()

        # Test basic chat
        response, tools = await orchestrator.get_response(
            "Hi there! This is a test message."
        )

        print("✅ ChatBox orchestrator test successful!"        print(f"   Response: {response[:100]}...")
        print(f"   Tools used: {len(tools)}")

        await orchestrator.close()
        return True

    except Exception as e:
        print(f"❌ ChatBox orchestrator test failed: {e}")
        return False


async def test_discord_orchestrator():
    """Test Discord orchestrator with Lily-Core."""
    print("🔍 Testing Discord orchestrator...")

    try:
        orchestrator = DiscordLLMOrchestrator(
            tool_use_enabled=False  # Disable agent loop for simple test
        )

        await orchestrator.initialize()

        # Test basic chat
        response, tools = await orchestrator.get_response(
            "Hello from Discord!",
            discord_user_id=12345,
            discord_user_name="TestUser"
        )

        print("✅ Discord orchestrator test successful!"        print(f"   Response: {response[:100]}...")
        print(f"   Tools returned: {tools}")

        await orchestrator.close()
        return True

    except Exception as e:
        print(f"❌ Discord orchestrator test failed: {e}")
        return False


async def run_all_tests():
    """Run all integration tests."""
    print("🚀 Starting Lily-Core integration tests...")
    print("=" * 50)

    results = []

    # Test 1: Direct Lily-Core client
    results.append(await test_lily_core_direct())
    print()

    # Test 2: ChatBox orchestrator
    results.append(await test_chatbox_orchestrator())
    print()

    # Test 3: Discord orchestrator
    results.append(await test_discord_orchestrator())
    print()

    # Summary
    passed = sum(results)
    total = len(results)

    print("=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! Lily-Core integration is working correctly.")
        return True
    else:
        print("⚠️  Some tests failed. Check Lily-Core service and configuration.")
        return False


def check_requirements():
    """Check if Lily-Core service is running."""
    print("🔧 Checking requirements...")

    lily_core_url = os.getenv('LILY_CORE_URL', 'http://localhost:8000')
    print(f"   Lily-Core URL: {lily_core_url}")
    print(f"   Note: Make sure Lily-Core service is running at {lily_core_url}")
    print()

    return True


async def main():
    """Main test function."""
    print("Lily-Core Integration Test for LilyTheThird")
    print("This test verifies that LilyTheThird can communicate with Lily-Core.")
    print()

    # Check requirements
    if not check_requirements():
        print("❌ Requirements not met. Exiting.")
        return False

    # Run tests
    success = await run_all_tests()

    return success


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        exit_code = 0 if success else 1
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print(f"\n💥 Test failed with unexpected error: {e}")
        sys.exit(1)