"""Compile-time SRAM/cache configurations shared by the build and tests."""

MATRIX_VARIANTS = {
    "baseline": (0, 0, "43494d40"),
    "turnaround": (1, 0, "43494d41"),
    "cache": (0, 1, "43494d42"),
    "combined": (1, 1, "43494d43"),
}
VARIANTS = {**MATRIX_VARIANTS, "banked": (1, 2, "43494d44"),
            "banked-retain": (1, 3, "43494d46")}
DEFAULT_VARIANT = "turnaround"
DEFAULT_K7_VARIANT = "banked"
