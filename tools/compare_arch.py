"""Generate SRAM architecture comparisons from captured simulation and K7 runs."""

import argparse
import csv
import json
import re
from pathlib import Path

from variants import MATRIX_VARIANTS, VARIANTS


def rows(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return [{key: int(value) for key, value in row.items()} for row in csv.DictReader(stream)]


def write(path, records):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def extract_physical(path, variant):
    impl = (path / "impl_vivado.log").read_text(encoding="utf-8", errors="replace")
    timing = (path / "check_timing.rpt").read_text(encoding="utf-8")
    util = (path / "utilization.rpt").read_text(encoding="utf-8")
    drc = (path / "drc.rpt").read_text(encoding="utf-8")
    route = (path / "route.rpt").read_text(encoding="utf-8")
    critical = (path / "critical_paths.rpt").read_text(encoding="utf-8")
    slack = re.search(r"^K7_WNS_NS=(\S+) K7_WHS_NS=(\S+)", impl, re.M)
    structure = re.search(r"^K7_STRUCTURES SPAD_RAMB36=(\d+) NEXT_ADDR_FFS=(\d+)", impl, re.M)
    unconstrained = re.search(r"checking unconstrained_internal_endpoints \((\d+)\)", timing)
    if not (slack and structure and unconstrained and "K7_BITSTREAM_READY" in impl.splitlines()):
        raise ValueError(f"{variant}: incomplete routed timing or structure report")
    wns, whs = map(float, slack.groups())
    spad, next_addr = map(int, structure.groups())
    turn, cache, _ = VARIANTS[variant]
    if (wns < 0 or whs < 0 or unconstrained[1] != "0" or spad != 2 * bool(cache) or
            bool(next_addr) != bool(turn) or re.search(r"^REQP-1839#", drc, re.M)):
        raise ValueError(f"{variant}: routed gate failed")
    scopes = ("cim_k7_top", "accel", "(accel)", "macro_unit", "quant_unit", "cpu")
    hierarchy = {}
    for line in util.splitlines():
        fields = [field.strip() for field in line.strip("|").split("|")]
        if fields[0] in scopes and len(fields) == 10:
            hierarchy[fields[0]] = dict(zip(("lut", "ff", "ramb36", "ramb18", "dsp"),
                                            (int(fields[i]) for i in (2, 6, 7, 8, 9))))
    if hierarchy.keys() != set(scopes):
        raise ValueError(f"{variant}: missing utilization scope")
    path_fields = ("Source:", "Destination:", "Path Group:", "Path Type:", "Data Path Delay:")
    first_path = {}
    for line in critical.splitlines():
        for field in path_fields:
            if line.lstrip().startswith(field):
                first_path.setdefault(field, line.strip())
    if len(first_path) != len(path_fields):
        raise ValueError(f"{variant}: missing critical path fields")
    return dict(variant=variant, wns_ns=wns, whs_ns=whs, unconstrained_internal=0,
                spad_ramb36=spad, next_addr_ffs=next_addr, hierarchy=hierarchy,
                critical_setup=list(first_path.values()),
                drc_rules=[line.strip() for line in drc.splitlines()
                           if re.match(r"^\|\s*[A-Z]+-\d+", line)],
                route_summary=[line.strip() for line in route.splitlines()
                               if "routable nets" in line or "routing errors" in line])


def capture(build, evidence):
    """Select public evidence without copying the local tool/CPU paths or bitstreams."""
    evidence.mkdir(parents=True, exist_ok=True)
    common = None
    board_identity = None
    for variant, (_, _, usr_access) in MATRIX_VARIANTS.items():
        path = build / f"k7_matrix_{variant}"
        bit = json.loads((path / "bitstream_metadata.json").read_text(encoding="utf-8"))
        prep = json.loads((path / "build_metadata.json").read_text(encoding="utf-8"))
        compare = {key: prep[key] for key in ("cpu_sources", "prepared_files", "activation_sha256",
                                              "golden_sha256", "fpga_part", "core_clock_hz")}
        if common is None:
            common = compare
        if compare != common or bit["prepared_files"] != common["prepared_files"] or bit["usr_access"] != usr_access:
            raise ValueError(f"{variant}: changed inputs or bitstream ID")
        sim = json.loads((path / "soc_results.json").read_text(encoding="utf-8"))
        reset = json.loads((path / "soc_reset_results.json").read_text(encoding="utf-8"))
        out = evidence / variant
        out.mkdir(exist_ok=True)
        for name in ("fixed", "real"):
            suffix = "" if name == "fixed" else "_real"
            write(out / f"{name}.csv", rows(build / "matrix_sim" / f"{variant}{suffix}.csv"))
        write(out / "traffic.csv", rows(path / "traffic.csv"))
        soc = dict(tasks=sim, resets=reset, software=json.loads((path / "soc_cpu_results.json").read_text()))
        records = {"soc": soc, "routed": dict(extract_physical(path, variant),
                                             usr_access=usr_access, bit_sha256=bit["bit_sha256"])}
        board_path = path / "board_results.json"
        if board_path.is_file():
            board = json.loads(board_path.read_text(encoding="utf-8"))
            identity = (board.pop("jtag_serial"), board.pop("uart_port"))
            if board_identity is None:
                board_identity = identity
            if identity != board_identity or board["usr_access"] != usr_access or bit["bit_sha256"] != board["bit_sha256"]:
                raise ValueError(f"{variant}: changed board or bitstream")
            if sim != board["tasks"] or reset != board["resets"]:
                raise ValueError(f"{variant}: RTL SoC and board accelerator results disagree")
            records["board"] = board
            uart = (path / "board_uart.log").read_text(encoding="ascii")
            (out / "uart.txt").write_text(uart, encoding="ascii")
        else:
            print(f"NOT_RUN {variant}: no board result")
            if (out / "board.json").exists():
                raise ValueError(f"{variant}: existing board evidence needs a separate capture directory")
        for name, record in records.items():
            (out / f"{name}.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    (evidence / "common.json").write_text(json.dumps(common, indent=2) + "\n", encoding="utf-8")


def with_gain(records, key_fields):
    reference = {tuple(r[k] for k in key_fields): r["cycles"]
                 for r in records if r["variant"] == "turnaround"}
    for row in records:
        base = reference[tuple(row[k] for k in key_fields)]
        row["cycles_saved_vs_turnaround"] = base - row["cycles"]
        row["pct_saved_vs_turnaround"] = f"{100 * (base - row['cycles']) / base:.4f}"
    return records


def compare(evidence, output):
    output.mkdir(parents=True, exist_ok=True)
    sweep, soc_rows, board_rows, physical, software = [], [], [], [], []
    for variant, (_, cache, _) in MATRIX_VARIANTS.items():
        path = evidence / variant
        fixed = rows(path / "fixed.csv")
        keys = {(r["read_latency"], r["M"], r["mode"]) for r in fixed}
        if len(fixed) != 32 or keys != {(latency, m, mode) for latency in (1, 2, 4, 8)
                                       for m in (1, 8, 32, 125) for mode in (0, 1)}:
            raise ValueError(f"{variant}: incomplete fixed sweep")
        for row in fixed:
            del row["clock_edges"], row["case"]
            sweep.append(dict(variant=variant, **row))
        soc = json.loads((path / "soc.json").read_text())
        board_path = path / "board.json"
        board = json.loads(board_path.read_text()) if board_path.is_file() else None
        if board is not None and board["tasks"] != soc["tasks"]:
            raise ValueError(f"{variant}: RTL SoC and board accelerator results disagree")
        traffic = {(r["M"], r["mode"]): r for r in rows(path / "traffic.csv")}
        for task in soc["tasks"]:
            r = traffic[(task["M"], task["mode"])]
            m, cycles = task["M"], task["cycles"]
            if (r["cycles"] != cycles or r["shared_reads"] != 1216 + (1 if cache else 8) * 16 * m or
                    r["shared_writes"] != task["committed_words"] or r["cache_reads"] != cache * 112 * m or
                    r["cache_writes"] != cache * 16 * m):
                raise ValueError(f"{variant}: inconsistent SoC traffic")
            row = dict(variant=variant, mode=r["mode"], M=m, cycles=cycles,
                       us_at_50mhz=f"{cycles / 50:.2f}", outputs=task["outputs"],
                       shared_reads_sim=r["shared_reads"], shared_writes=r["shared_writes"],
                       cache_reads_sim=r["cache_reads"], cache_writes_sim=r["cache_writes"])
            soc_rows.append(row)
            if board is not None:
                board_rows.append(row.copy())
        for name, result in (("soc", soc), ("board", board)):
            if result is not None:
                software.extend(dict(source=name, variant=variant, **row, us_at_50mhz=f"{row['cycles'] / 50:.2f}")
                                for row in result["software"])
        routed = json.loads((path / "routed.json").read_text())
        for scope, counts in routed["hierarchy"].items():
            physical.append(dict(variant=variant, scope=scope, **counts, wns_ns=routed["wns_ns"],
                                 whs_ns=routed["whs_ns"], spad_ramb36=routed["spad_ramb36"],
                                 next_addr_ffs=routed["next_addr_ffs"]))
    write(output / "fixed_sweep.csv", with_gain(sweep, ("M", "mode", "read_latency")))
    write(output / "soc_comparison.csv", with_gain(soc_rows, ("M", "mode")))
    if len(board_rows) == len(soc_rows):
        write(output / "k7_comparison.csv", with_gain(board_rows, ("M", "mode")))
    else:
        print("NOT_RUN complete four-variant board comparison")
    write(output / "k7_routed.csv", physical)
    write(output / "k7_software.csv", software)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--capture", type=Path, help="Build directory with completed local runs")
    parser.add_argument("--out", type=Path, default=Path("build/matrix_tables"))
    args = parser.parse_args()
    if args.capture:
        capture(args.capture, args.evidence)
    compare(args.evidence, args.out)


if __name__ == "__main__":
    main()
