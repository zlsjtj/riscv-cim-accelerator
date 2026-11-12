"""Generate the repository figures from the checked-in K7 record.

Install Playwright and Chromium, then run python docs/assets/generate.py.
An installed Chrome can be selected with --channel chrome.
"""

import argparse
import hashlib
import json
from html import escape
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "evidence/kws_subgraph/k7_board.json"
UART = SOURCE.with_name("k7_board_uart.txt")
CYCLES_PER_MS = 50_000
INK, MUTED, BLUE, TEAL, BG, LINE = "#152238", "#526079", "#2563EB", "#0F766E", "#F6F8FB", "#D9E1EC"
WHITE, BLUE_BG, TEAL_BG = "#FFFFFF", "#EAF1FF", "#E4F3F0"
PALE_BLUE, PALE_TEAL = "#BBD4FF", "#95E5D5"
SANS = "Arial, Liberation Sans, sans-serif"
MONO = "Consolas, Liberation Mono, monospace"


class Figure:
    def __init__(self, width, height, title, description):
        self.width, self.height = width, height
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
            f'<title id="title">{escape(title)}</title><desc id="desc">{escape(description)}</desc>',
        ]
        self.rect(0, 0, width, height, fill=BG, stroke="none", radius=0)

    def rect(self, x, y, w, h, fill=WHITE, stroke=LINE, radius=12):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" '
                          f'fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')

    def text(self, x, y, label, size=18, fill=INK, weight=400, anchor="start", mono=False):
        self.parts.append(f'<text x="{x}" y="{y}" fill="{fill}" font-size="{size}" '
                          f'font-family="{MONO if mono else SANS}" font-weight="{weight}" '
                          f'text-anchor="{anchor}">{escape(label)}</text>')

    def line(self, points, color=LINE, width=2, dashed=False, arrow=False, both=False):
        coords = " ".join(f"{x},{y}" for x, y in points)
        dash = ' stroke-dasharray="7 6"' if dashed else ""
        self.parts.append(f'<polyline points="{coords}" fill="none" stroke="{color}" '
                          f'stroke-width="{width}" stroke-linejoin="round"{dash}/>')
        if arrow:
            self.arrowhead(*points[-2:], color)
        if both:
            self.arrowhead(points[1], points[0], color)

    def arrowhead(self, start, end, color):
        dx, dy = end[0] - start[0], end[1] - start[1]
        assert bool(dx) != bool(dy), (start, end)
        ux, uy = ((1 if dx > 0 else -1), 0) if dx else (0, (1 if dy > 0 else -1))
        x, y = end
        a = (x - 9 * ux + 4 * uy, y - 9 * uy - 4 * ux)
        b = (x - 9 * ux - 4 * uy, y - 9 * uy + 4 * ux)
        self.parts.append(f'<polygon points="{x},{y} {a[0]},{a[1]} {b[0]},{b[1]}" fill="{color}"/>')

    def save(self, stem):
        path = HERE / f"{stem}.svg"
        path.write_text("\n".join([*self.parts, "</svg>"]) + "\n", encoding="utf-8", newline="\n")
        return path


def hero():
    fig = Figure(1280, 288, "Low-bit compute measured on FPGA",
                 "A banked scratchpad feeds the digital CiM macro proxy, followed by INT8 writeback.")
    fig.rect(2, 2, 1276, 284, INK, "#415069", 25)
    fig.text(54, 121, "Low-bit compute.", 63, WHITE, 700)
    fig.text(54, 194, "Measured on FPGA.", 63, PALE_TEAL, 700)
    fig.line([(696, 55), (696, 233)], "#415069", 2)
    fig.rect(744, 48, 486, 51, "#202F49", "#415069", 9)
    fig.rect(744, 119, 486, 51, "#273C60", "#637DAB", 9)
    fig.rect(744, 190, 486, 51, "#202F49", "#415069", 9)
    for label, y in [("Banked input scratchpad", 83), ("Digital CiM macro proxy", 154),
                     ("INT8 writeback", 225)]:
        fig.text(987, y, label, 32, WHITE, 700, anchor="middle")
    for y in (99, 170):
        fig.line([(987, y), (987, y+20)], PALE_TEAL, 3, arrow=True)
    return fig


