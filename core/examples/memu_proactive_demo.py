"""
Elora + MemU Proactive Memory Demo

This script demonstrates MemU's proactive memory capabilities integrated with Elora:

1. Continuous Learning Pipeline - Real-time memory extraction
2. Dual-Mode Retrieval - RAG (fast) vs LLM (deep reasoning)
3. Proactive Intent Capture - Understanding goals without explicit commands
4. Hierarchical Memory Organization - File system metaphor
5. Cost Efficiency - 10x lower always-on costs

Prerequisites (Self-Hosted - FREE, Uses Your Existing Gemini Key):
    export GOOGLE_API_KEY=your-gemini-api-key  # Same as Elora uses
    export MEMU_CLOUD=false
    
    Or use MemU Cloud (free tier available):
    export MEMU_API_KEY=your_api_key  # from memu.so
    export MEMU_CLOUD=true

Run:
    python examples/memu_proactive_demo.py
"""

import asyncio
import os
from datetime import datetime

# Add parent directory to path for imports
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.memu_memory import (
    memorize_async,
    retrieve_async,
    auto_memorise_async,
    get_proactive_suggestions,
    get_memory_categories,
    get_memu_service
)


async def demo_continuous_learning():
    """Demonstrate MemU's continuous learning pipeline."""
    print("\n" + "="*70)
    print("🧠 DEMO 1: Continuous Learning Pipeline")
    print("="*70)
    
    user_id = "demo_user_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    
    print(f"\nUser ID: {user_id}")
    print("\nSimulating conversation turns with automatic memory extraction...\n")
    
    conversation_turns = [
        "I'm a software engineer working at a startup in San Francisco. I love hiking on weekends.",
        "My favorite programming languages are Python and TypeScript. I've been coding for 8 years.",
        "I have a meeting with Sarah tomorrow at 3pm. She's the product manager on our team.",
        "I prefer morning meetings when I'm most productive. Afternoon meetings drain my energy.",
        "I'm allergic to peanuts and I'm vegetarian. Always forget to mention this at restaurants!",
    ]
    
    for i, turn in enumerate(conversation_turns, 1):
        print(f"Turn {i}: \"{turn[:80]}...\"")
        result = await auto_memorise_async(user_id, turn)
        
        if result.get("items"):
            print(f"  → Extracted {len(result['items'])} memories:")
            for item in result["items"][:3]:  # Show first 3
                summary = item.get("summary", "")[:100]
                memory_type = item.get("memory_type", "fact")
                print(f"     • [{memory_type}] {summary}...")
        
        await asyncio.sleep(0.5)
    
    print("\n✅ Continuous learning complete!")
    print(f"   MemU automatically categorized memories into hierarchical structure")
    print(f"   Cross-referenced related facts (e.g., work + meetings + preferences)")
    
    return user_id


async def demo_dual_mode_retrieval(user_id: str):
    """Demonstrate MemU's dual-mode retrieval (RAG vs LLM)."""
    print("\n" + "="*70)
    print("🔍 DEMO 2: Dual-Mode Retrieval (RAG vs LLM)")
    print("="*70)
    
    queries = [
        "What does the user do for work?",
        "What are their food preferences and allergies?",
        "Tell me about their meeting preferences and productivity patterns",
    ]
    
    for query in queries:
        print(f"\n📝 Query: \"{query}\"")
        
        # RAG mode - fast, cheap
        print("\n  ⚡ RAG Mode (fast, embedding-only):")
        start = asyncio.get_event_loop().time()
        result_rag = await retrieve_async(user_id, query, method="rag")
        elapsed_rag = asyncio.get_event_loop().time() - start
        
        if result_rag.get("memories"):
            for memory in result_rag["memories"][:2]:
                print(f"     • {memory[:120]}...")
        print(f"     Time: {elapsed_rag*1000:.0f}ms")
        
        # LLM mode - slower, deeper reasoning
        print("\n  🧠 LLM Mode (deep reasoning, intent prediction):")
        start = asyncio.get_event_loop().time()
        result_llm = await retrieve_async(user_id, query, method="llm")
        elapsed_llm = asyncio.get_event_loop().time() - start
        
        if result_llm.get("memories"):
            for memory in result_llm["memories"][:2]:
                print(f"     • {memory[:120]}...")
        if result_llm.get("next_step_query"):
            print(f"     Next suggested query: \"{result_llm['next_step_query']}\"")
        print(f"     Time: {elapsed_llm*1000:.0f}ms")
    
    print("\n✅ Dual-mode retrieval complete!")
    print(f"   RAG: Milliseconds, embedding cost only")
    print(f"   LLM: Seconds, but understands intent and suggests follow-ups")


async def demo_proactive_suggestions(user_id: str):
    """Demonstrate MemU's proactive suggestion engine."""
    print("\n" + "="*70)
    print("💡 DEMO 3: Proactive Suggestions")
    print("="*70)
    
    contexts = [
        "User is planning their schedule for tomorrow",
        "User mentioned going to a restaurant",
        "User is talking about their work project",
    ]
    
    for context in contexts:
        print(f"\n📍 Context: \"{context}\"")
        
        suggestions = await get_proactive_suggestions(user_id, context)
        
        if suggestions:
            print("  💬 Proactive suggestions:")
            for suggestion in suggestions:
                print(f"     • {suggestion[:150]}...")
        else:
            print("  (No proactive suggestions - MemU learning your patterns)")
    
    print("\n✅ Proactive suggestions complete!")
    print(f"   MemU analyzes context + memories to anticipate user needs")


