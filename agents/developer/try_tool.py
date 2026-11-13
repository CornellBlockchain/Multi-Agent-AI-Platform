"""Run one tool thru run_tool"""
import asyncio
import json
import sys
from dotenv import load_dotenv
load_dotenv()
from tools import run_tool

name, args = sys.argv[1], json.loads(sys.argv[2])
ctx = {"run_id": "r1", "task_id": "t1", "events": [], "sources": [], "artifacts": []}
result = asyncio.run(run_tool(name, args, ctx))

print('\n--- Result ---')
print(str(result.get("summary", result))[:2000])
print('\n--- Sources ---')
for s in ctx["sources"]:
    print(f"{s['title']}: {s['url']}")