def hero_narrow():
    fig = Figure(640, 160, "Low-bit compute measured on FPGA",
                 "Compact banner with the same two lines as the desktop version.")
    fig.rect(2, 2, 636, 156, INK, "#415069", 19)
    fig.text(320, 68, "Low-bit compute.", 43, WHITE, 700, anchor="middle")
    fig.text(320, 123, "Measured on FPGA.", 43, PALE_TEAL, 700, anchor="middle")
    return fig


def architecture():
    fig = Figure(840, 510, "RISC-V CiM system and KWS handoffs",
                 "RISC-V writes START and reads DONE through the controller MMIO interface. CPU depthwise runs between two "
                 "independently submitted pointwise tasks and exchanges tensors through shared SRAM.")
    fig.text(26, 43, "System architecture", 32, weight=700)
    fig.line([(479, 36), (521, 36)], TEAL, 3, arrow=True)
    fig.text(533, 43, "Data", 20, MUTED)
    fig.line([(632, 36), (675, 36)], BLUE, 3, dashed=True, arrow=True)
    fig.text(687, 43, "MMIO control", 20, MUTED)

    fig.rect(26, 104, 211, 132, BLUE_BG)
    fig.text(42, 142, "RISC-V CPU", 25, weight=700)
    fig.text(42, 176, "Ibex: open simulation", 18, MUTED)
    fig.text(42, 207, "K7: JYDD CPU", 18, MUTED)
    fig.rect(281, 104, 208, 132, TEAL_BG)
    fig.text(298, 142, "Shared SRAM", 25, weight=700)
    fig.text(298, 176, "Activations A / B", 19, MUTED)
    fig.text(298, 207, "Weights + parameters", 17, MUTED)
    fig.line([(237, 168), (281, 168)], TEAL, 3, arrow=True, both=True)

    fig.rect(543, 70, 271, 286)
    fig.text(558, 101, "CiM accelerator", 24, weight=700)
    stages = [(116, "Banked input scratchpad"), (166, "Digital CiM macro proxy"),
              (216, "Result slots / INT32 rebuild"), (266, "Requantize / write back")]
    for y, label in stages:
        fig.rect(557, y, 243, 38, BLUE_BG if y == 166 else BG, radius=7)
        fig.text(679, y+26, label, 19, weight=700 if y == 166 else 400, anchor="middle")
    for y in (154, 204, 254):
        fig.line([(679, y), (679, y+12)], TEAL, 2.5, arrow=True)
    fig.line([(489, 135), (557, 135)], TEAL, 3, arrow=True)
    fig.text(521, 124, "Input", 14, TEAL, anchor="middle")
    fig.line([(557, 285), (516, 285), (516, 207), (489, 207)], TEAL, 3, arrow=True)
    fig.rect(557, 310, 243, 39, BLUE_BG, radius=7)
    fig.text(679, 327, "Controller / MMIO", 19, BLUE, 700, anchor="middle")
    fig.text(679, 343, "Reserve a slot before launch", 15, MUTED, anchor="middle")
    fig.line([(131, 236), (131, 330), (557, 330)], BLUE, 3, dashed=True, arrow=True, both=True)
    fig.text(252, 316, "START / DONE", 18, BLUE, mono=True)

    fig.text(26, 374, "KWS activation handoffs", 26, weight=700)
    for x, label, detail, extra, fill in [
        (26, "PW (op2)", "CiM START #1", "Reads A", BLUE_BG),
        (310, "DW (op3)", "RISC-V CPU", "Reads B, writes A", TEAL_BG),
        (594, "PW (op4)", "CiM START #2", "Writes B", BLUE_BG),
    ]:
        fig.rect(x, 394, 220, 91, fill)
        fig.text(x+15, 423, label, 23, weight=700)
        fig.text(x+15, 450, detail, 19, MUTED)
        fig.text(x+15, 474, extra, 18, MUTED)
    for x, label in [(246, "B"), (530, "A")]:
        fig.line([(x, 448), (x+64, 448)], TEAL, 3, arrow=True)
        fig.text(x+32, 434, label, 21, TEAL, weight=700, anchor="middle", mono=True)
    return fig


