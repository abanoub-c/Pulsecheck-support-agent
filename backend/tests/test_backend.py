import sys
import os

# Tell Python to look in the 'app' folder next door to find main.py
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../app')))

from fastapi.testclient import TestClient
from main import app

def run_tests():
    print("🚀 Starting Pulsecheck Backend Tests...\n")
    passed = 0
    failed = 0

    def assert_test(name: str, condition: bool, error_msg: str = ""):
        nonlocal passed, failed
        if condition:
            print(f"✅ PASS: {name}")
            passed += 1
        else:
            print(f"❌ FAIL: {name} | {error_msg}")
            failed += 1

    # Wrapping the client in a 'with' statement forces the @app.on_event("startup") 
    # to run, which builds and seeds our mock database!
    with TestClient(app) as client:
        
        # --- TEST 1: The Missing Invoices ---
        res = client.get("/invoices/CUST-0005")
        assert_test(
            "Invoices endpoint returns seeded data", 
            res.status_code == 200 and len(res.json()) > 0, 
            f"Expected list of invoices, got: {res.text}"
        )

        # --- TEST 2: The Incidents Endpoint Default ---
        res = client.get("/incidents")
        data = res.json()
        has_resolved = any(inc["status"] == "resolved" for inc in data)
        assert_test(
            "Incidents endpoint shows resolved issues by default", 
            res.status_code == 200 and has_resolved, 
            "Did not find any 'resolved' incidents in the default response."
        )

        # --- TEST 3: Typo Guardrail (Strict Types) ---
        res = client.post("/tickets", json={
            "customer_id": "CUST-0001",
            "category": "biling",  # Intentional typo (missing an L)
            "subtype": "test",
            "subject": "test",
            "message": "test"
        })
        assert_test(
            "Ticket category typo is correctly blocked (422 Error)", 
            res.status_code == 422, 
            "API accepted a bad category instead of rejecting it."
        )

        # --- TEST 4: Duplicate Refund Guardrail ---
        # Request 1: Should succeed
        client.post("/refunds", json={"customer_id": "CUST-0003", "amount": 75.00, "reason": "First request"})
        # Request 2: Exact same amount/customer today, should fail
        res_dup = client.post("/refunds", json={"customer_id": "CUST-0003", "amount": 75.00, "reason": "Duplicate attempt"})
        assert_test(
            "Duplicate refund is blocked (409 Error)", 
            res_dup.status_code == 409, 
            "API allowed the same refund amount twice."
        )

        # --- TEST 5: Ops Dashboard PATCH Route ---
        # Create a pending refund ($150)
        res_large = client.post("/refunds", json={"customer_id": "CUST-0004", "amount": 150.00, "reason": "Large refund"})
        refund_id = res_large.json().get("refund_id")
        
        # Simulate a human rejecting it via the dashboard
        res_patch = client.patch(f"/refunds/{refund_id}", json={
            "status": "rejected",
            "notes": "Rejected by manager"
        })
        assert_test(
            "PATCH /refunds works for human Ops Dashboard", 
            res_patch.status_code == 200 and res_patch.json().get("status") == "rejected", 
            f"Patch failed: {res_patch.text}"
        )

    print(f"\n🎯 Results: {passed} Passed, {failed} Failed")
    if failed == 0:
        print("🌟 YOU ARE GOOD TO GO! Your backend is officially bulletproof.")
    else:
        print("⚠️ Check the errors above and review your code.")

if __name__ == "__main__":
    run_tests()