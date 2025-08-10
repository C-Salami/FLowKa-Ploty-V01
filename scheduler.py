from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Dict, Any
import pandas as pd

@dataclass
class Product:
    code: str
    duration_hours: float
    color: str

@dataclass
class WorkOrder:
    id: str
    product: str
    duration_hours: float

def generate_orders(counts: Dict[str, int], durations: Dict[str, float]) -> List[WorkOrder]:
    orders: List[WorkOrder] = []
    idx = 1
    for p in ["A", "B", "C"]:
        n = counts.get(p, 0)
        for _ in range(n):
            orders.append(WorkOrder(id=f"WO{idx}", product=p, duration_hours=durations[p]))
            idx += 1
    return orders

def lpt_schedule(orders: List[WorkOrder], machines: List[str], start: datetime) -> List[Dict[str, Any]]:
    """Longest Processing Time first across identical machines."""
    sorted_orders = sorted(orders, key=lambda o: o.duration_hours, reverse=True)
    avail = {m: start for m in machines}
    plan: List[Dict[str, Any]] = []
    for o in sorted_orders:
        m = min(machines, key=lambda k: avail[k])     # earliest-available machine
        s = avail[m]
        e = s + timedelta(hours=o.duration_hours)
        avail[m] = e
        plan.append({
            "id": o.id,
            "product": o.product,
            "machine": m,
            "start": s,
            "end": e,
            "duration_hours": o.duration_hours,
        })
    return plan

def metrics(plan: List[Dict[str, Any]]):
    if not plan:
        return {"makespan_hours": 0, "by_machine": {}}
    df = pd.DataFrame(plan)
    bym = {}
    for m, g in df.groupby("machine"):
        duration_sum = g["duration_hours"].sum()
        start_min = g["start"].min()
        end_max = g["end"].max()
        span_h = (end_max - start_min).total_seconds() / 3600
        util = (duration_sum / span_h)*100 if span_h > 0 else 0
        bym[m] = {
            "ops": len(g),
            "hours": float(duration_sum),
            "utilization_pct": float(round(util, 2)),
            "span_hours": float(round(span_h, 2)),
        }
    makespan_h = (df["end"].max() - df["start"].min()).total_seconds() / 3600
    return {"makespan_hours": float(round(makespan_h, 2)), "by_machine": bym}

def plan_to_dataframe(plan: List[Dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(plan)
    df["start"] = pd.to_datetime(df["start"])
    df["end"] = pd.to_datetime(df["end"])
    return df

def dataframe_to_plan(df: pd.DataFrame) -> List[Dict[str, Any]]:
    req_cols = {"id", "product", "machine", "start", "end", "duration_hours"}
    if not req_cols.issubset(df.columns):
        missing = req_cols - set(df.columns)
        raise ValueError(f"Missing columns: {missing}")
    df = df.copy()
    df["start"] = pd.to_datetime(df["start"])
    df["end"] = pd.to_datetime(df["end"])
    return df.to_dict(orient="records")
