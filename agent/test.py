"""
Pulsecheck support agent — End-to-End Graph Test Harness.

Belongs at: agent/test_graph.py
Run with: python agent/test_graph.py (Ensure FastAPI backend is running on http://127.0.0.1:8000)
"""

import sys
import os
# THIS MUST COME FIRST! It tells Python where to look for the 'agent' folder.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from dotenv import load_dotenv
load_dotenv()

from langchain_core.messages import HumanMessage
from agent.graph import graph
from agent.state import new_support_state

# ... (Keep the rest of your file exactly the same!)
def run_test_scenario(title: str, user_message: str, customer_id: str = "CUST-0005"):
    print(f"\n==================================================")
    print(f"🧪 SCENARIO: {title}")
    print(f"👤 User: '{user_message}'")
    print(f"==================================================")

    # Build fresh graph state
    initial_state = new_support_state(
        thread_id="test_thread_001",
        customer_id=customer_id,
        first_message=HumanMessage(content=user_message)
    )

    # Execute the graph
    final_state = graph.invoke(initial_state)

    print(f"\n📊 FINAL STATE SUMMARY:")
    print(f"• Category: {final_state.get('category')}")
    print(f"• Confidence: {final_state.get('confidence')}")
    print(f"• Resolution Status: {final_state.get('resolution_status')}")
    print(f"• Actions Taken (Tools Called): {len(final_state.get('actions_taken', []))}")
    
    # Print final agent response message
    messages = final_state.get("messages", [])
    if messages:
        print(f"\n🤖 Agent Reply:\n{messages[-1].content}")

if __name__ == "__main__":
    # Test 1: Billing Specialist (Invoice check)
    run_test_scenario(
        title="Billing Query (Failed Invoice Check)",
        user_message="Why was my card charged or why did my payment fail last week? Customer ID CUST-0005."
    )

    # Test 2: Technical Specialist (Deduplication check on known incident)
    run_test_scenario(
        title="Technical Query (Known Outage Check)",
        user_message="My API monitors are throwing errors and DNS seems down. Is something broken?"
    )

    # Test 3: Refund Specialist (<$100 Auto-Approval)
    run_test_scenario(
        title="Refund Query (<$100 Auto-Approval)",
        user_message="I'd like a refund of $50 for the downtime yesterday. Customer ID CUST-0003."
    )

    # Test 4: Low Confidence Escalation
    run_test_scenario(
        title="Ambiguous / Unrelated Query (Escalation)",
        user_message="Can you tell me a joke about airplanes?"
    )