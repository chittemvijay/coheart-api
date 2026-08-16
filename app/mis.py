from typing import Dict, List, Optional
from datetime import datetime

# Simple MIS trackers implementation
# trackers: tracker_id -> {id, title, indicators: {ind_id: {id, name, target}}}
trackers: Dict[str, Dict] = {}
# mis_data: tracker_id -> list of {timestamp, submitted_by, values: {ind_id: value}}
mis_data: Dict[str, List[Dict]] = {}


def create_tracker(tracker_id: str, title: str, indicators: List[Dict]) -> Dict:
    if tracker_id in trackers:
        raise ValueError("tracker exists")
    tracker = {"id": tracker_id, "title": title, "indicators": {ind["id"]: ind for ind in indicators}}
    trackers[tracker_id] = tracker
    mis_data[tracker_id] = []
    return tracker


def update_tracker(tracker_id: str, title: Optional[str], indicators: Optional[List[Dict]]) -> Dict:
    if tracker_id not in trackers:
        raise KeyError("not found")
    if title:
        trackers[tracker_id]["title"] = title
    if indicators is not None:
        trackers[tracker_id]["indicators"] = {ind["id"]: ind for ind in indicators}
    return trackers[tracker_id]


def delete_tracker(tracker_id: str) -> None:
    trackers.pop(tracker_id, None)
    mis_data.pop(tracker_id, None)


def submit_data(tracker_id: str, submitted_by: str, values: Dict[str, float]) -> Dict:
    if tracker_id not in trackers:
        raise KeyError("not found")
    entry = {"timestamp": datetime.utcnow().isoformat(), "submitted_by": submitted_by, "values": values}
    mis_data.setdefault(tracker_id, []).append(entry)
    return entry


def report_aggregate(tracker_id: str):
    # simple sum aggregation per indicator
    if tracker_id not in trackers:
        raise KeyError("not found")
    agg = {}
    for ind_id in trackers[tracker_id]["indicators"].keys():
        agg[ind_id] = 0
    for entry in mis_data.get(tracker_id, []):
        for k, v in entry.get("values", {}).items():
            try:
                agg[k] = agg.get(k, 0) + float(v)
            except Exception:
                pass
    return {"tracker_id": tracker_id, "title": trackers[tracker_id]["title"], "aggregate": agg, "count": len(mis_data.get(tracker_id, []))}
