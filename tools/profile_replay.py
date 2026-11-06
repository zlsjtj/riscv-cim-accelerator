"""Summarize complete SoC tasks from k7.py sim --profile-tasks."""

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path


PHASES = ("load", "macro_start", "macro_busy", "raw_full", "input_wait", "other")
ACTIVITY = ("contexts_full", "quant_issue", "quant_result", "write_pending",
            "write_commit", "shared_stall", "response_wait", "replay")
IDLE_ACTIVITY = ("other_quant_or_write", "other_full_quant_or_write")


def summarize(path):
    totals = {}
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            event = row.pop("event").strip()
            edge = {key: int(value) for key, value in row.items()}
            task = edge["task"]
            all_edges, later_tiles = totals.setdefault(task, (Counter(), Counter()))
            if event in ("done", "abort"):
                del totals[task]
                if event == "done":
                    if sum(all_edges[k] for k in PHASES) != edge["cycle"]:
                        raise ValueError(f"{path}: incomplete timeline for task {task}")
                    for region, counts in (("task", all_edges), ("replay_run", later_tiles)):
                        yield dict(task=task, M=edge["M"], mode=edge["mode"], region=region,
                                   cycles=sum(counts[k] for k in PHASES),
                                   **{k: counts[k] for k in PHASES + ACTIVITY + IDLE_ACTIVITY})
                continue
            if event != "edge":
                raise ValueError(f"{path}: unexpected event {event}")
            phase = ("load" if edge["state"] in (1, 2) else
                     next((key for key in PHASES[1:-1] if edge[key]), "other"))
            counters = (all_edges, later_tiles) if edge["tile"] > 0 and edge["state"] == 3 else (all_edges,)
            for counts in counters:
                counts[phase] += 1
                for key in ACTIVITY:
                    counts[key] += edge[key]
                if phase == "other" and (edge["quant_issue"] or edge["quant_result"] or edge["write_pending"]):
                    counts["other_quant_or_write"] += 1
                    counts["other_full_quant_or_write"] += edge["contexts_full"]
    if totals:
        raise ValueError(f"{path}: trace ends before a task completes")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    records = list(summarize(parser.parse_args().trace))
    if not records:
        raise ValueError("No completed tasks")
    writer = csv.DictWriter(sys.stdout, list(records[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(records)


if __name__ == "__main__":
    main()
