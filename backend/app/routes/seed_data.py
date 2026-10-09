"""
Pulsecheck seed data.

Belongs at: backend/app/seed_data.py (per Project 2 build plan, §13).
Used to populate the mock CRM's SQLite DB at startup / via a seed script.

Contains:
    TIER_CONFIG      - plan tiers, monitor limits, and pricing
    CUSTOMERS        - 25 customers across all tiers + a few edge-case statuses
    SUBSCRIPTIONS    - 1:1 with customers, includes past_due / trialing / cancelled
    TICKETS          - 55 historical tickets across billing/technical/refund/other
    KNOWN_INCIDENTS  - 7-item table the technical agent checks before treating
                       an alert as novel

All dates are ISO "YYYY-MM-DD" strings. "Today" for this seed data is 2026-08-25.
"""

# ---------------------------------------------------------------------------
# Tier configuration
# ---------------------------------------------------------------------------

TIER_CONFIG = {
    "starter": {"monitor_limit": 5, "price_monthly": 29},
    "team": {"monitor_limit": 25, "price_monthly": 99},
    "business": {"monitor_limit": 100, "price_monthly": 299},
}

# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------

CUSTOMERS = [
    {"customer_id": "CUST-0001", "company_name": "Northwind Analytics", "contact_name": "Dana Whitfield", "contact_email": "dana.whitfield@northwindanalytics.io", "signup_date": "2024-09-12", "tier": "starter", "account_status": "active"},
    {"customer_id": "CUST-0002", "company_name": "Vertex Cloud Systems", "contact_name": "Marcus Chen", "contact_email": "marcus.chen@vertexcloud.io", "signup_date": "2024-11-03", "tier": "team", "account_status": "active"},
    {"customer_id": "CUST-0003", "company_name": "Bramblewood Software", "contact_name": "Priya Anand", "contact_email": "priya.anand@bramblewood.dev", "signup_date": "2024-08-20", "tier": "business", "account_status": "active"},
    {"customer_id": "CUST-0004", "company_name": "Lumen Data Co", "contact_name": "Tom Reyes", "contact_email": "tom.reyes@lumendata.co", "signup_date": "2025-01-15", "tier": "starter", "account_status": "active"},
    {"customer_id": "CUST-0005", "company_name": "Ferroline Technologies", "contact_name": "Sofia Kruger", "contact_email": "sofia.kruger@ferroline.io", "signup_date": "2025-02-08", "tier": "team", "account_status": "past_due"},
    {"customer_id": "CUST-0006", "company_name": "Crestpoint Systems", "contact_name": "Liam O'Connell", "contact_email": "liam.oconnell@crestpoint.io", "signup_date": "2024-10-05", "tier": "business", "account_status": "active"},
    {"customer_id": "CUST-0007", "company_name": "Ember & Co", "contact_name": "Aisha Bello", "contact_email": "aisha.bello@emberco.dev", "signup_date": "2025-03-22", "tier": "starter", "account_status": "active"},
    {"customer_id": "CUST-0008", "company_name": "Cascadia DevOps", "contact_name": "Jordan Blake", "contact_email": "jordan.blake@cascadiadevops.com", "signup_date": "2025-04-11", "tier": "team", "account_status": "active"},
    {"customer_id": "CUST-0009", "company_name": "Ironleaf Technologies", "contact_name": "Elena Petrova", "contact_email": "elena.petrova@ironleaf.io", "signup_date": "2024-12-01", "tier": "business", "account_status": "active"},
    {"customer_id": "CUST-0010", "company_name": "Solace Systems", "contact_name": "Sam Okafor", "contact_email": "sam.okafor@solacesys.io", "signup_date": "2026-08-14", "tier": "starter", "account_status": "trialing"},
    {"customer_id": "CUST-0011", "company_name": "Nimbus Stack", "contact_name": "Rachel Kim", "contact_email": "rachel.kim@nimbusstack.dev", "signup_date": "2025-05-19", "tier": "team", "account_status": "active"},
    {"customer_id": "CUST-0012", "company_name": "Halcyon Cloud", "contact_name": "Diego Fuentes", "contact_email": "diego.fuentes@halcyoncloud.io", "signup_date": "2025-01-29", "tier": "business", "account_status": "past_due"},
    {"customer_id": "CUST-0013", "company_name": "Driftwood Analytics", "contact_name": "Noor Haddad", "contact_email": "noor.haddad@driftwoodanalytics.com", "signup_date": "2025-06-14", "tier": "starter", "account_status": "active"},
    {"customer_id": "CUST-0014", "company_name": "Quicksilver APIs", "contact_name": "Casey Lindgren", "contact_email": "casey.lindgren@quicksilverapis.dev", "signup_date": "2025-07-02", "tier": "team", "account_status": "active"},
    {"customer_id": "CUST-0015", "company_name": "Anchorpoint Software", "contact_name": "Priyanka Rao", "contact_email": "priyanka.rao@anchorpoint.io", "signup_date": "2024-09-30", "tier": "business", "account_status": "active"},
    {"customer_id": "CUST-0016", "company_name": "Bluepeak Systems", "contact_name": "Mateo Silva", "contact_email": "mateo.silva@bluepeaksys.com", "signup_date": "2025-08-25", "tier": "starter", "account_status": "past_due"},
    {"customer_id": "CUST-0017", "company_name": "Fenwick Digital", "contact_name": "Grace Whitaker", "contact_email": "grace.whitaker@fenwickdigital.io", "signup_date": "2025-09-10", "tier": "team", "account_status": "active"},
    {"customer_id": "CUST-0018", "company_name": "Grayscale Labs", "contact_name": "Ben Alsop", "contact_email": "ben.alsop@grayscalelabs.dev", "signup_date": "2024-07-18", "tier": "starter", "account_status": "cancelled"},
    {"customer_id": "CUST-0019", "company_name": "Hollowbrook Tech", "contact_name": "Yuki Tanaka", "contact_email": "yuki.tanaka@hollowbrooktech.com", "signup_date": "2025-10-05", "tier": "team", "account_status": "active"},
    {"customer_id": "CUST-0020", "company_name": "Ironclad Cloud", "contact_name": "Hannah Voss", "contact_email": "hannah.voss@ironcladcloud.io", "signup_date": "2026-08-10", "tier": "starter", "account_status": "trialing"},
    {"customer_id": "CUST-0021", "company_name": "Juniper Stack", "contact_name": "Omar Farouk", "contact_email": "omar.farouk@juniperstack.dev", "signup_date": "2025-11-12", "tier": "team", "account_status": "active"},
    {"customer_id": "CUST-0022", "company_name": "Kestrel Systems", "contact_name": "Chloe Dubois", "contact_email": "chloe.dubois@kestrelsys.io", "signup_date": "2025-12-01", "tier": "starter", "account_status": "active"},
    {"customer_id": "CUST-0023", "company_name": "Lighthouse Data", "contact_name": "Ravi Menon", "contact_email": "ravi.menon@lighthousedata.co", "signup_date": "2025-02-20", "tier": "team", "account_status": "past_due"},
    {"customer_id": "CUST-0024", "company_name": "Meridian DevOps", "contact_name": "Ingrid Sorensen", "contact_email": "ingrid.sorensen@meridiandevops.com", "signup_date": "2026-01-15", "tier": "starter", "account_status": "active"},
    {"customer_id": "CUST-0025", "company_name": "Novapoint Technologies", "contact_name": "Leo Marchetti", "contact_email": "leo.marchetti@novapoint.io", "signup_date": "2024-06-05", "tier": "starter", "account_status": "cancelled"},
]

# ---------------------------------------------------------------------------
# Subscriptions (1:1 with customers)
# ---------------------------------------------------------------------------

