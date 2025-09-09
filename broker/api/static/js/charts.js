/* Chart helpers (placeholder for future advanced charts) */
window.Charts = (() => {
  const palette = ['#0ea5e9','#22c55e','#f59e0b','#ef4444','#8b5cf6'];
  const pick = (i) => palette[i % palette.length];
  return { palette, pick };
})();

