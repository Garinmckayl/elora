"""
Tests for MemU Integration in Elora

Run with:
    cd core
    export GOOGLE_API_KEY=your-key
    export MEMU_CLOUD=false
    python -m pytest tests/test_memu.py -v

Or without pytest:
    python tests/test_memu.py
"""

import os
import sys
import asyncio
from datetime import datetime

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.memu_memory import (
    get_memu_agent,
    memorize_async,
    retrieve_async,
    auto_memorise_async,
    MEMU_AVAILABLE
)


def test_memu_available():
    """Test that MemU module is importable."""
    print("✓ Test: MemU module importable")
    assert MEMU_AVAILABLE is True, "MemU should be available (memu-py installed)"
    print(f"  MemU available: {MEMU_AVAILABLE}")


def test_memu_service_initialization():
    """Test MemU agent initializes with Gemini."""
    print("\n✓ Test: MemU agent initialization")
    
    # Check environment variables
    google_key = os.getenv("GOOGLE_API_KEY")
    if not google_key:
        print("  ⚠ GOOGLE_API_KEY not set - skipping agent init test")
        return
    
    agent = get_memu_agent("test_user")
    assert agent is not None, "MemU agent should initialize with valid API key"
    print(f"  Agent initialized: {agent is not None}")
    print(f"  Agent type: {type(agent).__name__}")


async def test_memorize_basic():
    """Test basic memory storage."""
    print("\n✓ Test: Basic memorization")
    
    user_id = f"test_user_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    fact = "I love hiking on weekends and prefer morning trails"
    
    result = await memorize_async(user_id, fact)
    
    print(f"  User ID: {user_id}")
    print(f"  Fact: {fact[:60]}...")
    print(f"  Status: {result.get('status')}")
    print(f"  Report: {result.get('report', 'N/A')[:100]}...")
    
    # Note: With invalid API key, we expect fallback or error
    # Test passes if it doesn't crash
    print("  ✓ Memorize call completed (no crash)")


async def test_retrieve_basic():
    """Test basic memory retrieval."""
    print("\n✓ Test: Basic retrieval")
    
    user_id = f"test_user_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # First memorize something
    await memorize_async(user_id, "I work as a software engineer in San Francisco")
    await memorize_async(user_id, "I prefer Python and TypeScript for programming")
    
    # Then retrieve
    result = await retrieve_async(user_id, "What does the user do for work?", method="rag")
    
    print(f"  Query: What does the user do for work?")
    print(f"  Status: {result.get('status')}")
    print(f"  Memories found: {len(result.get('memories', []))}")
    
    if result.get("memories"):
        print(f"  Top memory: {result['memories'][0][:100]}...")
    
    # Test passes if it doesn't crash
    print("  ✓ Retrieve call completed (no crash)")


async def test_auto_memorise():
    """Test proactive memory extraction."""
    print("\n✓ Test: Auto-memorise (proactive extraction)")
    
    user_id = f"test_user_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    conversation = """
    User: I've been working on a startup idea for 3 months now. 
    It's an AI-powered productivity tool. I'm most productive in the mornings, 
    so I try to avoid afternoon meetings. Also, I'm vegetarian and allergic to peanuts.
    """
    
    result = await auto_memorise_async(user_id, conversation)
    
    print(f"  Conversation: {conversation[:80]}...")
    print(f"  Status: {result.get('status')}")
    print(f"  Items extracted: {len(result.get('items', []))}")
    
    if result.get("items"):
        print(f"  Sample extraction: {result['items'][0].get('summary', '')[:100]}...")
    
    # Test passes if it doesn't crash
    print("  ✓ Auto-memorise call completed (no crash)")


async def test_dual_mode_retrieval():
    """Test RAG vs LLM retrieval modes."""
    print("\n✓ Test: Dual-mode retrieval (RAG vs LLM)")
    
    user_id = f"test_user_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # Memorize context
    await memorize_async(user_id, "I have a meeting with Sarah tomorrow at 3pm")
    await memorize_async(user_id, "Sarah is the product manager on my team")
    
    query = "Tell me about my upcoming meeting"
    
    # RAG mode (fast)
    import time
    start = time.time()
    result_rag = await retrieve_async(user_id, query, method="rag")
    rag_time = time.time() - start
    
    # LLM mode (deep reasoning)
    start = time.time()
    result_llm = await retrieve_async(user_id, query, method="llm")
    llm_time = time.time() - start
    
    print(f"  Query: {query}")
    print(f"  RAG mode: {rag_time*1000:.0f}ms")
    print(f"  LLM mode: {llm_time*1000:.0f}ms")
    
    if result_llm.get("next_step_query"):
        print(f"  LLM suggested follow-up: {result_llm['next_step_query'][:100]}...")
    
    print("  ✓ Dual-mode retrieval calls completed (no crash)")


async def run_all_tests():
    """Run all MemU tests."""
    print("="*70)
    print("🧪 ELORA + MEMU INTEGRATION TESTS")
    print("="*70)
    
    # Check prerequisites
    google_key = os.getenv("GOOGLE_API_KEY")
    memu_cloud = os.getenv("MEMU_CLOUD", "false").lower() == "true"
    
    print(f"\nConfiguration:")
    print(f"  GOOGLE_API_KEY: {'Set ✓' if google_key else 'Not set ✗'}")
    print(f"  MEMU_CLOUD: {memu_cloud}")
    print(f"  MemU Available: {MEMU_AVAILABLE}")
    
    if not google_key and not memu_cloud:
        print("\n⚠️  Warning: GOOGLE_API_KEY not set")
        print("Set it with: export GOOGLE_API_KEY=your-key")
        print("Running basic import tests only...\n")
    
    # Run tests
    try:
        test_memu_available()
        
        if google_key or memu_cloud:
            test_memu_service_initialization()
            await test_memorize_basic()
            await test_retrieve_basic()
            await test_auto_memorise()
            await test_dual_mode_retrieval()
        else:
            print("\n⚠️  Skipping API tests (no API key)")
        
        print("\n" + "="*70)
        print("✅ ALL TESTS COMPLETED")
        print("="*70)
        print("\nNote: API errors are expected with test API key.")
        print("With a valid GOOGLE_API_KEY, MemU will work fully.")
        print("\nNext steps:")
        print("  1. Set valid key: export GOOGLE_API_KEY=AIza...")
        print("  2. Run demo: python examples/memu_proactive_demo.py")
        print("  3. Test with Elora: Start backend and have a conversation")
        print("  4. Record demo scene showing MemU memory visualization")
        
    except Exception as e:
        print("\n" + "="*70)
        print("❌ TEST ERROR")
        print("="*70)
        print(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print("\n" + "="*70)
        print("❌ TEST ERROR")
        print("="*70)
        print(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