SUBSCRIPTIONS = [
    # account_balance: any goodwill/proration credit on the account (applied to next invoice)
    # discount_percent: active retention discount (0.00 = none)
    # discount_expires_at: when the discount lapses (None = no active discount)
    # retention_offer_used: True = a retention discount was already offered once (can't offer again)
    {"subscription_id": "SUB-0001", "customer_id": "CUST-0001", "tier": "starter", "monitor_limit": 5, "monitors_used": 4, "price_monthly": 29, "status": "active", "created_at": "2024-09-12", "next_billing_date": "2026-09-12", "trial_end_date": None, "cancelled_at": None, "failed_payment_count": 0, "payment_method_last4": "4242", "account_balance": "0.00", "discount_percent": "0.00", "discount_expires_at": None, "retention_offer_used": False},
    {"subscription_id": "SUB-0002", "customer_id": "CUST-0002", "tier": "team", "monitor_limit": 25, "monitors_used": 18, "price_monthly": 99, "status": "active", "created_at": "2024-11-03", "next_billing_date": "2026-09-03", "trial_end_date": None, "cancelled_at": None, "failed_payment_count": 0, "payment_method_last4": "1881", "account_balance": "0.00", "discount_percent": "0.00", "discount_expires_at": None, "retention_offer_used": False},
    {"subscription_id": "SUB-0003", "customer_id": "CUST-0003", "tier": "business", "monitor_limit": 100, "monitors_used": 76, "price_monthly": 299, "status": "active", "created_at": "2024-08-20", "next_billing_date": "2026-09-20", "trial_end_date": None, "cancelled_at": None, "failed_payment_count": 0, "payment_method_last4": "5566", "account_balance": "0.00", "discount_percent": "0.00", "discount_expires_at": None, "retention_offer_used": False},
    {"subscription_id": "SUB-0004", "customer_id": "CUST-0004", "tier": "starter", "monitor_limit": 5, "monitors_used": 3, "price_monthly": 29, "status": "active", "created_at": "2025-01-15", "next_billing_date": "2026-09-15", "trial_end_date": None, "cancelled_at": None, "failed_payment_count": 0, "payment_method_last4": "0912", "account_balance": "0.00", "discount_percent": "0.00", "discount_expires_at": None, "retention_offer_used": False},
    # CUST-0005: past_due — has a small goodwill credit from last cycle's failed-charge apology
    {"subscription_id": "SUB-0005", "customer_id": "CUST-0005", "tier": "team", "monitor_limit": 25, "monitors_used": 22, "price_monthly": 99, "status": "past_due", "created_at": "2025-02-08", "next_billing_date": "2026-08-09", "trial_end_date": None, "cancelled_at": None, "failed_payment_count": 2, "payment_method_last4": "7723", "account_balance": "15.00", "discount_percent": "0.00", "discount_expires_at": None, "retention_offer_used": False},
    # CUST-0006: already used retention offer (downgraded Business→Team, was given 10% for 2 months)
    {"subscription_id": "SUB-0006", "customer_id": "CUST-0006", "tier": "business", "monitor_limit": 100, "monitors_used": 54, "price_monthly": 299, "status": "active", "created_at": "2024-10-05", "next_billing_date": "2026-09-05", "trial_end_date": None, "cancelled_at": None, "failed_payment_count": 0, "payment_method_last4": "3390", "account_balance": "0.00", "discount_percent": "10.00", "discount_expires_at": "2026-11-05", "retention_offer_used": True},
    {"subscription_id": "SUB-0007", "customer_id": "CUST-0007", "tier": "starter", "monitor_limit": 5, "monitors_used": 5, "price_monthly": 29, "status": "active", "created_at": "2025-03-22", "next_billing_date": "2026-09-22", "trial_end_date": None, "cancelled_at": None, "failed_payment_count": 0, "payment_method_last4": "6104", "account_balance": "0.00", "discount_percent": "0.00", "discount_expires_at": None, "retention_offer_used": False},
    {"subscription_id": "SUB-0008", "customer_id": "CUST-0008", "tier": "team", "monitor_limit": 25, "monitors_used": 12, "price_monthly": 99, "status": "active", "created_at": "2025-04-11", "next_billing_date": "2026-09-11", "trial_end_date": None, "cancelled_at": None, "failed_payment_count": 0, "payment_method_last4": "2287", "account_balance": "0.00", "discount_percent": "0.00", "discount_expires_at": None, "retention_offer_used": False},
    {"subscription_id": "SUB-0009", "customer_id": "CUST-0009", "tier": "business", "monitor_limit": 100, "monitors_used": 91, "price_monthly": 299, "status": "active", "created_at": "2024-12-01", "next_billing_date": "2026-09-01", "trial_end_date": None, "cancelled_at": None, "failed_payment_count": 0, "payment_method_last4": "8845", "account_balance": "0.00", "discount_percent": "0.00", "discount_expires_at": None, "retention_offer_used": False},
    {"subscription_id": "SUB-0010", "customer_id": "CUST-0010", "tier": "starter", "monitor_limit": 5, "monitors_used": 2, "price_monthly": 29, "status": "trialing", "created_at": "2026-08-14", "next_billing_date": "2026-08-28", "trial_end_date": "2026-08-28", "cancelled_at": None, "failed_payment_count": 0, "payment_method_last4": "4471", "account_balance": "0.00", "discount_percent": "0.00", "discount_expires_at": None, "retention_offer_used": False},
    {"subscription_id": "SUB-0011", "customer_id": "CUST-0011", "tier": "team", "monitor_limit": 25, "monitors_used": 15, "price_monthly": 99, "status": "active", "created_at": "2025-05-19", "next_billing_date": "2026-09-19", "trial_end_date": None, "cancelled_at": None, "failed_payment_count": 0, "payment_method_last4": "1029", "account_balance": "0.00", "discount_percent": "0.00", "discount_expires_at": None, "retention_offer_used": False},
    # CUST-0012: past_due business — has a credit from a partial refund on the failed billing cycle
    {"subscription_id": "SUB-0012", "customer_id": "CUST-0012", "tier": "business", "monitor_limit": 100, "monitors_used": 88, "price_monthly": 299, "status": "past_due", "created_at": "2025-01-29", "next_billing_date": "2026-08-14", "trial_end_date": None, "cancelled_at": None, "failed_payment_count": 1, "payment_method_last4": "5540", "account_balance": "50.00", "discount_percent": "0.00", "discount_expires_at": None, "retention_offer_used": False},
    {"subscription_id": "SUB-0013", "customer_id": "CUST-0013", "tier": "starter", "monitor_limit": 5, "monitors_used": 5, "price_monthly": 29, "status": "active", "created_at": "2025-06-14", "next_billing_date": "2026-09-14", "trial_end_date": None, "cancelled_at": None, "failed_payment_count": 0, "payment_method_last4": "9902", "account_balance": "0.00", "discount_percent": "0.00", "discount_expires_at": None, "retention_offer_used": False},
    {"subscription_id": "SUB-0014", "customer_id": "CUST-0014", "tier": "team", "monitor_limit": 25, "monitors_used": 20, "price_monthly": 99, "status": "active", "created_at": "2025-07-02", "next_billing_date": "2026-09-02", "trial_end_date": None, "cancelled_at": None, "failed_payment_count": 0, "payment_method_last4": "3315", "account_balance": "0.00", "discount_percent": "0.00", "discount_expires_at": None, "retention_offer_used": False},
    # CUST-0015: considering downgrade — has a 15% retention discount active to prevent churn
    {"subscription_id": "SUB-0015", "customer_id": "CUST-0015", "tier": "business", "monitor_limit": 100, "monitors_used": 40, "price_monthly": 299, "status": "active", "created_at": "2024-09-30", "next_billing_date": "2026-09-30", "trial_end_date": None, "cancelled_at": None, "failed_payment_count": 0, "payment_method_last4": "6678", "account_balance": "0.00", "discount_percent": "15.00", "discount_expires_at": "2026-12-30", "retention_offer_used": True},
    # CUST-0016: past_due, 3 failed payments — no credits, no discount
    {"subscription_id": "SUB-0016", "customer_id": "CUST-0016", "tier": "starter", "monitor_limit": 5, "monitors_used": 5, "price_monthly": 29, "status": "past_due", "created_at": "2025-08-25", "next_billing_date": "2026-08-18", "trial_end_date": None, "cancelled_at": None, "failed_payment_count": 3, "payment_method_last4": "7791", "account_balance": "0.00", "discount_percent": "0.00", "discount_expires_at": None, "retention_offer_used": False},
    {"subscription_id": "SUB-0017", "customer_id": "CUST-0017", "tier": "team", "monitor_limit": 25, "monitors_used": 9, "price_monthly": 99, "status": "active", "created_at": "2025-09-10", "next_billing_date": "2026-09-10", "trial_end_date": None, "cancelled_at": None, "failed_payment_count": 0, "payment_method_last4": "2203", "account_balance": "0.00", "discount_percent": "0.00", "discount_expires_at": None, "retention_offer_used": False},
    {"subscription_id": "SUB-0018", "customer_id": "CUST-0018", "tier": "starter", "monitor_limit": 5, "monitors_used": 0, "price_monthly": 29, "status": "cancelled", "created_at": "2024-07-18", "next_billing_date": None, "trial_end_date": None, "cancelled_at": "2026-06-01", "failed_payment_count": 0, "payment_method_last4": "4450", "account_balance": "0.00", "discount_percent": "0.00", "discount_expires_at": None, "retention_offer_used": False},
    {"subscription_id": "SUB-0019", "customer_id": "CUST-0019", "tier": "team", "monitor_limit": 25, "monitors_used": 25, "price_monthly": 99, "status": "active", "created_at": "2025-10-05", "next_billing_date": "2026-09-05", "trial_end_date": None, "cancelled_at": None, "failed_payment_count": 0, "payment_method_last4": "8812", "account_balance": "0.00", "discount_percent": "0.00", "discount_expires_at": None, "retention_offer_used": False},
    {"subscription_id": "SUB-0020", "customer_id": "CUST-0020", "tier": "starter", "monitor_limit": 5, "monitors_used": 1, "price_monthly": 29, "status": "trialing", "created_at": "2026-08-10", "next_billing_date": "2026-08-24", "trial_end_date": "2026-08-24", "cancelled_at": None, "failed_payment_count": 0, "payment_method_last4": "3367", "account_balance": "0.00", "discount_percent": "0.00", "discount_expires_at": None, "retention_offer_used": False},
    {"subscription_id": "SUB-0021", "customer_id": "CUST-0021", "tier": "team", "monitor_limit": 25, "monitors_used": 17, "price_monthly": 99, "status": "active", "created_at": "2025-11-12", "next_billing_date": "2026-09-12", "trial_end_date": None, "cancelled_at": None, "failed_payment_count": 0, "payment_method_last4": "5529", "account_balance": "0.00", "discount_percent": "0.00", "discount_expires_at": None, "retention_offer_used": False},
    {"subscription_id": "SUB-0022", "customer_id": "CUST-0022", "tier": "starter", "monitor_limit": 5, "monitors_used": 2, "price_monthly": 29, "status": "active", "created_at": "2025-12-01", "next_billing_date": "2026-09-01", "trial_end_date": None, "cancelled_at": None, "failed_payment_count": 0, "payment_method_last4": "9013", "account_balance": "0.00", "discount_percent": "0.00", "discount_expires_at": None, "retention_offer_used": False},
    # CUST-0023: past_due — small goodwill credit applied while card situation is sorted
    {"subscription_id": "SUB-0023", "customer_id": "CUST-0023", "tier": "team", "monitor_limit": 25, "monitors_used": 24, "price_monthly": 99, "status": "past_due", "created_at": "2025-02-20", "next_billing_date": "2026-08-20", "trial_end_date": None, "cancelled_at": None, "failed_payment_count": 1, "payment_method_last4": "6650", "account_balance": "10.00", "discount_percent": "0.00", "discount_expires_at": None, "retention_offer_used": False},
    {"subscription_id": "SUB-0024", "customer_id": "CUST-0024", "tier": "starter", "monitor_limit": 5, "monitors_used": 4, "price_monthly": 29, "status": "active", "created_at": "2026-01-15", "next_billing_date": "2026-09-15", "trial_end_date": None, "cancelled_at": None, "failed_payment_count": 0, "payment_method_last4": "1147", "account_balance": "0.00", "discount_percent": "0.00", "discount_expires_at": None, "retention_offer_used": False},
    {"subscription_id": "SUB-0025", "customer_id": "CUST-0025", "tier": "starter", "monitor_limit": 5, "monitors_used": 0, "price_monthly": 29, "status": "cancelled", "created_at": "2024-06-05", "next_billing_date": None, "trial_end_date": None, "cancelled_at": "2026-07-10", "failed_payment_count": 0, "payment_method_last4": "2298", "account_balance": "0.00", "discount_percent": "0.00", "discount_expires_at": None, "retention_offer_used": False},
]

