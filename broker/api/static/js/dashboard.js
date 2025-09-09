/* Dashboard-specific logic and Chart.js mounts */
window.Dashboard = (() => {
  const rand = (n=12, base=100) => Array.from({length:n}, () => Math.round(Math.random()*base));

  const colors = {
    primary: '#0ea5e9',
    secondary: '#22c55e',
    accent: '#f59e0b',
  };

  const mountMarketOverview = (canvasId, labels, avgSeries, lowSeries) => {
    const el = document.getElementById(canvasId);
    if (!el || !window.Chart) return;
    new Chart(el.getContext('2d'), {
      type: 'line',
      data: { labels, datasets: [
        { label: 'Prezzo Medio 7g', data: avgSeries, borderColor: colors.primary, tension: .35 },
        { label: 'Prezzo Minimo', data: lowSeries, borderColor: colors.secondary, tension: .35 },
      ] },
      options: { responsive: true, plugins: { legend: { display: true } }, scales: { y: { beginAtZero: true } } }
    });
  };

  const mountMarketTrend = (canvasId, labels, salesSeries) => {
    const el = document.getElementById(canvasId);
    if (!el || !window.Chart) return;
    new Chart(el.getContext('2d'), {
      type: 'bar',
      data: { labels, datasets: [
        { label: 'Vendite/giorno (7g)', data: salesSeries, backgroundColor: colors.accent }
      ]},
      options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
    });
  };

  const mountAllocation = (canvasId) => {
    const el = document.getElementById(canvasId);
    if (!el || !window.Chart) return;
    new Chart(el.getContext('2d'), {
      type: 'doughnut',
      data: { labels: ['Materie Prime','Consumabili','Equip'], datasets: [
        { data: [45, 30, 25], backgroundColor: [colors.primary, colors.secondary, colors.accent] }
      ]},
      options: { responsive: true, plugins: { legend: { position: 'bottom' } } }
    });
  };

  const init = async () => {
    // ROI calculator simple logic
    const cost = document.getElementById('roi-cost');
    const price = document.getElementById('roi-price');
    const btn = document.getElementById('roi-calc');
    const out = document.getElementById('roi-result');
    if (btn) {
      btn.addEventListener('click', () => {
        const c = parseFloat(cost?.value || '0');
        const p = parseFloat(price?.value || '0');
        const roi = c > 0 ? ((p - c) / c) * 100 : 0;
        out.textContent = isFinite(roi) ? `${roi.toFixed(2)}%` : '—';
      });
    }

    // Load overview chart with real data
    try {
      const world = App.getWorld();
      const ov = await App.api.overview(world, 8);
      const items = ov.items || [];
      const labels = items.map(s => s.name || `Item ${s.item_id}`);
      const avgSeries = items.map(s => s.avg_price_7d ?? 0);
      const lowSeries = items.map(s => s.lowest ?? 0);
      mountMarketOverview('market-overview-chart', labels, avgSeries, lowSeries);
    } catch (e) {
      console.warn('Market overview data error', e);
    }
  };

  return { init, mountMarketOverview, mountMarketTrend, mountAllocation };
})();
