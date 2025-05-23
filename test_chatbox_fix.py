#!/usr/bin/env python3
"""
Test script to verify ChatBoxLLM performance fix.
Tests that simple messages like "hello" process efficiently without excessive retry loops.
"""

import asyncio
import sys
from llm.chatbox_llm import ChatBoxLLM

async def test_simple_message():
    """Test that simple conversational messages process efficiently."""
    
    print("=== Testing ChatBoxLLM Performance Fix ===")
    print("Creating ChatBoxLLM instance with Gemini provider...")
    
    # Initialize with Gemini provider explicitly
    chatbox = ChatBoxLLM(provider="gemini")
    
    if not chatbox.llm_client.client:
        print("ERROR: Failed to initialize ChatBoxLLM with Gemini provider")
        print("Check that Gemini API keys are properly configured in llm_api_keys.json")
        return False
    
    print(f"✓ ChatBoxLLM initialized successfully")
    print(f"  Provider: {chatbox.llm_client.provider}")
    print(f"  Model: {chatbox.llm_client.model}")
    print()
    
    # Test simple greeting that should NOT trigger tool selection loops
    test_message = "hello"
    print(f"Testing simple message: '{test_message}'")
    print("This should process quickly without excessive tool selection retry loops...")
    print()
    
    try:
        # Process the message and measure performance
        response, tool_calls = await chatbox.get_response(test_message)
        
        print("=== RESULTS ===")
        print(f"Response: {response}")
        print(f"Tool calls made: {len(tool_calls) if tool_calls else 0}")
        
        if tool_calls:
            print("Tool calls:")
            for i, call in enumerate(tool_calls, 1):
                print(f"  {i}. {call.get('tool_name', 'Unknown')} - {call.get('result', '')[:100]}...")
        
        # Check if this was efficient (should be minimal tool calls for simple greeting)
        if not tool_calls or len(tool_calls) <= 2:
            print("\n✓ SUCCESS: Message processed efficiently with minimal tool usage")
            return True
        else:
            print(f"\n⚠ WARNING: Message triggered {len(tool_calls)} tool calls - may still have performance issues")
            return False
            
    except Exception as e:
        print(f"ERROR during test: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Main test function."""
    success = await test_simple_message()
    
    if success:
        print("\n🎉 Performance fix appears to be working correctly!")
        sys.exit(0)
    else:
        print("\n❌ Performance issues may still exist or test failed")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