# ---------------------------------------------------------------------------
# Tickets (55 total: 16 billing / 20 technical / 12 refund / 7 other)
# ---------------------------------------------------------------------------

TICKETS = [
    # --- billing (16) ---
    {"ticket_id": "TICK-0001", "customer_id": "CUST-0005", "category": "billing", "subtype": "failed_payment", "subject": "Card declined - need help", "message": "Hi, I just got a notice that our card was declined for this month's Pulsecheck bill. Can you tell me why, and how do I update our payment method? We don't want our monitors to go down.", "status": "open", "created_at": "2026-08-10", "resolved_at": None, "resolution_notes": None},
    {"ticket_id": "TICK-0002", "customer_id": "CUST-0012", "category": "billing", "subtype": "failed_payment", "subject": "Payment failed again", "message": "This is the second time our subscription payment has failed even though the card on file should be valid. Can someone check what's going wrong on your end before we get suspended?", "status": "escalated", "created_at": "2026-08-15", "resolved_at": None, "resolution_notes": "Escalated: repeated payment failure needs manual account review before service is interrupted."},
    {"ticket_id": "TICK-0003", "customer_id": "CUST-0016", "category": "billing", "subtype": "failed_payment", "subject": "Account at risk of suspension", "message": "We've had three failed charges now and I'm worried our monitors are going to get disabled. Our finance team says the card is fine, so I think it might be something on your side. Please help ASAP.", "status": "escalated", "created_at": "2026-08-19", "resolved_at": None, "resolution_notes": "Escalated: third consecutive failed payment; flagged for manual billing review."},
    {"ticket_id": "TICK-0004", "customer_id": "CUST-0023", "category": "billing", "subtype": "failed_payment", "subject": "Failed payment notification", "message": "Got an email saying our payment didn't go through. I think our card just expired last week - how do I update it and retry the charge?", "status": "open", "created_at": "2026-08-21", "resolved_at": None, "resolution_notes": None},
    {"ticket_id": "TICK-0005", "customer_id": "CUST-0002", "category": "billing", "subtype": "plan_upgrade", "subject": "Need more monitors", "message": "We're bumping up against our 25 monitor limit on the Team plan. What does it look like to move to Business, and will we be charged the difference right away or at renewal?", "status": "resolved", "created_at": "2026-07-02", "resolved_at": "2026-07-03", "resolution_notes": "Walked customer through Team to Business upgrade; prorated charge applied at next invoice."},
    {"ticket_id": "TICK-0006", "customer_id": "CUST-0009", "category": "billing", "subtype": "plan_upgrade", "subject": "Approaching monitor limit", "message": "We're at 91 of 100 monitors on Business. Is there a tier above this, or can we add extra monitors a la carte instead of jumping to a whole new plan?", "status": "resolved", "created_at": "2026-08-05", "resolved_at": "2026-08-06", "resolution_notes": "Explained Business is the top tier; recommended add-on monitor packs instead of a new plan."},
    {"ticket_id": "TICK-0007", "customer_id": "CUST-0019", "category": "billing", "subtype": "plan_upgrade", "subject": "At our monitor cap", "message": "We just hit 25/25 monitors on the Team plan and need to add two more endpoints today. Can you upgrade us now and prorate the cost?", "status": "resolved", "created_at": "2026-08-22", "resolved_at": "2026-08-22", "resolution_notes": "Upgraded to Business same-day with prorated charge for the remaining cycle."},
    {"ticket_id": "TICK-0008", "customer_id": "CUST-0006", "category": "billing", "subtype": "plan_downgrade", "subject": "Downgrading from Business to Team", "message": "We've consolidated a lot of our services and only need about 20 monitors now. Can we move down to the Team plan, and will we get any credit back for the difference?", "status": "resolved", "created_at": "2026-06-18", "resolved_at": "2026-06-19", "resolution_notes": "Processed downgrade effective next cycle; prorated credit applied to next invoice."},
    {"ticket_id": "TICK-0009", "customer_id": "CUST-0015", "category": "billing", "subtype": "plan_downgrade", "subject": "Considering a smaller plan", "message": "We're only using 40 of our 100 monitors on Business. Does it make sense to move to Team, and how does the proration work if we switch mid-cycle?", "status": "open", "created_at": "2026-08-12", "resolved_at": None, "resolution_notes": None},
    {"ticket_id": "TICK-0010", "customer_id": "CUST-0003", "category": "billing", "subtype": "proration", "subject": "Confused about last invoice", "message": "Our latest invoice has a partial credit line item I don't understand. We upgraded mid-month and I want to make sure we weren't double charged.", "status": "resolved", "created_at": "2026-05-30", "resolved_at": "2026-05-31", "resolution_notes": "Explained proration line item from mid-cycle upgrade; confirmed no double charge."},
    {"ticket_id": "TICK-0011", "customer_id": "CUST-0008", "category": "billing", "subtype": "proration", "subject": "Proration math looks off", "message": "We downgraded from Business to Team on the 10th of last month but the invoice doesn't seem to reflect a prorated credit. Can someone double check the numbers?", "status": "resolved", "created_at": "2026-07-14", "resolved_at": "2026-07-16", "resolution_notes": "Found a delayed credit; applied manually and confirmed corrected balance with customer."},
    {"ticket_id": "TICK-0012", "customer_id": "CUST-0021", "category": "billing", "subtype": "proration", "subject": "Mid-cycle upgrade charge", "message": "We upgraded from Starter to Team a couple weeks into the billing cycle. Just want to confirm we're only being charged for the remaining days, not a full new month.", "status": "resolved", "created_at": "2026-08-01", "resolved_at": "2026-08-01", "resolution_notes": "Confirmed the charge only covers remaining days in the cycle."},
    {"ticket_id": "TICK-0013", "customer_id": "CUST-0004", "category": "billing", "subtype": "invoice_question", "subject": "Need invoice for accounting", "message": "Can someone send over a copy of our most recent invoice as a PDF? Our accounting team needs it for expense reporting.", "status": "resolved", "created_at": "2026-07-20", "resolved_at": "2026-07-20", "resolution_notes": "Sent PDF copy of latest invoice."},
    {"ticket_id": "TICK-0014", "customer_id": "CUST-0017", "category": "billing", "subtype": "invoice_question", "subject": "Tax info on invoice", "message": "Our invoices don't show a VAT breakdown and our finance team needs that for filing. Is there a way to get that added?", "status": "open", "created_at": "2026-08-18", "resolved_at": None, "resolution_notes": None},
    {"ticket_id": "TICK-0015", "customer_id": "CUST-0011", "category": "billing", "subtype": "payment_method_update", "subject": "Updating our card", "message": "Our old company card is being cancelled next week. How do I swap in a new card before our next billing date?", "status": "resolved", "created_at": "2026-08-16", "resolved_at": "2026-08-16", "resolution_notes": "Sent hosted payment page link; customer updated card successfully."},
    {"ticket_id": "TICK-0016", "customer_id": "CUST-0024", "category": "billing", "subtype": "payment_method_update", "subject": "Switch to a different payment method", "message": "We want to move from a credit card to ACH/bank transfer if that's supported. Is that something Pulsecheck offers?", "status": "open", "created_at": "2026-08-23", "resolved_at": None, "resolution_notes": None},

    # --- technical (20) ---
    {"ticket_id": "TICK-0017", "customer_id": "CUST-0001", "category": "technical", "subtype": "false_positive_alert", "subject": "Getting alerts for a site that's clearly up", "message": "We got a downtime alert for our main API at 3am but the endpoint was up the whole time based on our own logs. Is something wrong with the check?", "status": "resolved", "created_at": "2026-08-09", "resolved_at": "2026-08-11", "resolution_notes": "Matched known incident INC-004 (DNS resolver flapping); no action needed on customer's end."},
    {"ticket_id": "TICK-0018", "customer_id": "CUST-0007", "category": "technical", "subtype": "false_positive_alert", "subject": "False downtime alert overnight", "message": "Same as a few other people I've seen mention - we got paged for downtime last night but nothing was actually wrong. Is this a known issue?", "status": "resolved", "created_at": "2026-08-10", "resolved_at": "2026-08-11", "resolution_notes": "Confirmed as part of INC-004; resolved upstream."},
    {"ticket_id": "TICK-0019", "customer_id": "CUST-0013", "category": "technical", "subtype": "false_positive_alert", "subject": "Alert fired but site was fine", "message": "Our status page monitor triggered an alert for 2 minutes of downtime, but nothing shows in our own server logs. Can you check what happened?", "status": "resolved", "created_at": "2026-08-11", "resolved_at": "2026-08-11", "resolution_notes": "Matched INC-004; resolved same day as root cause fix."},
    {"ticket_id": "TICK-0020", "customer_id": "CUST-0022", "category": "technical", "subtype": "false_positive_alert", "subject": "Random downtime alert", "message": "We got a single downtime ping in the middle of the night for one of our endpoints. Everything looks fine now, and I don't see anything in our infra logs either.", "status": "resolved", "created_at": "2026-08-12", "resolved_at": "2026-08-12", "resolution_notes": "Trailing alert from the INC-004 window; confirmed monitor healthy."},
    {"ticket_id": "TICK-0021", "customer_id": "CUST-0002", "category": "technical", "subtype": "false_positive_alert", "subject": "Multiple false alerts this week", "message": "We've had three false-positive downtime alerts in the last five days, all resolving themselves within a minute or two. It's starting to cause alert fatigue on our team.", "status": "escalated", "created_at": "2026-08-17", "resolved_at": None, "resolution_notes": "Pattern doesn't match a known incident; escalated to engineering to investigate possible new check flakiness."},
    {"ticket_id": "TICK-0022", "customer_id": "CUST-0014", "category": "technical", "subtype": "false_positive_alert", "subject": "Flaky alert on one endpoint", "message": "One specific monitor keeps flapping between up and down every few hours even though the endpoint hasn't changed. Can you take a look at the check config?", "status": "open", "created_at": "2026-08-20", "resolved_at": None, "resolution_notes": None},
    {"ticket_id": "TICK-0023", "customer_id": "CUST-0011", "category": "technical", "subtype": "webhook_slack_integration", "subject": "Slack alerts stopped coming through", "message": "Our #alerts Slack channel hasn't gotten a single notification in two days, even though I can see incidents logged in the Pulsecheck dashboard.", "status": "resolved", "created_at": "2026-08-08", "resolved_at": "2026-08-09", "resolution_notes": "Matched known incident INC-002 (us-east-1 delivery backlog); resolved."},
    {"ticket_id": "TICK-0024", "customer_id": "CUST-0017", "category": "technical", "subtype": "webhook_slack_integration", "subject": "Webhook not firing", "message": "We set up a custom webhook a week ago and it's never once fired, even during a real outage yesterday. Is there a way to test it?", "status": "open", "created_at": "2026-08-19", "resolved_at": None, "resolution_notes": None},
    {"ticket_id": "TICK-0025", "customer_id": "CUST-0009", "category": "technical", "subtype": "webhook_slack_integration", "subject": "Delayed Slack notifications", "message": "Alerts are showing up in Slack but sometimes 20-30 minutes late, which kind of defeats the purpose. Is this a known delay somewhere?", "status": "resolved", "created_at": "2026-08-07", "resolved_at": "2026-08-09", "resolution_notes": "Matched INC-002; delivery delays resolved."},
    {"ticket_id": "TICK-0026", "customer_id": "CUST-0019", "category": "technical", "subtype": "webhook_slack_integration", "subject": "PagerDuty sending duplicate pages", "message": "We're getting paged twice for every single incident through the PagerDuty integration. It's waking people up unnecessarily.", "status": "escalated", "created_at": "2026-08-21", "resolved_at": None, "resolution_notes": "Matches open incident INC-007 (duplicate PagerDuty pages); escalated, no fix yet."},
    {"ticket_id": "TICK-0027", "customer_id": "CUST-0021", "category": "technical", "subtype": "webhook_slack_integration", "subject": "Reconnecting Slack integration", "message": "We rotated our Slack workspace and now none of our old webhook alerts work. What's the process to reconnect?", "status": "resolved", "created_at": "2026-07-28", "resolved_at": "2026-07-28", "resolution_notes": "Walked customer through reconnecting Slack after the workspace migration."},
    {"ticket_id": "TICK-0028", "customer_id": "CUST-0004", "category": "technical", "subtype": "monitor_pending", "subject": "Monitor stuck in pending for hours", "message": "I added a new monitor for our staging API this morning and it's been sitting in 'pending' status for over four hours. Is that normal?", "status": "resolved", "created_at": "2026-08-13", "resolved_at": "2026-08-13", "resolution_notes": "Manually activated monitor per known issue INC-003 workaround."},
    {"ticket_id": "TICK-0029", "customer_id": "CUST-0024", "category": "technical", "subtype": "monitor_pending", "subject": "New monitor won't activate", "message": "Same issue as I think others have had - a monitor I just created won't move out of pending no matter how long I wait.", "status": "open", "created_at": "2026-08-22", "resolved_at": None, "resolution_notes": None},
    {"ticket_id": "TICK-0030", "customer_id": "CUST-0001", "category": "technical", "subtype": "monitor_pending", "subject": "Pending monitor blocking our setup", "message": "We're trying to finish onboarding two new endpoints but one of them has been stuck in pending since yesterday. Can someone push it through manually?", "status": "resolved", "created_at": "2026-08-14", "resolved_at": "2026-08-14", "resolution_notes": "Manually pushed monitor out of pending; logged as another INC-003 occurrence."},
    {"ticket_id": "TICK-0031", "customer_id": "CUST-0003", "category": "technical", "subtype": "ssl_cert_false_failure", "subject": "SSL check failing on a valid cert", "message": "Pulsecheck is flagging our SSL cert as invalid but every other checker (including the browser) says it's fine and not expiring for months. What's going on?", "status": "resolved", "created_at": "2026-08-06", "resolved_at": "2026-08-07", "resolution_notes": "Matched INC-001 (stale intermediate cert bundle); resolved."},
    {"ticket_id": "TICK-0032", "customer_id": "CUST-0015", "category": "technical", "subtype": "ssl_cert_false_failure", "subject": "False SSL expiry warning", "message": "We got an SSL expiration warning for a cert that was just renewed last week. Seems like the check might be looking at cached data.", "status": "resolved", "created_at": "2026-08-09", "resolved_at": "2026-08-09", "resolution_notes": "Confirmed part of INC-001; check re-ran successfully after the fix."},
    {"ticket_id": "TICK-0033", "customer_id": "CUST-0008", "category": "technical", "subtype": "ssl_cert_false_failure", "subject": "Cert check failing intermittently", "message": "Our SSL monitor passes about half the time and fails the other half, for the exact same certificate. Nothing has changed on our end.", "status": "open", "created_at": "2026-08-23", "resolved_at": None, "resolution_notes": None},
    {"ticket_id": "TICK-0034", "customer_id": "CUST-0006", "category": "technical", "subtype": "api_rate_limit", "subject": "Hitting rate limits on your API", "message": "We're getting 429 errors when creating monitors in bulk through your API. What's the actual rate limit and is there a way to get it raised for a Business account?", "status": "resolved", "created_at": "2026-08-04", "resolved_at": "2026-08-05", "resolution_notes": "Matched INC-005 (misapplied rate tier); Business limits restored."},
    {"ticket_id": "TICK-0035", "customer_id": "CUST-0009", "category": "technical", "subtype": "api_rate_limit", "subject": "Rate limited during migration", "message": "We're migrating a few hundred endpoints into Pulsecheck via the API and keep getting rate limited partway through. Any way to get a temporary bump?", "status": "resolved", "created_at": "2026-08-15", "resolved_at": "2026-08-15", "resolution_notes": "Applied a temporary rate limit increase during the migration window."},
    {"ticket_id": "TICK-0036", "customer_id": "CUST-0014", "category": "technical", "subtype": "api_rate_limit", "subject": "429 errors on status endpoint", "message": "Our internal dashboard polls your GET /monitors endpoint every 10 seconds and started getting 429s today. Did the rate limit change recently?", "status": "open", "created_at": "2026-08-24", "resolved_at": None, "resolution_notes": None},

    # --- refund (12) ---
    {"ticket_id": "TICK-0037", "customer_id": "CUST-0018", "category": "refund", "subtype": "refund_bad_onboarding", "subject": "Onboarding was a mess, want a refund", "message": "We signed up last month but never got our monitors set up correctly, and support was slow to help. We'd like a refund for the month since we basically got no value from the product.", "status": "resolved", "created_at": "2026-05-28", "resolved_at": "2026-05-29", "resolution_notes": "Full refund of $29 issued for the cycle; subscription cancelled per customer request."},
    {"ticket_id": "TICK-0038", "customer_id": "CUST-0025", "category": "refund", "subtype": "refund_bad_onboarding", "subject": "Requesting refund - rough start", "message": "Honestly our first two weeks were spent fighting with the Slack integration instead of actually monitoring anything. We'd like our money back for this billing cycle.", "status": "resolved", "created_at": "2026-07-05", "resolved_at": "2026-07-06", "resolution_notes": "Refund issued for the billing cycle; subscription cancelled."},
    {"ticket_id": "TICK-0039", "customer_id": "CUST-0022", "category": "refund", "subtype": "refund_bad_onboarding", "subject": "Refund for setup issues", "message": "We had a rough first week where none of our monitors were reporting correctly, so we barely got to use the product we paid for. Can we get a partial refund?", "status": "resolved", "created_at": "2026-06-10", "resolved_at": "2026-06-11", "resolution_notes": "Partial refund issued as a goodwill credit; subscription kept active."},
    {"ticket_id": "TICK-0040", "customer_id": "CUST-0010", "category": "refund", "subtype": "trial_cancel_refund", "subject": "Cancel before trial ends", "message": "We're still in our trial period and decided Pulsecheck isn't the right fit for our team right now. Can you confirm we won't be charged when the trial ends?", "status": "resolved", "created_at": "2026-08-24", "resolved_at": "2026-08-24", "resolution_notes": "Trial cancelled before conversion; confirmed no charge will occur."},
    {"ticket_id": "TICK-0041", "customer_id": "CUST-0020", "category": "refund", "subtype": "trial_cancel_refund", "subject": "Trial just ended, please don't charge us", "message": "I think our trial ended yesterday and I completely forgot to cancel. We don't want to move forward - can you cancel now and make sure we're not charged?", "status": "open", "created_at": "2026-08-25", "resolved_at": None, "resolution_notes": None},
    {"ticket_id": "TICK-0042", "customer_id": "CUST-0007", "category": "refund", "subtype": "trial_cancel_refund", "subject": "Charged after trial, want refund", "message": "I was sure we cancelled during the trial but we just got charged $29. Can you check on your end and refund us if the cancellation didn't go through?", "status": "escalated", "created_at": "2026-08-05", "resolved_at": None, "resolution_notes": "Cancellation-before-charge dispute; escalated to confirm whether the trial cancellation was logged correctly before refunding."},
    {"ticket_id": "TICK-0043", "customer_id": "CUST-0006", "category": "refund", "subtype": "downgrade_prorated_refund", "subject": "Refund after downgrade", "message": "We downgraded from Business to Team last week and were told we'd get a prorated credit for the unused Business time, but I don't see it on our account yet.", "status": "resolved", "created_at": "2026-08-11", "resolved_at": "2026-08-12", "resolution_notes": "Located the missing prorated credit and issued it manually."},
    {"ticket_id": "TICK-0044", "customer_id": "CUST-0015", "category": "refund", "subtype": "downgrade_prorated_refund", "subject": "Prorated refund for downgrade", "message": "Following up on our downgrade from last month - we were expecting a partial refund for the difference and haven't seen anything hit our card yet.", "status": "open", "created_at": "2026-08-19", "resolved_at": None, "resolution_notes": None},
    {"ticket_id": "TICK-0045", "customer_id": "CUST-0012", "category": "refund", "subtype": "cancellation", "subject": "Want to cancel our account", "message": "Between the recent billing issues and a shrinking team, we'd like to cancel our Pulsecheck subscription entirely. Please confirm once it's done.", "status": "escalated", "created_at": "2026-08-16", "resolved_at": None, "resolution_notes": "Cancellation requested while account is past due; escalated to resolve the outstanding balance before closing the account."},
    {"ticket_id": "TICK-0046", "customer_id": "CUST-0016", "category": "refund", "subtype": "cancellation", "subject": "Cancelling due to repeated billing problems", "message": "We've had three failed payments in a row now and honestly it's been more hassle than it's worth. We'd like to cancel and would appreciate a refund for this last partial cycle.", "status": "escalated", "created_at": "2026-08-20", "resolved_at": None, "resolution_notes": "Cancellation plus refund request exceeds the auto-approval threshold; escalated for human review."},
    {"ticket_id": "TICK-0047", "customer_id": "CUST-0023", "category": "refund", "subtype": "cancellation", "subject": "Cancel subscription", "message": "We're switching to an in-house monitoring solution and want to cancel our plan. Is there a refund for the unused part of this month?", "status": "open", "created_at": "2026-08-22", "resolved_at": None, "resolution_notes": None},
    {"ticket_id": "TICK-0048", "customer_id": "CUST-0019", "category": "refund", "subtype": "cancellation", "subject": "Downsizing, need to cancel", "message": "Our company is downsizing and we need to cancel Pulsecheck effective immediately. Can you also let me know if any of this month's payment is refundable?", "status": "open", "created_at": "2026-08-23", "resolved_at": None, "resolution_notes": None},

    # --- other (7) ---
    {"ticket_id": "TICK-0049", "customer_id": "CUST-0002", "category": "other", "subtype": "feature_request", "subject": "Feature request: multi-region checks", "message": "Would love the ability to run the same monitor from multiple regions at once to catch region-specific outages. Is this on the roadmap?", "status": "open", "created_at": "2026-07-25", "resolved_at": None, "resolution_notes": None},
    {"ticket_id": "TICK-0050", "customer_id": "CUST-0014", "category": "other", "subtype": "feature_request", "subject": "Request: status page customization", "message": "Any plans to let us customize the branding and domain on the public status page? Right now it just shows the default Pulsecheck styling.", "status": "open", "created_at": "2026-08-02", "resolved_at": None, "resolution_notes": None},
    {"ticket_id": "TICK-0051", "customer_id": "CUST-0021", "category": "other", "subtype": "account_access", "subject": "Can't invite teammate", "message": "I'm trying to invite a new engineer to our workspace but the invite email never seems to arrive. Tried twice with two different email addresses.", "status": "resolved", "created_at": "2026-08-13", "resolved_at": "2026-08-13", "resolution_notes": "Found invite emails were being caught by the customer's spam filter; sent a direct link instead."},
    {"ticket_id": "TICK-0052", "customer_id": "CUST-0003", "category": "other", "subtype": "account_access", "subject": "Locked out of admin account", "message": "Our account owner left the company and nobody else has admin access to change billing or monitors. How do we get ownership transferred?", "status": "escalated", "created_at": "2026-08-18", "resolved_at": None, "resolution_notes": "Account ownership transfer requires identity verification; escalated for manual handling."},
    {"ticket_id": "TICK-0053", "customer_id": "CUST-0017", "category": "other", "subtype": "account_access", "subject": "SSO login broken", "message": "We use Google SSO to log in and it's been throwing an error for the last day. Regular email/password login still seems to work fine though.", "status": "open", "created_at": "2026-08-24", "resolved_at": None, "resolution_notes": None},
    {"ticket_id": "TICK-0054", "customer_id": "CUST-0005", "category": "other", "subtype": "unclear", "subject": "Question about our account", "message": "Hey, just wanted to check in on a few things with our account when someone gets a chance. Not urgent.", "status": "open", "created_at": "2026-08-21", "resolved_at": None, "resolution_notes": None},
    {"ticket_id": "TICK-0055", "customer_id": "CUST-0011", "category": "other", "subtype": "unclear", "subject": "Quick question", "message": "Do you all support monitoring for internal/private endpoints that aren't publicly accessible, or only public URLs?", "status": "resolved", "created_at": "2026-07-30", "resolved_at": "2026-07-30", "resolution_notes": "Confirmed Pulsecheck supports private/internal endpoints via an agent-based check; sent setup docs."},
]

