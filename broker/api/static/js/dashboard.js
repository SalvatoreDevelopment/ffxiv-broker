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

  const mountItemHistory = (canvasId, labels, priceSeries) => {
    const el = document.getElementById(canvasId);
    if (!el || !window.Chart) return;
    try {
      // Destroy previous chart instance on the same canvas if present (Chart.js v3+)
      const prev = Chart.getChart ? Chart.getChart(el) : (el.__chartInstance || null);
      if (prev && typeof prev.destroy === 'function') prev.destroy();
    } catch {}
    const chart = new Chart(el.getContext('2d'), {
      type: 'line',
      data: { labels, datasets: [
        { label: 'Prezzo/Unit (storico recente)', data: priceSeries, borderColor: colors.primary, tension: .3 }
      ]},
      options: {
        responsive: true,
        plugins: { legend: { display: true } },
        scales: { y: { beginAtZero: false } }
      }
    });
    // Fallback linkage for older Chart.js to allow destroy on next call
    try { el.__chartInstance = chart; } catch {}
  };

  const mountScatterROI = (canvasId, items) => {
    const el = document.getElementById(canvasId);
    if (!el || !window.Chart) return;
    const data = (items||[]).map(it => ({
      x: it.sales_per_day ?? 0,
      y: (it.roi ?? 0) * 100,
      r: 4,
      item: it
    }));
    const colors = data.map(d => (d.item.flags||[]).includes('flip') ? '#60a5fa' : '#22c55e');
    new Chart(el.getContext('2d'), {
      type: 'scatter',
      data: { datasets: [{ label: 'ROI vs Vendite/g', data, pointBackgroundColor: colors }] },
      options: {
        responsive: true,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => {
          const it = ctx.raw.item || {}; return `${it.name||('Item '+it.item_id)}: ROI ${(it.roi*100).toFixed(1)}%, SPD ${(it.sales_per_day||0).toFixed(2)}`; } } } },
        scales: { x: { title: { display: true, text: 'Vendite/g' }, beginAtZero: true }, y: { title: { display: true, text: 'ROI %' } } }
      }
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

    // KPI updater using current filters
    const k = {
      deals: document.getElementById('kpi-deals'),
      roi: document.getElementById('kpi-roi'),
      spd: document.getElementById('kpi-spd'),
      flips: document.getElementById('kpi-flips'),
      sat: document.getElementById('kpi-saturo'),
      scanned: document.getElementById('kpi-scanned'),
      bar: document.getElementById('kpi-progress-bar'),
      status: document.getElementById('kpi-status'),
    };
    const readFilters = () => {
      const roiMin = parseFloat(document.getElementById('adv-roi-min')?.value || '0');
      const limit = parseInt(document.getElementById('adv-limit')?.value || '20', 10);
      const minSpd = parseFloat(document.getElementById('adv-min-spd')?.value || '0');
      const minPrice = parseInt(document.getElementById('adv-min-price')?.value || '0', 10);
      const minHistory = parseInt(document.getElementById('adv-min-history')?.value || '0', 10);
      const target = (document.getElementById('adv-target')?.value || 'avg');
      const q = parseFloat(document.getElementById('adv-q')?.value || '');
      const maxC = parseInt(document.getElementById('adv-scan-depth')?.value || '150', 10);
      return { roi_min: roiMin, limit, min_spd: minSpd, min_price: minPrice, min_history: minHistory, target, q: (target==='q' ? q : undefined), max_candidates: maxC };
    };
    const fmtPercent = (v) => `${(v*100).toFixed(1)}%`;
    const updateKpis = async () => {
      try {
        if (k.status) k.status.textContent = 'Scansione…';
        const world = App.getWorld();
        const f = readFilters();
        const res = await App.api.advice(world, f);
        const items = res.items || [];
        const deals = items.length;
        const avgRoi = deals ? items.reduce((s,i)=>s+(i.roi||0),0)/deals : 0;
        const avgSpd = deals ? items.reduce((s,i)=>s+(i.sales_per_day||0),0)/deals : 0;
        const flips = items.filter(i => (i.flags||[]).includes('flip')).length;
        const sat = items.filter(i => (i.flags||[]).includes('saturo')).length;
        if (k.deals) k.deals.textContent = String(deals);
        if (k.roi) k.roi.textContent = fmtPercent(avgRoi);
        if (k.spd) k.spd.textContent = (avgSpd||0).toFixed(2);
        if (k.flips) k.flips.textContent = String(flips);
        if (k.sat) k.sat.textContent = String(sat);
        const scanned = res.scanned ?? 0; const maxC = f.max_candidates ?? 1;
        if (k.scanned) k.scanned.textContent = `${scanned}/${maxC}`;
        if (k.bar) { const p = Math.max(0, Math.min(1, scanned / Math.max(1,maxC))); k.bar.style.width = `${(p*100).toFixed(0)}%`; }
      } catch (e) {
        console.warn('KPI update error', e);
      } finally { if (k.status) k.status.textContent = ''; }
    };
    // Hook filters
    ['adv-roi-min','adv-limit','adv-min-spd','adv-min-price','adv-min-history','adv-target','adv-q','adv-scan-depth']
      .forEach(id => document.getElementById(id)?.addEventListener('change', updateKpis));
    updateKpis();
  };

  return { init, mountMarketOverview, mountMarketTrend, mountItemHistory, mountAllocation, mountScatterROI };
})();
