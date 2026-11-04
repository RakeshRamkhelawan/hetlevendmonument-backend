#!/usr/bin/env python3
"""
Test Workflow Generation Logging

This script tests the workflow generation endpoint and displays timing information.
Use this to verify the logging and performance breakdown.

Usage:
    python test_workflow_generation_logging.py

Or test specific complexity:
    python test_workflow_generation_logging.py --complexity simple
    python test_workflow_generation_logging.py --complexity complex
"""

import asyncio
import json
import sys
from datetime import datetime, timezone

import httpx

# Configuration
API_BASE_URL = "http://localhost:8100"  # Port updated from 8000 to 8100
WORKFLOW_GENERATION_ENDPOINT = f"{API_BASE_URL}/api/v1/vibe/generate"

# Test prompts
TEST_PROMPTS = {
    "simple": "Send an email to admin when a task is completed",
    "medium": "Build a daily standup workflow that fetches team status from database, summarizes with AI, and posts to Slack at 9am",
    "complex": "Create an automated incident response workflow that monitors system health, detects anomalies using ML, creates Jira tickets, notifies stakeholders via Slack, logs to database, and generates a daily report",
}


async def test_workflow_generation(complexity: str = "medium"):
    """
    Test workflow generation and display timing breakdown.
    """
    if complexity not in TEST_PROMPTS:
        print("❌ Invalid complexity. Choose: simple, medium, or complex")
        return

    prompt = TEST_PROMPTS[complexity]
    print(f"\n{'='*80}")
    print(f"🧪 WORKFLOW GENERATION TEST - {complexity.upper()}")
    print(f"{'='*80}\n")
    print(f"📝 Prompt: {prompt[:80]}...\n")
    print(f"⏱️  Starting request at {datetime.now(timezone.utc).strftime('%H:%M:%S')}")
    print(f"{'─'*80}\n")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            start_time = asyncio.get_event_loop().time()

            # Make request
            response = await client.post(
                WORKFLOW_GENERATION_ENDPOINT,
                json={"prompt": prompt, "complexity": complexity, "tenant_id": 1},
            )

            end_time = asyncio.get_event_loop().time()
            total_time = (end_time - start_time) * 1000

            # Parse response
            data = response.json()

            # Display results
            print("📊 RESPONSE ANALYSIS:")
            print(f"{'─'*80}")
            print(f"Status Code: {response.status_code}")
            print(f"Correlation ID: {data.get('correlation_id', 'N/A')}")
            print(f"Success: {data.get('success', False)}")
            print("\n⏱️  TIMING:")
            print(f"  • API Response Time: {total_time:.0f}ms")
            print(f"  • Generation Time (server): {data.get('generation_time_ms', 0):.2f}ms")
            print("\n📐 WORKFLOW STRUCTURE:")
            print(f"  • Nodes: {data.get('node_count', 0)}")
            print(f"  • Edges: {data.get('edge_count', 0)}")

            if data.get("success"):
                print("\n✅ SUCCESS! Workflow generated")
                if "workflow" in data and data["workflow"]:
                    wf = data["workflow"]
                    print("\n📋 WORKFLOW DETAILS:")
                    print(f"  • Name: {wf.get('name', 'N/A')}")
                    print(f"  • Description: {wf.get('description', 'N/A')[:60]}...")
                    print("\n🔗 NODES:")
                    for node in wf.get("nodes", [])[:3]:  # Show first 3 nodes
                        print(f"  • {node.get('label', 'Unknown')} ({node.get('agent_name')})")
                    if len(wf.get("nodes", [])) > 3:
                        print(f"  ... and {len(wf.get('nodes', [])) - 3} more")
            else:
                print("\n❌ FAILED")
                print(f"Error: {data.get('error', 'Unknown error')}")

    except httpx.ConnectError:
        print(f"❌ Could not connect to backend at {API_BASE_URL}")
        print("   Make sure the backend is running on port 8000")
        print("\n   Start backend with:")
        print("   docker-compose -f docker-compose.dev.yml up -d backend")
        return

    except httpx.TimeoutException:
        print("❌ Request timed out after 60 seconds")
        print("   This might indicate a problem with the API")
        return

    except Exception as e:
        print(f"❌ Error: {e}")
        return

    print(f"\n{'='*80}\n")


async def main():
    """Main test runner."""
    complexity = "medium"

    # Parse command line args
    if len(sys.argv) > 1:
        if sys.argv[1] == "--help":
            print("Usage: python test_workflow_generation_logging.py [--complexity LEVEL]")
            print("LEVEL: simple, medium, or complex (default: medium)")
            return
        elif sys.argv[1] == "--complexity" and len(sys.argv) > 2:
            complexity = sys.argv[2]

    await test_workflow_generation(complexity)


if __name__ == "__main__":
    print("🚀 Workflow Generation Logging Test Suite\n")
    asyncio.run(main())