# ---------------------------------------------------------------------------
# Known incidents (technical agent checks this before treating an alert as novel)
# ---------------------------------------------------------------------------

KNOWN_INCIDENTS = [
    {
        "incident_id": "INC-001",
        "title": "SSL certificate checks failing for valid Let's Encrypt certs",
        "description": "A subset of SSL monitors were flagging valid, non-expiring certificates as failed. Impacted checks used Let's Encrypt intermediate certificates issued after a routine CA chain update.",
        "affected_component": "ssl_cert_check",
        "status": "resolved",
        "started_at": "2026-08-04",
        "resolved_at": "2026-08-07",
        "root_cause": "Our SSL validation service was using a stale intermediate certificate bundle that didn't include a newly rotated Let's Encrypt chain.",
        "customer_facing_note": "This was a known issue (INC-001) affecting SSL checks on certain Let's Encrypt certificates between Aug 4-7. It's fully resolved - no action needed on your end.",
    },
    {
        "incident_id": "INC-002",
        "title": "Delayed Slack webhook delivery in us-east-1",
        "description": "Slack notifications for triggered alerts were delayed by 15-40 minutes for accounts routed through our us-east-1 notification workers.",
        "affected_component": "slack_webhook",
        "status": "resolved",
        "started_at": "2026-08-06",
        "resolved_at": "2026-08-09",
        "root_cause": "A backlog in the us-east-1 notification queue caused by an undersized worker pool during a traffic spike.",
        "customer_facing_note": "This was a known issue (INC-002) causing delayed Slack alerts Aug 6-9. It's resolved and delivery times are back to normal.",
    },
    {
        "incident_id": "INC-003",
        "title": "New monitors intermittently stuck in 'pending' status",
        "description": "A small percentage of newly created monitors fail to transition out of 'pending' and require a manual nudge from the checker fleet.",
        "affected_component": "monitor_provisioning",
        "status": "monitoring",
        "started_at": "2026-08-10",
        "resolved_at": None,
        "root_cause": "Suspected race condition in monitor provisioning when checker fleet capacity is reassigned; under investigation.",
        "customer_facing_note": "We're aware of an intermittent issue (INC-003) where new monitors can get stuck in 'pending.' Our team can manually activate affected monitors - flag the monitor ID and we'll fix it right away while we finish the permanent fix.",
    },
    {
        "incident_id": "INC-004",
        "title": "False-positive downtime alerts from DNS resolver flapping",
        "description": "One of our upstream DNS resolvers was intermittently failing to resolve customer domains, triggering false downtime alerts even though target endpoints were healthy.",
        "affected_component": "uptime_check_dns",
        "status": "resolved",
        "started_at": "2026-08-08",
        "resolved_at": "2026-08-11",
        "root_cause": "Upstream third-party DNS resolver had an intermittent regional outage; we've since added a secondary resolver with automatic failover.",
        "customer_facing_note": "This matches a known issue (INC-004): brief false-positive downtime alerts caused by a DNS resolver problem between Aug 8-11. Resolved, and we've added redundancy to prevent a repeat.",
    },
    {
        "incident_id": "INC-005",
        "title": "429 rate limit errors on bulk monitor creation",
        "description": "Business-tier accounts creating monitors in bulk via the API were hitting rate limits well below the documented threshold.",
        "affected_component": "api_rate_limit",
        "status": "resolved",
        "started_at": "2026-08-02",
        "resolved_at": "2026-08-05",
        "root_cause": "A misconfigured rate limit tier was applied to Business accounts after a recent API gateway deploy, capping them at Team-tier limits.",
        "customer_facing_note": "This was a known issue (INC-005): Business-tier accounts were incorrectly rate-limited at Team-tier levels Aug 2-5. Fixed - Business accounts now get their full documented limit.",
    },
    {
        "incident_id": "INC-006",
        "title": "Delayed email alerts during SendGrid outage",
        "description": "Email-based alert delivery was delayed by up to an hour during an upstream SendGrid outage.",
        "affected_component": "email_alerts",
        "status": "resolved",
        "started_at": "2026-07-21",
        "resolved_at": "2026-07-21",
        "root_cause": "Third-party email provider (SendGrid) had a multi-hour regional outage affecting outbound delivery.",
        "customer_facing_note": "This was caused by a short outage at our email provider on Jul 21 (INC-006). Fully resolved - Slack and PagerDuty alerts were not affected.",
    },
    {
        "incident_id": "INC-007",
        "title": "Duplicate alerts sent through PagerDuty integration",
        "description": "Some accounts using the PagerDuty integration are receiving two pages for a single incident.",
        "affected_component": "pagerduty_integration",
        "status": "open",
        "started_at": "2026-08-19",
        "resolved_at": None,
        "root_cause": "Suspected duplicate event dispatch when an incident is re-evaluated by the checker fleet before the first alert acknowledges; under investigation.",
        "customer_facing_note": "We're actively investigating duplicate PagerDuty pages (INC-007) reported starting Aug 19. No fix yet - we recommend acknowledging the first page and disregarding immediate duplicates while we work on it.",
    },
]


