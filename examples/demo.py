#!/usr/bin/env python3
"""End-to-end demo of the No-Slop Harness CIV pipeline.

This script demonstrates a full Coordinator → Implementor → Verifier
pipeline using a local LM Studio instance.

Usage:
    python examples/demo.py "Add a User model with email and password fields"

Requirements:
    - LM Studio running on localhost:1234 (or set NO_SLOP_API_URL)
    - httpx installed: pip install no-slop-harness[inference]
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Add the src directory to path for development runs
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from no_slop_harness.runner import CIVPipeline


async def main() -> None:
    request = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Add a hello() function to /tmp/demo.py that returns 'Hello, World!'"

    base_url = os.environ.get("NO_SLOP_API_URL", "http://localhost:1234/v1")
    model = os.environ.get("NO_SLOP_MODEL", "qwen/qwen3.6-35b-a3b")
    api_key = os.environ.get("NO_SLOP_API_KEY", "not-needed")

    print(f"╔══════════════════════════════════════════════════╗")
    print(f"║   No-Slop Harness — CIV Pipeline Demo           ║")
    print(f"╠══════════════════════════════════════════════════╣")
    print(f"║ API: {base_url:<42} ║")
    print(f"║ Model: {model:<40} ║")
    print(f"╚══════════════════════════════════════════════════╝")
    print()
    print(f"Request: {request}")
    print()

    pipeline = CIVPipeline(
        base_url=base_url,
        model=model,
        api_key=api_key,
        work_dir=Path.cwd(),
    )

    try:
        print("─" * 55)
        print("Phase 1: Coordinator — decomposing request...")
        print("─" * 55)

        result = await pipeline.run(request)

        print()
        print("─" * 55)
        print("Pipeline Complete!")
        print("─" * 55)
        print(f"Success: {result['success']}")
        print(f"Request ID: {result['request_id']}")
        print(f"Tasks: {result['tasks_total']} total, "
              f"{result['tasks_completed']} completed, "
              f"{result['tasks_failed']} failed")
        print()

        if result.get("task_results"):
            for tid, tr in result["task_results"].items():
                status = "✓" if tr["success"] else "✗"
                print(f"  [{status}] {tid}: {tr.get('summary', '')[:80]}")
                if "verification" in tr:
                    print(f"       Verify: {tr['verification'][:80]}")

        print()
        print(result["summary"])

    finally:
        await pipeline.close()


if __name__ == "__main__":
    asyncio.run(main())
