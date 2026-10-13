"""scripts/evaluate.py — Evaluate system accuracy on sample queries."""
import asyncio
import uuid
import sys
import os
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from app.graph.state import new_state
from app.graph.workflow import get_workflow
from app.storage.database import app_session
from app.storage.models import Source

TEST_QUERIES = [
    "How many rows are in the dataset?",
    "What is the total sales amount across all regions?",
    "Which category has the highest average customer rating?",
    "Show me the sales trend by month in North America.",
]

async def evaluate():
    print("Starting evaluation...")
    workflow = get_workflow()
    
    with app_session() as session:
        src = session.query(Source).first()
        if not src:
            print("No source found. Run load_sample_data.py first.")
            return
        source_id = src.id

    results = []
    
    for q in TEST_QUERIES:
        print(f"\nQ: {q}")
        session_id = str(uuid.uuid4())
        state = new_state(
            question=q,
            session_id=session_id,
            source_id=source_id,
        )
        
        try:
            final_state = None
            async for event in workflow.astream(state):
                for node_name, node_state in event.items():
                    state.update(node_state)
                    final_state = state
            
            if final_state is None:
                final_state = {}
            sql = final_state.get('generated_sql')
            verified = final_state.get('verified', False)
            rows = final_state.get('result_row_count', 0)
            print(f"SQL Generated: {sql is not None}")
            print(f"Rows Returned: {rows}")
            print(f"Verified: {verified}")
            
            results.append({
                "question": q,
                "sql_generated": sql is not None,
                "verified": verified,
                "rows": rows
            })
        except Exception as e:
            print(f"Error: {e}")
            results.append({
                "question": q,
                "sql_generated": False,
                "verified": False,
                "error": str(e)
            })
            
    print("\n--- Benchmark Results ---")
    total = len(results)
    success = sum(1 for r in results if r.get("sql_generated"))
    verified = sum(1 for r in results if r.get("verified"))
    print(f"Total Queries: {total}")
    print(f"SQL Generated: {success}/{total} ({success/total*100:.1f}%)")
    print(f"Pandas Verified: {verified}/{total} ({verified/total*100:.1f}%)")

if __name__ == "__main__":
    asyncio.run(evaluate())
