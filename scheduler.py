from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd
import bisect

# ---------- Data models ----------

@dataclass
class WorkOrder:
    id: str
    product: str
    duration_hours: float
    op_index: Optional[int] = None        # for multi-op products (D1, D2, D3)
    due_date: Optional[datetime] = None

# ---------- Helpers for time windows ----------

Interval = Tuple[datetime, datetime]

def merge_intervals(intervals: List[Interval]) -> List[Interval]:
    """Merge overlapping downtime intervals."""
    if not intervals:
        return []
    I = sorted(intervals, key=lambda x: x[0])
    out = [I[0]]
    for s, e in I[1:]:
        if s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out

def overlaps(a: Interval, b: Interval) -> bool:
    return a[0] < b[1] and b[0] < a[1]

def next_slot_avoiding_downtime(
    start: datetime, duration_h: float, machine: str, downtime: Dict[str, List[Interval]]
) -> datetime:
    """Return earliest start >= start that does NOT overlap downtime on the machine."""
    cur = start
    dur = timedelta(hours=duration_h)
    blocks = downtime.get(machine, [])
    # fast exit
    if not blocks:
        return cur
    # try until no overlap
    while True:
        task_interval = (cur, cur + dur)
        bumped = False
        for (ds, de) in blocks:
            if overlaps(task_interval, (ds, de)):
                # jump to end of downtime and try again
                cur = de
                bumped = True
                break
        if not bumped:
            return cur

# ---------- Order generation ----------

def generate_orders_with_D(
    counts: Dict[str, int],
    durations_ABC: Dict[str, float],
    count_D: int,
    lag_D_min_h: float,
    start: datetime,
    auto_due_slack_hours: Optional[float] = None,
    jitter_hours: float = 0.0
) -> List[WorkOrder]:
    """
    Products:
      A: 1 op (durations_ABC['A'])
      B: 1 op (durations_ABC['B'])
      C: 1 op (durations_ABC['C'])
      D: 3 ops fixed: [1h, 3h, 2h] with precedence and min-lag between ops
    """
    orders: List[WorkOrder] = []
    idx = 1
    # A/B/C
    for p in ["A", "B", "C"]:
        n = counts.get(p, 0)
        for _ in range(n):
            dur = float(durations_ABC[p])
            dd = None
            if auto_due_slack_hours is not None:
                from random import random
                jitter = (random() - 0.5) * 2.0 * jitter_hours if jitter_hours else 0.0
                dd = start + timedelta(hours=dur + auto_due_slack_hours + jitter)
            orders.append(WorkOrder(id=f"WO{idx}", product=p, duration_hours=dur, op_index=None, due_date=dd))
            idx += 1
    # D with 3 ops
    for _ in range(count_D):
        dd = None
        if auto_due_slack_hours is not None:
            # sum of op durations + min lag * 2 is a rough base
            base = 1 + 3 + 2 + (2 * lag_D_min_h)
            dd = start + timedelta(hours=base + auto_due_slack_hours)
        wo_id = f"WO{idx}"
        orders.append(WorkOrder(id=wo_id, product="D", duration_hours=1.0, op_index=1, due_date=dd))
        orders.append(WorkOrder(id=wo_id, product="D", duration_hours=3.0, op_index=2, due_date=dd))
        orders.append(WorkOrder(id=wo_id, product="D", duration_hours=2.0, op_index=3, due_date=dd))
        idx += 1
    return orders

# ---------- Scheduling ----------

