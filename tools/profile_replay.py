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
                    record["tail_cycles"] = record.pop("run_end") - record.pop("last_macro")
                    yield record
                last_tile.pop(task, None)
                continue
            if last_tile.get(task) == 7 and tile == 0:
                second[task] = dict(task=task, M=int(row["M"]), layer2_start=cycle, run_start=0,
                                    run_cycles=0, input_wait=0, first_macro_offset=-1,
                                    input_wait_replay=0, input_wait_no_replay=0,
                                    backend_cycles=0, backend_both_live=0,
                                    last_quant_result=0, last_write_commit=0,
                                    run_end=0, last_macro=0)
            last_tile[task] = tile
            if task in second and tile == 0 and state == 3:
                record = second[task]
                if not record["run_cycles"]:
                    record["run_start"] = cycle
                record["run_cycles"] += 1
                record["run_end"] = cycle
                macro = row["macro_start"] == "1" or row["macro_busy"] == "1"
                if row["macro_start"] == "1" and record["first_macro_offset"] == -1:
                    record["first_macro_offset"] = cycle - record["run_start"]
                if row["quant_result"] == "1":
                    record["last_quant_result"] = cycle - record["run_start"]
                if row["write_commit"] == "1":
                    record["last_write_commit"] = cycle - record["run_start"]
                if macro:
                    record["last_macro"] = cycle
                elif row["raw_full"] != "1":
                    if row["input_wait"] == "1":
                        record["input_wait"] += 1
                        key = "input_wait_replay" if row["replay"] == "1" else "input_wait_no_replay"
                        record[key] += 1
                    else:
                        record["backend_cycles"] += 1
                        record["backend_both_live"] += int(row["contexts_full"])


def backend_stage(edge, ctx):
    """Classify a non-macro, non-input edge by the oldest live row."""
    if not edge["live_mask"]:
        return "allocate" if edge["allocate"] else "tile_drain"
    if edge["allocate"]:
        return "allocate"
    if edge["write_offer"] and edge["write_ctx"] == ctx:
        if not edge["write_commit"]:
            return "write_stall"
        return "write_last" if edge["write_last"] else "write_first"
    if (edge["output_ready_mask"] >> ctx) & 1:
        return "write_enqueue"
    if edge["quant_result"] and edge["quant_result_ctx"] == ctx:
        return "quant_last" if edge["quant_result_channel"] == 7 else "quant_result"
    if (edge["recon_mask"] >> ctx) & 1:
        return "quant_issue" if edge["quant_issue"] and edge["quant_ctx"] == ctx else "quant_wait"
    return "reconstruct" if edge["raw_mask"] else "macro_result_wait"


def backend_tile0_edges(path, task):
    """Return all second-layer tile-zero RUN edges with exclusive categories."""
    prev_tile = None
    layer = 1
    start = None
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if int(row["task"]) != task or row.pop("event").strip() != "edge":
                continue
            edge = {key: int(value) for key, value in row.items()}
            tile = edge["tile"]
            if prev_tile == 7 and tile == 0:
                layer += 1
            prev_tile = tile
            if layer != 2 or tile != 0 or edge["state"] != 3:
                continue
            if start is None:
                start = edge["cycle"]
            live = [ctx for ctx in (0, 1) if (edge["live_mask"] >> ctx) & 1]
            oldest = min(live, key=lambda ctx: edge[f"position{ctx}"]) if live else -1
            phase = next((key for key in PHASES[1:-1] if edge[key]), "other")
            yield dict(relative_cycle=edge["cycle"] - start, phase=phase, oldest=oldest,
                       backend=backend_stage(edge, oldest) if phase == "other" else "", **edge)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--second-tile0", action="store_true",
                       help="measure the second layer's first tile within a chained task")
    group.add_argument("--backend-tile0", type=int, metavar="TASK",
                       help="classify each second-layer tile-zero edge of a traced task")
    args = parser.parse_args()
    profile = summarize_second_tile0 if args.second_tile0 else summarize
    records = list(backend_tile0_edges(args.trace, args.backend_tile0)
                   if args.backend_tile0 is not None else profile(args.trace))
    if not records:
        raise ValueError("No completed tasks")
    writer = csv.DictWriter(sys.stdout, list(records[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(records)


if __name__ == "__main__":
    main()
