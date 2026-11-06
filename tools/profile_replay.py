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


def summarize_second_tile0(path):
    """Measure tile zero after the 7-to-0 transition inside a single START."""
    last_tile = {}
    second = {}
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            task, tile, state, cycle = (int(row[key]) for key in ("task", "tile", "state", "cycle"))
            event = row["event"].strip()
            if event in ("done", "abort"):
                record = second.pop(task, None)
                if event == "done" and record:
                    yield record
                last_tile.pop(task, None)
                continue
            if last_tile.get(task) == 7 and tile == 0:
                second[task] = dict(task=task, M=int(row["M"]), layer2_start=cycle, run_start=0,
                                    run_cycles=0, input_wait=0, first_macro_offset=-1)
            last_tile[task] = tile
            if task in second and tile == 0 and state == 3:
                record = second[task]
                if not record["run_cycles"]:
                    record["run_start"] = cycle
                record["run_cycles"] += 1
                macro_start = int(row["macro_start"])
                if macro_start and record["first_macro_offset"] == -1:
                    record["first_macro_offset"] = cycle - record["run_start"]
                if int(row["input_wait"]) and not (macro_start or int(row["macro_busy"]) or int(row["raw_full"])):
                    record["input_wait"] += 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--second-tile0", action="store_true",
                        help="measure the second layer's first tile within a chained task")
    args = parser.parse_args()
    profile = summarize_second_tile0 if args.second_tile0 else summarize
    records = list(profile(args.trace))
    if not records:
        raise ValueError("No completed tasks")
    writer = csv.DictWriter(sys.stdout, list(records[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(records)


if __name__ == "__main__":
    main()