# ---------------------------------------------------------------------------
# Invoices (historical billing records — one or two per active customer)
# Fields: invoice_id, customer_id, subscription_id, amount, currency,
#         status (paid | unpaid | failed | void), invoice_date, due_date, paid_at, failure_reason
# ---------------------------------------------------------------------------

INVOICES = [
    # CUST-0001 — Starter, paid up to date
    {"invoice_id": "INV-0001", "customer_id": "CUST-0001", "subscription_id": "SUB-0001", "amount": "29.00", "currency": "USD", "status": "paid", "invoice_date": "2026-08-12", "due_date": "2026-08-12", "paid_at": "2026-08-12", "failure_reason": None},
    {"invoice_id": "INV-0002", "customer_id": "CUST-0001", "subscription_id": "SUB-0001", "amount": "29.00", "currency": "USD", "status": "paid", "invoice_date": "2026-07-12", "due_date": "2026-07-12", "paid_at": "2026-07-12", "failure_reason": None},
    # CUST-0002 — Team, paid up to date
    {"invoice_id": "INV-0003", "customer_id": "CUST-0002", "subscription_id": "SUB-0002", "amount": "99.00", "currency": "USD", "status": "paid", "invoice_date": "2026-08-03", "due_date": "2026-08-03", "paid_at": "2026-08-03", "failure_reason": None},
    {"invoice_id": "INV-0004", "customer_id": "CUST-0002", "subscription_id": "SUB-0002", "amount": "99.00", "currency": "USD", "status": "paid", "invoice_date": "2026-07-03", "due_date": "2026-07-03", "paid_at": "2026-07-03", "failure_reason": None},
    # CUST-0003 — Business, paid. Includes a proration line from TICK-0010 mid-cycle upgrade
    {"invoice_id": "INV-0005", "customer_id": "CUST-0003", "subscription_id": "SUB-0003", "amount": "299.00", "currency": "USD", "status": "paid", "invoice_date": "2026-08-20", "due_date": "2026-08-20", "paid_at": "2026-08-20", "failure_reason": None},
    {"invoice_id": "INV-0006", "customer_id": "CUST-0003", "subscription_id": "SUB-0003", "amount": "152.19", "currency": "USD", "status": "paid", "invoice_date": "2026-05-20", "due_date": "2026-05-20", "paid_at": "2026-05-20", "failure_reason": None},
    # CUST-0004 — Starter, paid
    {"invoice_id": "INV-0007", "customer_id": "CUST-0004", "subscription_id": "SUB-0004", "amount": "29.00", "currency": "USD", "status": "paid", "invoice_date": "2026-08-15", "due_date": "2026-08-15", "paid_at": "2026-08-15", "failure_reason": None},
    # CUST-0005 — Team, past_due: most recent invoice failed twice
    {"invoice_id": "INV-0008", "customer_id": "CUST-0005", "subscription_id": "SUB-0005", "amount": "99.00", "currency": "USD", "status": "failed", "invoice_date": "2026-08-09", "due_date": "2026-08-09", "paid_at": None, "failure_reason": "Card declined: insufficient funds"},
    {"invoice_id": "INV-0009", "customer_id": "CUST-0005", "subscription_id": "SUB-0005", "amount": "99.00", "currency": "USD", "status": "failed", "invoice_date": "2026-07-09", "due_date": "2026-07-09", "paid_at": None, "failure_reason": "Card declined: do not honor"},
    {"invoice_id": "INV-0010", "customer_id": "CUST-0005", "subscription_id": "SUB-0005", "amount": "99.00", "currency": "USD", "status": "paid", "invoice_date": "2026-06-09", "due_date": "2026-06-09", "paid_at": "2026-06-09", "failure_reason": None},
    # CUST-0006 — Business, active; discount applied (see SUB-0006: 10% retention)
    {"invoice_id": "INV-0011", "customer_id": "CUST-0006", "subscription_id": "SUB-0006", "amount": "269.10", "currency": "USD", "status": "paid", "invoice_date": "2026-08-05", "due_date": "2026-08-05", "paid_at": "2026-08-05", "failure_reason": None},
    {"invoice_id": "INV-0012", "customer_id": "CUST-0006", "subscription_id": "SUB-0006", "amount": "299.00", "currency": "USD", "status": "paid", "invoice_date": "2026-07-05", "due_date": "2026-07-05", "paid_at": "2026-07-05", "failure_reason": None},
    # CUST-0007 — Starter, paid
    {"invoice_id": "INV-0013", "customer_id": "CUST-0007", "subscription_id": "SUB-0007", "amount": "29.00", "currency": "USD", "status": "paid", "invoice_date": "2026-08-22", "due_date": "2026-08-22", "paid_at": "2026-08-22", "failure_reason": None},
    # CUST-0008 — Team, paid; includes a downgrade prorated invoice from TICK-0011
    {"invoice_id": "INV-0014", "customer_id": "CUST-0008", "subscription_id": "SUB-0008", "amount": "99.00", "currency": "USD", "status": "paid", "invoice_date": "2026-08-11", "due_date": "2026-08-11", "paid_at": "2026-08-11", "failure_reason": None},
    {"invoice_id": "INV-0015", "customer_id": "CUST-0008", "subscription_id": "SUB-0008", "amount": "65.40", "currency": "USD", "status": "paid", "invoice_date": "2026-07-10", "due_date": "2026-07-10", "paid_at": "2026-07-16", "failure_reason": None},
    # CUST-0009 — Business, paid
    {"invoice_id": "INV-0016", "customer_id": "CUST-0009", "subscription_id": "SUB-0009", "amount": "299.00", "currency": "USD", "status": "paid", "invoice_date": "2026-08-01", "due_date": "2026-08-01", "paid_at": "2026-08-01", "failure_reason": None},
    {"invoice_id": "INV-0017", "customer_id": "CUST-0009", "subscription_id": "SUB-0009", "amount": "299.00", "currency": "USD", "status": "paid", "invoice_date": "2026-07-01", "due_date": "2026-07-01", "paid_at": "2026-07-01", "failure_reason": None},
    # CUST-0011 — Team, paid
    {"invoice_id": "INV-0018", "customer_id": "CUST-0011", "subscription_id": "SUB-0011", "amount": "99.00", "currency": "USD", "status": "paid", "invoice_date": "2026-08-19", "due_date": "2026-08-19", "paid_at": "2026-08-19", "failure_reason": None},
    # CUST-0012 — Business, past_due: one failed invoice
    {"invoice_id": "INV-0019", "customer_id": "CUST-0012", "subscription_id": "SUB-0012", "amount": "299.00", "currency": "USD", "status": "failed", "invoice_date": "2026-08-14", "due_date": "2026-08-14", "paid_at": None, "failure_reason": "Card declined: card expired"},
    {"invoice_id": "INV-0020", "customer_id": "CUST-0012", "subscription_id": "SUB-0012", "amount": "299.00", "currency": "USD", "status": "paid", "invoice_date": "2026-07-14", "due_date": "2026-07-14", "paid_at": "2026-07-14", "failure_reason": None},
    # CUST-0013 — Starter, paid
    {"invoice_id": "INV-0021", "customer_id": "CUST-0013", "subscription_id": "SUB-0013", "amount": "29.00", "currency": "USD", "status": "paid", "invoice_date": "2026-08-14", "due_date": "2026-08-14", "paid_at": "2026-08-14", "failure_reason": None},
    # CUST-0014 — Team, paid
    {"invoice_id": "INV-0022", "customer_id": "CUST-0014", "subscription_id": "SUB-0014", "amount": "99.00", "currency": "USD", "status": "paid", "invoice_date": "2026-08-02", "due_date": "2026-08-02", "paid_at": "2026-08-02", "failure_reason": None},
    # CUST-0015 — Business, discount active (15% retention), paid
    {"invoice_id": "INV-0023", "customer_id": "CUST-0015", "subscription_id": "SUB-0015", "amount": "254.15", "currency": "USD", "status": "paid", "invoice_date": "2026-08-30", "due_date": "2026-08-30", "paid_at": "2026-08-30", "failure_reason": None},
    {"invoice_id": "INV-0024", "customer_id": "CUST-0015", "subscription_id": "SUB-0015", "amount": "299.00", "currency": "USD", "status": "paid", "invoice_date": "2026-07-30", "due_date": "2026-07-30", "paid_at": "2026-07-30", "failure_reason": None},
    # CUST-0016 — Starter, 3 failed payments (past_due)
    {"invoice_id": "INV-0025", "customer_id": "CUST-0016", "subscription_id": "SUB-0016", "amount": "29.00", "currency": "USD", "status": "failed", "invoice_date": "2026-08-18", "due_date": "2026-08-18", "paid_at": None, "failure_reason": "Card declined: insufficient funds"},
    {"invoice_id": "INV-0026", "customer_id": "CUST-0016", "subscription_id": "SUB-0016", "amount": "29.00", "currency": "USD", "status": "failed", "invoice_date": "2026-07-25", "due_date": "2026-07-25", "paid_at": None, "failure_reason": "Card declined: do not honor"},
    {"invoice_id": "INV-0027", "customer_id": "CUST-0016", "subscription_id": "SUB-0016", "amount": "29.00", "currency": "USD", "status": "failed", "invoice_date": "2026-07-10", "due_date": "2026-07-10", "paid_at": None, "failure_reason": "Card declined: insufficient funds"},
    # CUST-0017 — Team, paid
    {"invoice_id": "INV-0028", "customer_id": "CUST-0017", "subscription_id": "SUB-0017", "amount": "99.00", "currency": "USD", "status": "paid", "invoice_date": "2026-08-10", "due_date": "2026-08-10", "paid_at": "2026-08-10", "failure_reason": None},
    # CUST-0018 — Starter, cancelled (void after cancellation)
    {"invoice_id": "INV-0029", "customer_id": "CUST-0018", "subscription_id": "SUB-0018", "amount": "29.00", "currency": "USD", "status": "void", "invoice_date": "2026-06-01", "due_date": "2026-06-01", "paid_at": None, "failure_reason": "Subscription cancelled; invoice voided"},
    # CUST-0019 — Team, paid
    {"invoice_id": "INV-0030", "customer_id": "CUST-0019", "subscription_id": "SUB-0019", "amount": "99.00", "currency": "USD", "status": "paid", "invoice_date": "2026-08-05", "due_date": "2026-08-05", "paid_at": "2026-08-05", "failure_reason": None},
    # CUST-0021 — Team, paid
    {"invoice_id": "INV-0031", "customer_id": "CUST-0021", "subscription_id": "SUB-0021", "amount": "99.00", "currency": "USD", "status": "paid", "invoice_date": "2026-08-12", "due_date": "2026-08-12", "paid_at": "2026-08-12", "failure_reason": None},
    # CUST-0022 — Starter, paid
    {"invoice_id": "INV-0032", "customer_id": "CUST-0022", "subscription_id": "SUB-0022", "amount": "29.00", "currency": "USD", "status": "paid", "invoice_date": "2026-08-01", "due_date": "2026-08-01", "paid_at": "2026-08-01", "failure_reason": None},
    # CUST-0023 — Team, past_due: one failed invoice, one paid
    {"invoice_id": "INV-0033", "customer_id": "CUST-0023", "subscription_id": "SUB-0023", "amount": "99.00", "currency": "USD", "status": "failed", "invoice_date": "2026-08-20", "due_date": "2026-08-20", "paid_at": None, "failure_reason": "Card declined: card expired"},
    {"invoice_id": "INV-0034", "customer_id": "CUST-0023", "subscription_id": "SUB-0023", "amount": "99.00", "currency": "USD", "status": "paid", "invoice_date": "2026-07-20", "due_date": "2026-07-20", "paid_at": "2026-07-20", "failure_reason": None},
    # CUST-0024 — Starter, paid
    {"invoice_id": "INV-0035", "customer_id": "CUST-0024", "subscription_id": "SUB-0024", "amount": "29.00", "currency": "USD", "status": "paid", "invoice_date": "2026-08-15", "due_date": "2026-08-15", "paid_at": "2026-08-15", "failure_reason": None},
    # CUST-0025 — Starter, cancelled; last invoice paid before cancel
    {"invoice_id": "INV-0036", "customer_id": "CUST-0025", "subscription_id": "SUB-0025", "amount": "29.00", "currency": "USD", "status": "paid", "invoice_date": "2026-07-05", "due_date": "2026-07-05", "paid_at": "2026-07-05", "failure_reason": None},
]