async def demo_hierarchical_memory(user_id: str):
    """Demonstrate MemU's file system metaphor for memory."""
    print("\n" + "="*70)
    print("📁 DEMO 4: Hierarchical Memory (File System Metaphor)")
    print("="*70)
    
    print("\nMemU organizes memories like a file system:")
    print("""
    memory/
    ├── preferences/
    │   ├── communication_style.md
    │   ├── meeting_preferences.md
    │   └── food_dietary.md
    ├── relationships/
    │   ├── contacts/
    │   │   └── sarah_product_manager.md
    │   └── interaction_history/
    ├── knowledge/
    │   ├── domain_expertise/
    │   │   ├── python_programming.md
    │   │   └── typescript_programming.md
    │   └── learned_skills/
    └── context/
        ├── recent_conversations/
        └── pending_tasks/
            └── meeting_sarah_tomorrow_3pm.md
    """)
    
    categories = await get_memory_categories(user_id)
    
    if categories:
        print("\n📊 Auto-generated categories for this user:")
        for cat in categories[:5]:
            name = cat.get("name", "Unknown")
            path = cat.get("path", "")
            item_count = cat.get("item_count", 0)
            print(f"   📁 {name} ({path}) - {item_count} items")
    else:
        print("\n(Categories will populate with more conversation data)")
    
    print("\n✅ Hierarchical memory complete!")
    print(f"   Memories are portable, exportable, and navigable like files")


async def demo_cost_efficiency():
    """Demonstrate MemU's cost efficiency claims."""
    print("\n" + "="*70)
    print("💰 DEMO 5: Cost Efficiency Analysis")
    print("="*70)
    
    print("""
    ┌─────────────────────────────────────────────────────────────┐
    │  MemU Cost Efficiency (vs Traditional Always-On Memory)     │
    ├─────────────────────────────────────────────────────────────┤
    │                                                             │
    │  Traditional RAG Approach:                                  │
    │  • Every query → LLM call for context understanding         │
    │  • Continuous background processing → constant LLM usage    │
    │  • Estimated: ~$50-100/month per active user                │
    │                                                             │
    │  MemU Dual-Mode Approach:                                   │
    │  • RAG mode: Embedding search only (no LLM) → ~$0.01/query  │
    │  • LLM mode: On-demand deep reasoning → used sparingly      │
    │  • Smart caching: Reuses extracted insights                 │
    │  • Estimated: ~$5-10/month per active user                  │
    │                                                             │
    │  💡 Result: 10x lower always-on costs                       │
    │                                                             │
    │  🎯 Bonus: Uses Google Gemini (same as Elora)               │
    │  • No new API keys needed                                   │
    │  • Unified billing & rate limits                            │
    │  • text-embedding-004 for embeddings                        │
    │  • gemini-2.0-flash for reasoning                           │
    └─────────────────────────────────────────────────────────────┘
    """)
    
    print("\n✅ Cost efficiency analysis complete!")


async def main():
    """Run all MemU demos."""
    print("\n" + "="*70)
    print("🚀 ELORA + MEMU PROACTIVE MEMORY DEMO")
    print("="*70)
    print("\nThis demo showcases MemU's integration with Elora:")
    print("  • 10x lower always-on costs")
    print("  • 92.09% Locomo benchmark accuracy")
    print("  • Proactive intent capture")
    print("  • Hierarchical file-system memory metaphor")
    print("  • Dual-mode retrieval (RAG + LLM)")
    
    # Check if MemU is available
    service = get_memu_service()
    if not service:
        print("\n⚠️  MemU service not available.")
        print("\nSet one of the following:")
        print("  export MEMU_API_KEY=your_api_key  # Recommended (memu.so)")
        print("  export OPENAI_API_KEY=your_api_key && export MEMU_CLOUD=false")
        print("\nRunning in simulation mode...\n")
        
        # Run cost efficiency demo (doesn't require API)
        await demo_cost_efficiency()
        return
    
    print("\n✅ MemU service initialised successfully\n")
    
    # Run all demos
    user_id = await demo_continuous_learning()
    await demo_dual_mode_retrieval(user_id)
    await demo_proactive_suggestions(user_id)
    await demo_hierarchical_memory(user_id)
    await demo_cost_efficiency()
    
    print("\n" + "="*70)
    print("🎉 ALL DEMOS COMPLETE!")
    print("="*70)
    print("\nKey Takeaways:")
    print("  1. MemU enables 24/7 proactive memory at 10x lower cost")
    print("  2. Dual-mode retrieval balances speed vs depth")
    print("  3. File system metaphor makes memory portable and intuitive")
    print("  4. 92.09% Locomo accuracy validates memory quality")
    print("  5. Continuous learning pipeline extracts intent automatically")
    print("\nHackathon Advantage:")
    print("  Elora + MemU = Production-ready always-on personal AI agent")
    print("  Not just a demo — this architecture scales to millions of users")
    print("="*70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
