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
INK, MUTED, BLUE, TEAL, BG, LINE = "#152238", "#526079", "#2563EB", "#0F766E", "#F6F8FB", "#D9E1EC"
WHITE, BLUE_BG, TEAL_BG = "#FFFFFF", "#EAF1FF", "#E4F3F0"
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


def architecture():
    fig = Figure(840, 560, "RISC-V CiM system and KWS handoffs",
                 "A RISC-V CPU controls a shared-SRAM accelerator over MMIO. CPU depthwise "
                 "runs between two separately submitted pointwise tasks and exchanges tensors in SRAM.")
    fig.text(30, 41, "System architecture", 29, weight=700)
    fig.text(30, 69, "Control, shared storage and the three-operator KWS path", 17, MUTED)
    fig.line([(529, 61), (563, 61)], TEAL, 3, arrow=True)
    fig.text(572, 66, "Data", 14, MUTED)
    fig.line([(644, 61), (679, 61)], BLUE, 2.5, dashed=True, arrow=True)
    fig.text(688, 66, "MMIO control", 14, MUTED)

    fig.rect(30, 127, 210, 132, BLUE_BG)
    fig.text(46, 163, "RISC-V CPU", 23, weight=700)
    fig.text(46, 191, "Ibex: public simulation", 16, MUTED)
    fig.text(46, 219, "K7: JYDD CPU", 16, MUTED)
    fig.rect(296, 127, 205, 132, TEAL_BG)
    fig.text(312, 163, "Shared SRAM", 23, weight=700)
    fig.text(312, 191, "Activations A / B", 16, MUTED)
    fig.text(312, 219, "Weights + quantization", 16, MUTED)
    fig.line([(240, 196), (296, 196)], TEAL, 3, arrow=True, both=True)

    fig.rect(558, 98, 252, 272)
    fig.text(574, 127, "CiM accelerator", 22, weight=700)
    for y, label in [(142, "Banked input cache"), (191, "Digital CiM macro proxy"),
                     (240, "Result slots / rebuild INT32"), (289, "Quantize and write back")]:
        fig.rect(573, y, 222, 37, BLUE_BG if y == 191 else BG, radius=7)
        fig.text(684, y+24, label, 15, weight=700 if y == 191 else 400, anchor="middle")
    for y in (179, 228, 277):
        fig.line([(684, y), (684, y+12)], TEAL, 2, arrow=True)
    fig.line([(501, 159), (573, 159)], TEAL, 3, arrow=True)
    fig.line([(573, 309), (530, 309), (530, 228), (501, 228)], TEAL, 3, arrow=True)
    fig.line([(135, 259), (135, 349), (558, 349)], BLUE, 2.5, dashed=True, arrow=True, both=True)
    fig.text(259, 337, "START / DONE", 15, BLUE, mono=True)
    fig.text(684, 350, "Reserve a slot before macro launch", 13, MUTED, anchor="middle")

    fig.text(30, 411, "KWS data in the same SRAM buffers", 21, weight=700)
    for x, label, detail, extra, fill in [
        (30, "PW (op2)", "CiM START #1", "Reads A · tensor23", BLUE_BG),
        (315, "DW (op3)", "RISC-V CPU", "Reads B, writes A", TEAL_BG),
        (600, "PW (op4)", "CiM START #2", "Writes B · tensor26", BLUE_BG),
    ]:
        fig.rect(x, 429, 210, 101, fill)
        fig.text(x+15, 456, label, 21, weight=700)
        fig.text(x+15, 482, detail, 16, MUTED)
        fig.text(x+15, 507, extra, 15, MUTED)
    for x, label in [(240, "B"), (525, "A")]:
        fig.line([(x, 485), (x+75, 485)], TEAL, 3, arrow=True)
        fig.text(x+37, 471, label, 17, TEAL, weight=700, anchor="middle", mono=True)
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
    fig = Figure(840, 433, "K7 end-to-end subgraph latency",
                 "Zero-based bars show CPU and hybrid latency in milliseconds for Stop and Left. "
                 "Both run the same three operators on the same 50 MHz board image.")
    fig.text(30, 41, "K7 subgraph latency", 29, weight=700)
    fig.text(30, 69, "PW (op2) → CPU DW (op3) → PW (op4)  ·  50 MHz", 17, MUTED)
    x0, scale = 174, 4.16
    for tick in range(0, 141, 20):
        x = x0 + tick * scale
        fig.line([(x, 111), (x, 338)], "#9BAAC0" if tick == 0 else LINE, 1.5)
        fig.text(x, 363, str(tick), 15, MUTED, anchor="middle", mono=True)
    fig.text(785, 363, "ms", 15, MUTED, mono=True)
    for case, sample, top in [(0, "Stop", 122), (1, "Left", 244)]:
        fig.text(30, top+15, sample, 20, weight=700)
        for mode, label, color, y in [("cpu_only", "CPU", MUTED, top), ("hybrid", "Hybrid", TEAL, top+43)]:
            ms = rows[case, mode]["total_cycles"] / 50_000
            fig.text(157, y+19, label, 17, MUTED, anchor="end")
            fig.rect(x0, y, ms*scale, 26, color, "none", 4)
            fig.text(x0+ms*scale+10, y+19, f"{ms:.2f}", 16, INK, 700, mono=True)
    fig.text(30, 402, "Same bitstream 43494d4a, ELF and SRAM image · lower is faster", 15, MUTED)
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
    figures = [("architecture", architecture()), ("k7_subgraph_latency", latency(rows)),
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