def schedule_orders(
    orders: List[WorkOrder],
    machines: List[str],
    start: datetime,
    rule: str = "LPT",
    lag_D_min_h: float = 0.0,
    downtime: Optional[Dict[str, List[Interval]]] = None
) -> List[Dict[str, Any]]:
    """
    Simple list scheduling on identical machines with:
      - rule in {"LPT","EDD","WSPT"}:
          LPT: long jobs first
          EDD: earliest due date first (None last)
          WSPT: shortest processing first (weights=1)
      - precedence for D (op1 -> op2 -> op3) with min lag between ops
      - downtime windows: tasks cannot overlap
    """
    downtime = {m: merge_intervals(downtime.get(m, [])) for m in (downtime or {})}
    # Build a precedence map for D: prev end times per WO id
    prev_end_D: Dict[Tuple[str,int], datetime] = {}  # (wo_id, op_index)

    # sort by rule
    def sort_key(o: WorkOrder):
        if rule.upper() == "LPT":
            return (-o.duration_hours, o.product, o.op_index or 0)
        if rule.upper() == "EDD":
            return (o.due_date is None, o.due_date or datetime.max, o.product, o.op_index or 0)
        if rule.upper() == "WSPT":
            return (o.duration_hours, o.product, o.op_index or 0)
        return (o.product, o.op_index or 0)

    # Important: respect precedence by making sure we schedule in op order for D
    orders_sorted = sorted(orders, key=lambda o: (o.product != "D", o.id, o.op_index or 0, *sort_key(o)))

    avail = {m: start for m in machines}
    plan: List[Dict[str, Any]] = []

    for o in orders_sorted:
        # compute earliest by precedence
        earliest = start
        if o.product == "D" and o.op_index is not None and o.op_index > 1:
            # need previous op end + lag
            prev_key = (o.id, o.op_index - 1)
            if prev_key not in prev_end_D:
                # If not scheduled yet (shouldn't happen due to sorting), just use start.
                pass
            else:
                earliest = max(earliest, prev_end_D[prev_key] + timedelta(hours=lag_D_min_h))

        # choose earliest-available machine but also avoid downtime
        chosen = machines[0]
        best_start = None
        best_end = None
        dur_h = o.duration_hours
        for m in machines:
            candidate = max(avail[m], earliest)
            candidate = next_slot_avoiding_downtime(candidate, dur_h, m, downtime)
            end = candidate + timedelta(hours=dur_h)
            if best_start is None or candidate < best_start:
                chosen, best_start, best_end = m, candidate, end

        # assign
        avail[chosen] = best_end
        plan_item = {
            "id": o.id,
            "product": o.product,
            "operation": f"{o.product}{o.op_index or ''}",
            "machine": chosen,
            "start": best_start,
            "end": best_end,
            "duration_hours": o.duration_hours,
            "due_date": o.due_date,
        }
        plan.append(plan_item)

        # record D op end for precedence
        if o.product == "D" and o.op_index is not None:
            prev_end_D[(o.id, o.op_index)] = best_end

    return plan

# ---------- DataFrame utilities ----------

def plan_to_dataframe(plan: List[Dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(plan)
    if df.empty:
        return df
    for col in ["start","end","due_date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])
    return df

def dataframe_to_plan(df: pd.DataFrame) -> List[Dict[str, Any]]:
    req_cols = {"id","product","machine","start","end","duration_hours"}
    if not req_cols.issubset(df.columns):
        missing = req_cols - set(df.columns)
        raise ValueError(f"Missing columns: {missing}")
    df = df.copy()
    for col in ["start","end","due_date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])
    return df.to_dict(orient="records")

def metrics(plan: List[Dict[str, Any]]):
    df = plan_to_dataframe(plan)
    if df.empty:
        return {"makespan_hours": 0, "by_machine": {}, "lateness": {}}
    bym = {}
    for m, g in df.groupby("machine"):
        duration_sum = g["duration_hours"].sum()
        smin = g["start"].min()
        emax = g["end"].max()
        span_h = (emax - smin).total_seconds() / 3600.0
        util = (duration_sum / span_h)*100 if span_h > 0 else 0.0
        bym[m] = {
            "ops": int(len(g)),
            "hours": float(duration_sum),
            "utilization_pct": float(round(util, 2)),
            "span_hours": float(round(span_h, 2)),
        }
    makespan_h = (df["end"].max() - df["start"].min()).total_seconds() / 3600.0

    late = {}
    if "due_date" in df.columns and df["due_date"].notna().any():
        df["lateness_h"] = (df["end"] - df["due_date"]).dt.total_seconds() / 3600.0
        df["tardiness_h"] = df["lateness_h"].clip(lower=0)
        late = {
            "avg_lateness_h": float(round(df["lateness_h"].mean(skipna=True), 2)),
            "total_tardiness_h": float(round(df["tardiness_h"].sum(skipna=True), 2)),
            "percent_late": float(round((df["tardiness_h"] > 0).mean() * 100, 1))
        }
    return {"makespan_hours": float(round(makespan_h, 2)), "by_machine": bym, "lateness": late}
