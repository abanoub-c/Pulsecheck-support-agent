# Pulsecheck — Multi-Agent Customer Support System

A production-grade multi-agent support architecture built with **LangGraph**, **FastAPI**, and **Streamlit**.

## Features
- **Intent Triage Router:** Categorizes customer inquiries into billing, technical, and refund domain agents.
- **Human-in-the-Loop:** Uses LangGraph `interrupt()` nodes to route high-value refunds or complex tickets to an ops dashboard.
- **Audit Logging:** Tracks tool execution state and persistent thread histories.