/* SPDX-License-Identifier: Apache-2.0 */
OUTPUT_ARCH(riscv)
ENTRY(_start)
PHDRS
{
    program PT_LOAD FLAGS(5);
    fixture PT_LOAD FLAGS(6);
}
SECTIONS
{
    .text 0x00100080 : {
        KEEP(*(.text.start))
        *(.text .text.*)
        *(.rodata .rodata.* .srodata .srodata.*)
    } :program
    ASSERT(. <= 0x00110000, "Firmware overlaps the chain fixture")
    .fixture 0x00110000 : { KEEP(*(.fixture)) } :fixture
    ASSERT(SIZEOF(.fixture) == 0x10000, "Chain fixture must be 64 KiB")
    _stack_top = 0x00124000;
}
