# APS Scheduling — Plotly/Streamlit MVP

Minimal **Streamlit** app to visualize a production schedule (Gantt) with **Plotly**.

## Features
- Default puzzle: 5 machines, 100 one-step orders (A/B/C = 2h/5h/6h), start **Aug 9, 2025 08:00 (Asia/Makassar)**
- Adjustable machines, counts, durations, start date/time
- **LPT** heuristic across identical machines
- Plotly timeline (zoom/pan/hover)
- Metrics: makespan + per-machine utilization
- Import/Export JSON, Download CSV

## Run locally
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