# ---------------------------------------------------------------------------
# Refunds  (matching resolved/escalated refund tickets in TICKETS above)
# Fields: refund_id, customer_id, ticket_id, amount, currency, reason,
#         status (approved | pending_review | rejected), created_at, processed_at, notes
# $100 threshold: >=100 -> pending_review (server-enforced); <$100 -> approved
# ---------------------------------------------------------------------------

REFUNDS = [
    # TICK-0037 — CUST-0018 bad onboarding, $29 full refund, auto-approved
    {"refund_id": "REF-0001", "customer_id": "CUST-0018", "ticket_id": "TICK-0037", "amount": "29.00", "currency": "USD", "reason": "Full refund for billing cycle where customer received no value due to onboarding failure.", "status": "approved", "created_at": "2026-05-28", "processed_at": "2026-05-29", "notes": "Subscription cancelled same day."},
    # TICK-0038 — CUST-0025 bad onboarding, $29 refund, auto-approved
    {"refund_id": "REF-0002", "customer_id": "CUST-0025", "ticket_id": "TICK-0038", "amount": "29.00", "currency": "USD", "reason": "Refund for billing cycle; customer unable to use product due to Slack integration issues.", "status": "approved", "created_at": "2026-07-05", "processed_at": "2026-07-06", "notes": None},
    # TICK-0039 — CUST-0022 partial goodwill credit (applied as account_balance)
    {"refund_id": "REF-0003", "customer_id": "CUST-0022", "ticket_id": "TICK-0039", "amount": "14.50", "currency": "USD", "reason": "Partial goodwill credit for first week where monitors were not reporting correctly.", "status": "approved", "created_at": "2026-06-10", "processed_at": "2026-06-11", "notes": "Applied as account balance credit, not card refund."},
    # TICK-0043 — CUST-0006 prorated refund after Business->Team downgrade
    {"refund_id": "REF-0004", "customer_id": "CUST-0006", "ticket_id": "TICK-0043", "amount": "86.30", "currency": "USD", "reason": "Prorated credit for unused Business days after downgrade to Team mid-cycle.", "status": "approved", "created_at": "2026-08-11", "processed_at": "2026-08-12", "notes": "Applied as account balance credit for next invoice."},
    # TICK-0045 — CUST-0012 cancellation + refund; EXCEEDS $100 -> pending_review
    {"refund_id": "REF-0005", "customer_id": "CUST-0012", "ticket_id": "TICK-0045", "amount": "149.50", "currency": "USD", "reason": "Partial refund requested on cancellation of Business plan while account is past due.", "status": "pending_review", "created_at": "2026-08-16", "processed_at": None, "notes": "Escalated: amount exceeds $100 auto-approval threshold; account also has outstanding failed payment."},
    # TICK-0046 — CUST-0016 cancellation prorated refund, under $100, approved but pending cancel confirm
    {"refund_id": "REF-0006", "customer_id": "CUST-0016", "ticket_id": "TICK-0046", "amount": "19.33", "currency": "USD", "reason": "Prorated refund for unused Starter days after cancellation due to repeated payment failures.", "status": "approved", "created_at": "2026-08-20", "processed_at": None, "notes": "Pending cancellation confirmation before processing."},
    # TICK-0042 — CUST-0007 charged-after-trial dispute; needs investigation -> pending_review
    {"refund_id": "REF-0007", "customer_id": "CUST-0007", "ticket_id": "TICK-0042", "amount": "29.00", "currency": "USD", "reason": "Customer claims trial was cancelled before charge; refund pending confirmation of cancellation log.", "status": "pending_review", "created_at": "2026-08-05", "processed_at": None, "notes": "Escalated to confirm whether trial cancellation was recorded before charge was processed."},
]

