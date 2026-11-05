"""Compile-time SRAM/cache configurations shared by the build and tests."""

VARIANTS = {
    "baseline": (0, 0, "43494d40"),
    "turnaround": (1, 0, "43494d41"),
    "cache": (0, 1, "43494d42"),
    "combined": (1, 1, "43494d43"),
}
DEFAULT_VARIANT = "turnaround"
DEFAULT_K7_VARIANT = "combined"
