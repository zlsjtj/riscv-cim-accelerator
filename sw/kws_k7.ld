/* SPDX-License-Identifier: Apache-2.0 */
ENTRY(_start)
SECTIONS
{
    .text 0x80000000 : { KEEP(*(.text.start)) *(.text .text.*) }
    .data 0x80100000 : { *(.rodata .rodata.* .srodata .srodata.*) *(.data .data.*) }
    .bss (NOLOAD) : { *(.bss .bss.* COMMON) }
    _stack_bottom = 0x80100400;
    _stack_top = 0x80101000;
    ASSERT(SIZEOF(.text) <= 0x4000, "KWS firmware exceeds instruction ROM")
    ASSERT(. <= _stack_bottom, "KWS data overlaps reserved stack")
}
