# Recorded UART log replay

This is a replay of the archived K7 50 MHz serial output from 2026-11-07.
The board ran both modes for Stop and Left using bitstream `43494d4a`.
[Original UART excerpt](evidence/kws_subgraph/k7_board_uart.txt)

```bash
printf '%s\n' 'Recorded UART log replay'
cat docs/evidence/kws_subgraph/k7_board_uart.txt
```

`KWS_RESULT` fields are hexadecimal and contain sample index, path index,
total cycles, PW1, DW and PW2 window cycles, the two PW core cycle counts,
mismatches and status. Sample indices 0 and 1 are Stop and Left. Path
indices 0 and 1 are hybrid and scalar CPU. The final PASS in the excerpt
is the recorded firmware message. The host separately checked the captured
diagnostic tensors. [Decoded results](evidence/kws_subgraph/k7_board.json)

For a live demonstration, run the open [Ibex smoke test](REPRODUCE.md#quick-start-with-the-open-cpu)
or follow the [K7 setup](KWS_SUBGRAPH.md#复现) on the supported board.
