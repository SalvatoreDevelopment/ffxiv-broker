/* Advice list UI (Saddlebag-like) */
window.AdviceUI = (() => {
  const lsKey = 'ffxiv_watchlist';
  const cfgKey = 'ffxiv_advice_cfg';

  const loadWatchlist = () => { try { return JSON.parse(localStorage.getItem(lsKey) || '[]'); } catch { return []; } };
  const saveWatchlist = (items) => localStorage.setItem(lsKey, JSON.stringify(items));
  const loadCfg = () => { try { return JSON.parse(localStorage.getItem(cfgKey) || '{}'); } catch { return {}; } };
  const saveCfg = (cfg) => localStorage.setItem(cfgKey, JSON.stringify(cfg));

  const addToWatchlist = (item) => {
    const wl = loadWatchlist();
    if (!wl.find((x) => x.item_id === item.item_id)) {
      wl.push({ item_id: item.item_id, name: item.name || `Item ${item.item_id}` });
      saveWatchlist(wl);
      App.notify('Aggiunto alla watchlist', 'success');
    } else {
      App.notify('Già presente in watchlist');
    }
  };

  const showDetails = async (itemId, row) => {
    try {
      const world = App.getWorld();
      const raw = await App.json(`/market/item/${itemId}/raw?world=${encodeURIComponent(world)}`);
      const history = Array.isArray(raw.recentHistory) ? raw.recentHistory : [];
      const labels = history.map(h => new Date(h.timestamp * 1000).toLocaleDateString());
      const prices = history.map(h => h.pricePerUnit);
      window.Dashboard?.mountItemHistory?.('adv-chart', labels, prices);
      document.getElementById('adv-details')?.classList?.remove('hidden');
      const t = document.getElementById('adv-details-title'); if (t) t.textContent = `${row?.name || 'Item ' + itemId} (#${itemId})`;
      const low = Array.isArray(raw.listings) && raw.listings.length ? Math.min(...raw.listings.map(l => l.pricePerUnit)) : null;
      const elLow = document.getElementById('adv-d-lowest'); if (elLow) elLow.textContent = low != null ? App.fmt.gil(low) : '-';
      const elTgt = document.getElementById('adv-d-target'); if (elTgt) elTgt.textContent = row?.price != null ? App.fmt.gil(row.price) : '-';
      const elSpd = document.getElementById('adv-d-spd'); if (elSpd) elSpd.textContent = row?.sales_per_day != null ? String(row.sales_per_day.toFixed(2)) : '-';

      // Fill listings table (top 10)
      const lbody = document.getElementById('adv-listings-body');
      if (lbody) {
        const listings = Array.isArray(raw.listings) ? raw.listings.slice(0, 10) : [];
        lbody.innerHTML = listings.map(l => `<tr><td>${App.fmt.gil(l.pricePerUnit)}</td><td>${l.quantity}</td><td>${l.hq ? 'HQ' : 'NQ'}</td></tr>`).join('');
      }

      // Arbitrage DC: compare lowest across worlds in selected DC
      const dcSel = document.getElementById('data-center-select');
      const arbBody = document.getElementById('adv-arb-body');
      if (dcSel && dcSel.value && arbBody) {
        try {
          const worldsData = await App.api.worlds(dcSel.value);
          const worlds = Array.isArray(worldsData.worlds) ? worldsData.worlds : [];
          const results = [];
          let idx = 0;
          const worker = async () => {
            while (idx < worlds.length) {
              const w = worlds[idx++];
              try {
                const r = await App.json(`/market/item/${itemId}/raw?world=${encodeURIComponent(w)}`);
                const lows = Array.isArray(r.listings) && r.listings.length ? Math.min(...r.listings.map(x => x.pricePerUnit)) : null;
                results.push({ world: w, lowest: lows });
              } catch {}
            }
          };
          await Promise.all([worker(), worker(), worker()]);
          const vals = results.map(r => r.lowest).filter(v => v != null).sort((a,b)=>a-b);
          const median = vals.length ? vals[Math.floor(vals.length/2)] : null;
          results.sort((a,b)=> (a.lowest??Infinity) - (b.lowest??Infinity));
          arbBody.innerHTML = results.map(r => {
            const delta = (median!=null && r.lowest!=null) ? (((r.lowest - median)/median)*100) : null;
            const cur = r.world === world ? 'font-semibold' : '';
            return `<tr class="${cur}"><td>${r.world}</td><td>${r.lowest!=null?App.fmt.gil(r.lowest):'-'}</td><td>${delta!=null?delta.toFixed(1)+'%':'-'}</td></tr>`;
          }).join('');
        } catch (e) { arbBody.innerHTML = '<tr><td colspan="3" class="text-slate-500">N/D</td></tr>'; }
      }

      // Tabs behavior
      const tabs = document.querySelectorAll('.tab');
      const panels = document.querySelectorAll('.tab-panel');
      tabs.forEach(t => t.addEventListener('click', () => {
        tabs.forEach(x => x.classList.remove('active'));
        panels.forEach(p => p.classList.remove('active'));
        t.classList.add('active');
        const target = t.getAttribute('data-tab');
        document.getElementById(target==='arb' ? 'adv-tab-arb' : 'adv-tab-listings')?.classList.add('active');
      }));
    } catch (e) {
      console.warn('Dettagli item error', e);
    }
  };

  let currentRows = [];
  let sortKey = 'score';
  let sortDir = 'desc';
  let currentOffset = 0;

  const sortRows = (rows) => {
    const r = [...rows];
    const keyMap = { roi: (x)=>x.roi||0, spd: (x)=>x.sales_per_day||0, score: (x)=>x.score||0, item: (x)=>x.name||('Item '+x.item_id), risk: (x)=>x.risk||'' };
    const getter = keyMap[sortKey] || keyMap.score;
    r.sort((a,b)=>{
      const va = getter(a), vb = getter(b);
      if (typeof va === 'number' && typeof vb === 'number') return sortDir==='asc' ? va-vb : vb-va;
      return sortDir==='asc' ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va));
    });
    return r;
  };

  const render = (tableId, rows) => {
    const table = document.getElementById(tableId);
    if (!table) return;
    const tbody = table.querySelector('tbody');
    if (!tbody) return;
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="text-center text-slate-500">Nessun risultato</td></tr>';
      return;
    }
    currentRows = rows;
    const sorted = sortRows(currentRows);
    tbody.innerHTML = '';
    sorted.forEach((r) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td class="whitespace-nowrap">${r.name || 'Item ' + r.item_id}</td>
        <td>${(r.roi * 100).toFixed(1)}%</td>
        <td>${(r.sales_per_day ?? 0).toFixed(2)}</td>
        <td>${(r.score ?? 0).toFixed(2)}</td>
        <td>${(r.flags || []).map((f) => `<span class='badge'>${f}</span>`).join(' ')}</td>
        <td>${r.risk || '-'}</td>
        <td class="text-right">
          <button class="btn btn-xs" data-detail="${r.item_id}">Dettagli</button>
          <button class="btn btn-xs" data-universalis="${r.item_id}">Universalis</button>
          <button class="btn btn-xs" data-add="${r.item_id}">Watch</button>
        </td>`;
      tr.setAttribute('data-row-id', String(r.item_id));
      tbody.appendChild(tr);
    });
    tbody.querySelectorAll('[data-add]')?.forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const id = parseInt(btn.getAttribute('data-add') || '0', 10);
        const item = currentRows.find((x) => x.item_id === id);
        if (item) addToWatchlist(item);
      });
    });
    // Dedicated details buttons
    tbody.querySelectorAll('[data-detail]')?.forEach((btn) => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const id = parseInt(btn.getAttribute('data-detail') || '0', 10);
        if (!id) return;
        await showDetails(id, currentRows.find(x => x.item_id === id));
      });
    });
    // Universalis buttons (open in new tab)
    tbody.querySelectorAll('[data-universalis]')?.forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const id = parseInt(btn.getAttribute('data-universalis') || '0', 10);
        const world = App.getWorld();
        if (id) window.open(`https://universalis.app/market/${id}`, '_blank');
      });
    });

    const thead = table.querySelector('thead');
    thead?.querySelectorAll('th[data-sort]')?.forEach(th => {
      th.addEventListener('click', () => {
        const key = th.getAttribute('data-sort');
        if (!key) return;
        sortDir = (sortKey === key && sortDir==='desc') ? 'asc' : 'desc';
        sortKey = key;
        render(tableId, currentRows);
      });
    });
  };

  const mount = (tableId, cfg = {}) => {
    const world = App.getWorld();
    const roiMinInput = document.getElementById(cfg.roiMinInput || 'adv-roi-min');
    const limitInput = document.getElementById(cfg.limitInput || 'adv-limit');
    const refreshBtn = document.getElementById(cfg.refreshBtn || 'adv-refresh');
    const exportLink = document.getElementById(cfg.exportLink || 'adv-export');
    const minSpdInput = document.getElementById('adv-min-spd');
    const minPriceInput = document.getElementById('adv-min-price');
    const minHistInput = document.getElementById('adv-min-history');
    const targetSel = document.getElementById('adv-target');
    const qInput = document.getElementById('adv-q');
    const scanDepthInput = document.getElementById('adv-scan-depth');
    const chips = document.getElementById('adv-chips');
    const resetBtn = document.getElementById('adv-reset');
    const moreBtn = document.getElementById('adv-more');
    const expertChk = document.getElementById('adv-expert');
    const advAdvanced = document.getElementById('adv-advanced');

    const syncQState = () => { if (!targetSel || !qInput) return; qInput.disabled = targetSel.value !== 'q'; };
    syncQState();
    targetSel?.addEventListener('change', () => { syncQState(); load(); });

    // Restore saved config if present
    const saved = loadCfg();
    if (saved && typeof saved === 'object') {
      if (saved.roi_min != null) roiMinInput.value = saved.roi_min;
      if (saved.limit != null) limitInput.value = saved.limit;
      if (saved.min_spd != null) minSpdInput.value = saved.min_spd;
      if (saved.min_price != null) minPriceInput.value = saved.min_price;
      if (saved.min_history != null) minHistInput.value = saved.min_history;
      if (saved.target) targetSel.value = saved.target;
      if (saved.q != null) qInput.value = saved.q;
      if (saved.max_candidates != null) scanDepthInput.value = saved.max_candidates;
      if (saved.offset != null) currentOffset = parseInt(saved.offset, 10) || 0;
      if (saved.expert) expertChk.checked = true;
      syncQState();
    }
    const applyExpert = () => { advAdvanced?.classList?.toggle('hidden', !expertChk?.checked); };
    applyExpert();
    expertChk?.addEventListener('change', () => { saveCfg({ ...(loadCfg()||{}), expert: expertChk.checked }); applyExpert(); if (!expertChk.checked) { /* non-expert fallback will run */ } });

    // Table is always compact
    (() => { const el = document.getElementById(tableId)?.closest('table') || document.getElementById(tableId); el?.classList?.add('table-compact'); })();

    const renderChips = (cfg, note) => {
      if (!chips) return;
      const items = [];
      items.push(`<span class='badge'>ROI ≥ ${cfg.roi_min}</span>`);
      if (cfg.min_spd>0) items.push(`<span class='badge'>Vendite/g ≥ ${cfg.min_spd}</span>`);
      if (cfg.min_price>0) items.push(`<span class='badge'>Prezzo ≥ ${cfg.min_price}</span>`);
      if (cfg.min_history>0) items.push(`<span class='badge'>Storico ≥ ${cfg.min_history}</span>`);
      items.push(`<span class='badge'>Target: ${cfg.target}${cfg.target==='q' && cfg.q!=null ? ' q='+cfg.q : ''}</span>`);
      items.push(`<span class='badge'>Scan: ${cfg.max_candidates}</span>`);
      if (note) items.push(`<span class='badge'>${note}</span>`);
      chips.innerHTML = items.join(' ');
    };

    const load = async (append=false) => {
      const targetEl = document.getElementById('adv-table')?.closest('.card') || document.getElementById('adv-table');
      const spinner = document.getElementById('adv-loading');
      const roiMin = parseFloat(roiMinInput?.value || '0');
      const limit = parseInt(limitInput?.value || '20', 10);
      const minSpd = parseFloat(minSpdInput?.value || '0');
      const minPrice = parseInt(minPriceInput?.value || '0', 10);
      const minHistory = parseInt(minHistInput?.value || '0', 10);
      const target = (targetSel?.value || 'avg');
      const q = parseFloat(qInput?.value || '');
      const maxC = parseInt(scanDepthInput?.value || '150', 10);
      const expert = !!expertChk?.checked;
      saveCfg({ roi_min: roiMin, limit, min_spd: minSpd, min_price: minPrice, min_history: minHistory, target, q: (target==='q' ? q : null), max_candidates: maxC, offset: currentOffset, expert });
      renderChips({ roi_min: roiMin, min_spd: minSpd, min_price: minPrice, min_history: minHistory, target, q: (target==='q' ? q : null), max_candidates: maxC });
      try {
        const res = await App.withLoading(targetEl, async () => {
          spinner?.classList?.remove('hidden');
          let r0 = await App.api.advice(world, { roi_min: roiMin, limit, min_spd: minSpd, min_price: minPrice, min_history: minHistory, target, q: (target==='q' ? q : undefined), max_candidates: maxC, offset: currentOffset });
          let items0 = r0.items || [];
          let note = '';
          if (!expert && (!items0 || items0.length === 0)) {
            const f1 = await App.api.advice(world, { roi_min: roiMin, limit, min_spd: minSpd, min_price: minPrice, min_history: minHistory, target, q: (target==='q'?q:undefined), max_candidates: Math.max(maxC, 500), offset: 0 });
            if (f1.items && f1.items.length) { r0 = f1; items0 = f1.items; note = 'fallback: profondità'; }
          }
          if (!expert && (!items0 || items0.length === 0)) {
            const f2 = await App.api.advice(world, { roi_min: Math.min(roiMin, 0.05), limit, min_spd: 0.2, min_price: 0, min_history: 0, target: 'avg', max_candidates: Math.max(maxC, 500), offset: 0 });
            if (f2.items && f2.items.length) { r0 = f2; items0 = f2.items; note = 'fallback: filtri ridotti'; }
          }
          if (!expert && (!items0 || items0.length === 0)) {
            const f3 = await App.api.advice(world, { roi_min: 0.0, limit, min_spd: 0.0, min_price: 0, min_history: 0, target: 'avg', max_candidates: 1000, offset: 0 });
            if (f3.items && f3.items.length) { r0 = f3; items0 = f3.items; note = 'fallback: esplorazione'; }
          }
          if (note) {
            renderChips({ roi_min: roiMin, min_spd: minSpd, min_price: minPrice, min_history: minHistory, target, q: (target==='q' ? q : null), max_candidates: maxC }, note);
          }
          return { r: r0, items: items0 };
        });
        let newItems = res.items;
        const merged = append ? (currentRows.concat(newItems)) : newItems;
        render(tableId, merged);
        document.dispatchEvent(new CustomEvent('advice:loaded', { detail: { items: merged } }));
        if (exportLink) {
          const qp = new URLSearchParams({ world, roi_min: String(roiMin), limit: String(limit), min_spd: String(minSpd), min_price: String(minPrice), min_history: String(minHistory), target, max_candidates: String(maxC), offset: String(currentOffset) });
          if (target === 'q' && !Number.isNaN(q)) qp.set('q', String(q));
          const url = `/export/excel/advice?${qp.toString()}`;
          exportLink.setAttribute('href', url);
        }
      } catch (e) {
        console.warn('Advice load error', e);
        render(tableId, []);
      } finally { spinner?.classList?.add('hidden'); }
    };

    refreshBtn?.addEventListener('click', () => { currentOffset = 0; load(false); });
    roiMinInput?.addEventListener('change', load);
    limitInput?.addEventListener('change', load);
    minSpdInput?.addEventListener('change', load);
    minPriceInput?.addEventListener('change', load);
    minHistInput?.addEventListener('change', load);
    qInput?.addEventListener('change', load);
    scanDepthInput?.addEventListener('change', () => { currentOffset = 0; load(false); });
    resetBtn?.addEventListener('click', () => {
      currentOffset = 0;
      // Balanced preset
      roiMinInput.value = 0.2;
      minSpdInput.value = 1.0;
      minPriceInput.value = 1500;
      minHistInput.value = 10;
      targetSel.value = 'median';
      qInput.value = '';
      expertChk.checked = false; applyExpert();
      load(false);
    });
    // Preset buttons click -> auto load
    document.getElementById('adv-presets')?.querySelectorAll('[data-preset]')?.forEach(btn => {
      btn.addEventListener('click', () => {
        const p = btn.getAttribute('data-preset');
        currentOffset = 0;
        if (p === 'conservative') { roiMinInput.value = 0.3; minSpdInput.value = 1.5; minPriceInput.value = 3000; minHistInput.value = 15; targetSel.value='median'; qInput.value=''; }
        else if (p === 'balanced') { roiMinInput.value = 0.2; minSpdInput.value = 1.0; minPriceInput.value = 1500; minHistInput.value = 10; targetSel.value='median'; qInput.value=''; }
        else { roiMinInput.value = 0.1; minSpdInput.value = 0.5; minPriceInput.value = 500; minHistInput.value = 0; targetSel.value='avg'; qInput.value=''; }
        expertChk.checked = false; applyExpert();
        load(false);
      });
    });
    moreBtn?.addEventListener('click', () => { const step = parseInt(scanDepthInput?.value || '150', 10); currentOffset += (isFinite(step)? step : 150); load(true); });
    load();
  };

  return { mount };
})();