def board_rows():
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    assert data["usr_access"] == "43494d4a"
    rows = {(row["case"], row["mode"]): row for row in data["modes"]}
    assert set(rows) == {(case, mode) for case in (0, 1) for mode in ("cpu_only", "hybrid")}
    for row in rows.values():
        assert row["total_cycles"] == sum(row[k] for k in ("pw1_cycles", "dw_cycles", "pw2_cycles"))
        assert row["mismatches"] == 0
    assert sum(row["compared_bytes"] for row in data["diagnostics"] if not row["mismatches"]) == 96000
    return rows


def latency(rows):
    fig = Figure(840, 388, "K7 end-to-end subgraph latency",
                 "Stop and Left use a shared zero-based axis. Hybrid is 6.84 and 6.83 times "
                 "faster than scalar RV32IM C on the same 50 MHz board image.")
    fig.text(28, 45, "K7 subgraph latency", 33, weight=700)
    fig.text(28, 78, "Three operators · 50 MHz · vs. scalar RV32IM C", 21, MUTED)
    x0, scale = 211, 4.05
    for tick in range(0, 141, 20):
        x = x0 + tick * scale
        fig.line([(x, 105), (x, 307)], "#9BAAC0" if tick == 0 else LINE, 1.5)
        fig.text(x, 335, str(tick), 19, MUTED, anchor="middle", mono=True)
    fig.text(802, 335, "ms", 19, MUTED, mono=True)
    for case, sample, top in [(0, "Stop", 119), (1, "Left", 228)]:
        cpu = rows[case, "cpu_only"]["total_cycles"]
        hybrid = rows[case, "hybrid"]["total_cycles"]
        fig.text(28, top+19, sample, 24, weight=700)
        fig.text(28, top+58, f"{cpu/hybrid:.2f}×", 22, TEAL, 700, mono=True)
        for cycles, label, color, y in [(cpu, "Scalar C", MUTED, top),
                                        (hybrid, "Hybrid", TEAL, top+41)]:
            ms = cycles / CYCLES_PER_MS
            fig.text(193, y+20, label, 21, MUTED, anchor="end")
            fig.rect(x0, y, ms*scale, 27, color, "none", 4)
            fig.text(x0+ms*scale+9, y+20, f"{ms:.3f}", 20, INK, 700, mono=True)
    fig.text(28, 367, "Same bitstream, firmware and SRAM image", 19, MUTED)
    return fig