# ---------------------------------------------------------------------------
# Downtime events  (backs the get_historical_stats / GET /monitors/{customer_id}/stats tool)
# Fields: event_id, customer_id, endpoint_name, started_at, resolved_at,
#         duration_minutes, cause, related_incident_id
# ---------------------------------------------------------------------------

DOWNTIME_EVENTS = [
    # CUST-0001 — false-positive from INC-004 DNS flapping (TICK-0017)
    {"event_id": "DT-0001", "customer_id": "CUST-0001", "endpoint_name": "api.northwindanalytics.io", "started_at": "2026-08-09", "resolved_at": "2026-08-09", "duration_minutes": 3, "cause": "False positive — upstream DNS resolver flapping (INC-004)", "related_incident_id": "INC-004"},
    # CUST-0001 — separate real brief outage unrelated to an incident
    {"event_id": "DT-0002", "customer_id": "CUST-0001", "endpoint_name": "dashboard.northwindanalytics.io", "started_at": "2026-07-22", "resolved_at": "2026-07-22", "duration_minutes": 12, "cause": "Customer-side server restart during a deployment", "related_incident_id": None},
    # CUST-0002 — multiple false-positive alerts (TICK-0021), pattern under investigation
    {"event_id": "DT-0003", "customer_id": "CUST-0002", "endpoint_name": "api.vertexcloud.io", "started_at": "2026-08-13", "resolved_at": "2026-08-13", "duration_minutes": 1, "cause": "Unexplained brief check failure — possible new flakiness (TICK-0021)", "related_incident_id": None},
    {"event_id": "DT-0004", "customer_id": "CUST-0002", "endpoint_name": "api.vertexcloud.io", "started_at": "2026-08-15", "resolved_at": "2026-08-15", "duration_minutes": 2, "cause": "Unexplained brief check failure — possible new flakiness (TICK-0021)", "related_incident_id": None},
    {"event_id": "DT-0005", "customer_id": "CUST-0002", "endpoint_name": "api.vertexcloud.io", "started_at": "2026-08-17", "resolved_at": "2026-08-17", "duration_minutes": 1, "cause": "Unexplained brief check failure — pattern escalated (TICK-0021)", "related_incident_id": None},
    # CUST-0003 — SSL false failure during INC-001 window (TICK-0031)
    {"event_id": "DT-0006", "customer_id": "CUST-0003", "endpoint_name": "api.bramblewood.dev (SSL check)", "started_at": "2026-08-06", "resolved_at": "2026-08-07", "duration_minutes": 1440, "cause": "False SSL failure — stale intermediate cert bundle (INC-001)", "related_incident_id": "INC-001"},
    # CUST-0006 — real downtime unrelated to tickets
    {"event_id": "DT-0007", "customer_id": "CUST-0006", "endpoint_name": "app.crestpoint.io", "started_at": "2026-06-14", "resolved_at": "2026-06-14", "duration_minutes": 28, "cause": "Customer-side infrastructure maintenance window", "related_incident_id": None},
    # CUST-0007 — false-positive from INC-004 (TICK-0018)
    {"event_id": "DT-0008", "customer_id": "CUST-0007", "endpoint_name": "api.emberco.dev", "started_at": "2026-08-10", "resolved_at": "2026-08-10", "duration_minutes": 4, "cause": "False positive — upstream DNS resolver flapping (INC-004)", "related_incident_id": "INC-004"},
    # CUST-0008 — intermittent SSL check (TICK-0033, still open)
    {"event_id": "DT-0009", "customer_id": "CUST-0008", "endpoint_name": "api.cascadiadevops.com (SSL check)", "started_at": "2026-08-21", "resolved_at": "2026-08-21", "duration_minutes": 5, "cause": "Intermittent SSL check failure — root cause under investigation (TICK-0033)", "related_incident_id": None},
    {"event_id": "DT-0010", "customer_id": "CUST-0008", "endpoint_name": "api.cascadiadevops.com (SSL check)", "started_at": "2026-08-23", "resolved_at": "2026-08-23", "duration_minutes": 7, "cause": "Intermittent SSL check failure — root cause under investigation (TICK-0033)", "related_incident_id": None},
    # CUST-0009 — brief degradation during API migration (TICK-0035)
    {"event_id": "DT-0011", "customer_id": "CUST-0009", "endpoint_name": "api.ironleaf.io", "started_at": "2026-08-15", "resolved_at": "2026-08-15", "duration_minutes": 9, "cause": "Brief degradation during bulk monitor migration via API", "related_incident_id": None},
    # CUST-0011 — real outage during INC-002 Slack delivery gap (TICK-0023)
    {"event_id": "DT-0012", "customer_id": "CUST-0011", "endpoint_name": "api.nimbusstack.dev", "started_at": "2026-08-08", "resolved_at": "2026-08-08", "duration_minutes": 6, "cause": "Real brief outage during which Slack alert was delayed 20+ min (INC-002)", "related_incident_id": "INC-002"},
    # CUST-0013 — false-positive from INC-004 (TICK-0019)
    {"event_id": "DT-0013", "customer_id": "CUST-0013", "endpoint_name": "status.driftwoodanalytics.com", "started_at": "2026-08-11", "resolved_at": "2026-08-11", "duration_minutes": 2, "cause": "False positive — upstream DNS resolver flapping (INC-004)", "related_incident_id": "INC-004"},
    # CUST-0015 — SSL false failure during INC-001 (TICK-0032)
    {"event_id": "DT-0014", "customer_id": "CUST-0015", "endpoint_name": "api.anchorpoint.io (SSL check)", "started_at": "2026-08-09", "resolved_at": "2026-08-09", "duration_minutes": 480, "cause": "False SSL expiry warning — stale cert bundle (INC-001)", "related_incident_id": "INC-001"},
    # CUST-0017 — real brief outage during which webhook never fired (TICK-0024)
    {"event_id": "DT-0015", "customer_id": "CUST-0017", "endpoint_name": "webhook.fenwickdigital.io", "started_at": "2026-08-12", "resolved_at": "2026-08-12", "duration_minutes": 14, "cause": "Real brief outage during which configured webhook never fired (TICK-0024)", "related_incident_id": None},
    # CUST-0019 — real outage with duplicate PagerDuty pages per INC-007 (TICK-0026)
    {"event_id": "DT-0016", "customer_id": "CUST-0019", "endpoint_name": "api.hollowbrooktech.com", "started_at": "2026-08-20", "resolved_at": "2026-08-20", "duration_minutes": 11, "cause": "Real outage; PagerDuty sent duplicate pages per INC-007", "related_incident_id": "INC-007"},
    # CUST-0022 — trailing false-positive from INC-004 (TICK-0020)
    {"event_id": "DT-0017", "customer_id": "CUST-0022", "endpoint_name": "api.kestrelsys.io", "started_at": "2026-08-12", "resolved_at": "2026-08-12", "duration_minutes": 1, "cause": "Trailing false-positive alert from INC-004 DNS window", "related_incident_id": "INC-004"},
    # CUST-0024 — monitor stuck in pending (TICK-0029/INC-003); endpoint unchecked, ongoing
    {"event_id": "DT-0018", "customer_id": "CUST-0024", "endpoint_name": "staging.meridiandevops.com", "started_at": "2026-08-22", "resolved_at": None, "duration_minutes": None, "cause": "Monitor stuck in 'pending' — endpoint unchecked (TICK-0029, INC-003); ongoing", "related_incident_id": "INC-003"},
]

