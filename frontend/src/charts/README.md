# Charts (T019)

- `TimeSeriesChart.vue`: ECharts line/scatter chart with inside and slider zoom, reference bands, event markers and alarm periods. It emits `zoom` with the visible time range.
- `useSeries.ts`: loads the overview of a signal, then the visible range again after each zoom. The server downsamples (min/max per bucket, at most 2000 points); the browser never thins data itself.
- `merge.ts`: splices the zoomed detail into the overview, with gaps at the seams.
- `overlays.ts`: maintenance markers, alarm periods and the verified healthy reference band (mean ±2σ).
- `DownsampleNote.vue`: says whether the chart shows a downsample or every point, and exports the full-resolution range as CSV.

Performance is checked end to end in `tests/e2e/charts.spec.ts` against the demo server's SIMULATED 1.1M-point bench signal.