def uart_replay(rows):
    transcript = UART.read_text(encoding="ascii").splitlines()
    assert transcript[-1] == "CIM_PASS"
    result_lines = [line.split()[1:] for line in transcript if line.startswith("KWS_RESULT ")]
    assert len(result_lines) == len(rows)
    fields = ("total_cycles", "pw1_cycles", "dw_cycles", "pw2_cycles", "pw1_core_cycles",
              "pw2_core_cycles", "mismatches")

    fig = Figure(660, 339, "Archived K7 results",
                 "Four decoded K7 board timings from the archived UART transcript.")
    fig.rect(2, 2, 656, 335, INK, "#415069", 15)
    fig.text(25, 43, "Archived K7 results", 33, WHITE, 700)
    fig.text(26, 74, "Decoded from recorded UART · 50 MHz · 2026-11-07", 23, PALE_BLUE)
    fig.line([(26, 94), (634, 94)], "#536582", 1.5)
    for x, label, anchor in [(27, "INPUT", "start"), (141, "MODE", "start"),
                             (438, "CYCLES", "end"), (632, "ms", "end")]:
        fig.text(x, 125, label, 24, PALE_BLUE, 700, anchor=anchor, mono=True)
    seen = set()
    for index, words in enumerate(result_lines):
        case, mode, *values, status = (int(word, 16) for word in words)
        key = (case, ("hybrid", "cpu_only")[mode])
        row = rows[key]
        assert key not in seen and values == [row[field] for field in fields] and status == 0
        seen.add(key)
        y = 163 + index*32
        fig.text(27, y, ("Stop", "Left")[case], 25, WHITE, mono=True)
        fig.text(141, y, ("Hybrid", "Scalar C")[mode], 25, WHITE, mono=True)
        cycles = row["total_cycles"]
        fig.text(438, y, f"{cycles:,}", 25, WHITE, anchor="end", mono=True)
        fig.text(632, y, f"{cycles/CYCLES_PER_MS:.5f}", 25, WHITE, anchor="end", mono=True)
    fig.line([(26, 279), (634, 279)], "#536582", 1.5)
    fig.text(27, 312, f"{transcript[-1]}  ·  archived firmware", 23, PALE_TEAL, 700, mono=True)
    return fig


def social(rows):
    ratios = [rows[c, "cpu_only"]["total_cycles"] / rows[c, "hybrid"]["total_cycles"] for c in (0, 1)]
    fig = Figure(1280, 640, "RISC-V CiM Accelerator",
                 f"Digital CiM proxy with open Ibex simulation and approximately {min(ratios):.1f} times "
                 "lower KWS subgraph latency on K7 at 50 MHz.")
    fig.rect(40, 40, 1200, 560, WHITE, radius=26)
    fig.rect(833, 65, 382, 510, INK, "none", 22)
    fig.text(82, 117, "K7 FPGA  /  INT8  /  SYSTEMVERILOG", 21, BLUE, 700, mono=True)
    fig.text(79, 235, "RISC-V CiM", 88, INK, 700)
    fig.text(79, 327, "Accelerator", 88, INK, 700)
    fig.text(84, 392, "Digital macro proxy · Open Ibex simulation", 27, MUTED)
    for x, label, fill in [(85, "CiM PW", BLUE_BG), (331, "CPU DW", TEAL_BG), (577, "CiM PW", BLUE_BG)]:
        fig.rect(x, 477, 189, 64, fill)
        fig.text(x+94, 518, label, 24, weight=700, anchor="middle", mono=True)
    for x in (274, 520):
        fig.line([(x, 509), (x+57, 509)], TEAL, 3, arrow=True)
    fig.text(875, 156, "MEASURED ON K7", 22, "#BBD4FF", 700, mono=True)
    fig.text(866, 321, f"≈{min(ratios):.1f}×", 102, WHITE, 700)
    fig.text(878, 380, "KWS subgraph speedup", 27, WHITE, 700)
    fig.text(878, 426, "50 MHz · Three operators", 23, "#C8D6EA")
    fig.text(878, 463, "vs. same-firmware RV32IM C", 21, "#C8D6EA")
    return fig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", help="installed Chromium channel, such as chrome")
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright

    rows = board_rows()
    figures = [("hero", hero()), ("hero-narrow", hero_narrow()), ("architecture", architecture()),
               ("k7_subgraph_latency", latency(rows)), ("uart-replay", uart_replay(rows)),
               ("social-preview", social(rows))]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel=args.channel)
        for stem, fig in figures:
            svg = fig.save(stem)
            page = browser.new_page(viewport={"width": fig.width, "height": fig.height})
            page.goto(svg.as_uri())
            page.locator("svg").screenshot(path=HERE / f"{stem}.png")
            page.close()
        browser.close()
    png = HERE / "social-preview.png"
    assert png.stat().st_size < 1_000_000
    print("K7 source SHA-256", hashlib.sha256(SOURCE.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