# ---------------------------------------------------------------------------
# PASTE THIS BLOCK near the bottom of your seed_data.py (the file main.py imports
# from): after DOWNTIME_EVENTS is defined and ABOVE the `if __name__ == "__main__":`
# block.
#
# Why: the seed data was written for "today = 2026-08-25" with hard-coded dates.
# Time moves on, so billing dates drift into the past (negative days_remaining in
# the proration math), TICK-0022 falls outside the 14-day dedup window, and the
# downtime events fall outside the 30-day stats window. This shifts every ISO date
# by (today - anchor), so all the relative relationships stay exactly as designed.
# Non-date strings (IDs, prose) and None are left alone; string dates stay strings.
# ---------------------------------------------------------------------------
import re as _re
from datetime import date as _date

SEED_ANCHOR = _date(2026, 8, 25)  # the "today" this seed data was written for
_ISO_DATE = _re.compile(r"\d{4}-\d{2}-\d{2}")


def _shift_value(value, delta):
    if isinstance(value, str) and _ISO_DATE.fullmatch(value):
        return (_date.fromisoformat(value) + delta).isoformat()
    if isinstance(value, _date):
        return value + delta
    return value


def _shift_rows(rows, delta):
    return [{key: _shift_value(val, delta) for key, val in row.items()} for row in rows]


_DELTA = _date.today() - SEED_ANCHOR
CUSTOMERS = _shift_rows(CUSTOMERS, _DELTA)
SUBSCRIPTIONS = _shift_rows(SUBSCRIPTIONS, _DELTA)
TICKETS = _shift_rows(TICKETS, _DELTA)
KNOWN_INCIDENTS = _shift_rows(KNOWN_INCIDENTS, _DELTA)
INVOICES = _shift_rows(INVOICES, _DELTA)
REFUNDS = _shift_rows(REFUNDS, _DELTA)
DOWNTIME_EVENTS = _shift_rows(DOWNTIME_EVENTS, _DELTA)

if __name__ == "__main__":
    print(f"Customers:        {len(CUSTOMERS)}")
    print(f"Subscriptions:    {len(SUBSCRIPTIONS)}")
    print(f"Tickets:          {len(TICKETS)}")
    print(f"Known incidents:  {len(KNOWN_INCIDENTS)}")
    print(f"Invoices:         {len(INVOICES)}")
    print(f"Refunds:          {len(REFUNDS)}")
    print(f"Downtime events:  {len(DOWNTIME_EVENTS)}")

    from collections import Counter
    print("Tickets by category:", dict(Counter(t["category"] for t in TICKETS)))
    print("Tickets by status:  ", dict(Counter(t["status"] for t in TICKETS)))
    print("Customers by tier:  ", dict(Counter(c["tier"] for c in CUSTOMERS)))
    print("Customers by status:", dict(Counter(c["account_status"] for c in CUSTOMERS)))
    print("Invoices by status: ", dict(Counter(i["status"] for i in INVOICES)))
    print("Refunds by status:  ", dict(Counter(r["status"] for r in REFUNDS)))