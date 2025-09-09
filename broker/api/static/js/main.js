/* Main JavaScript helpers for FFXIV Market Advisor */
window.App = (() => {
  const onReady = (fn) => {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn);
    else fn();
  };

  const withLoading = async (el, fn) => {
    try { el?.classList?.add('loading'); return await fn(); }
    finally { el?.classList?.remove('loading'); }
  };

  const tooltip = (el, text) => {
    el?.setAttribute?.('title', text);
  };

  const notify = (msg, type = 'info') => {
    const n = document.createElement('div');
    n.className = `fixed right-4 top-4 z-50 px-3 py-2 rounded shadow text-white ${
      type === 'error' ? 'bg-red-500' : type === 'success' ? 'bg-emerald-500' : 'bg-slate-800'
    }`;
    n.textContent = msg;
    document.body.appendChild(n);
    setTimeout(() => n.remove(), 2500);
  };

  const fmt = {
    number: (v, opts = {}) => new Intl.NumberFormat('it-IT', opts).format(v ?? 0),
    gil: (v) => new Intl.NumberFormat('it-IT', { maximumFractionDigits: 0 }).format(v ?? 0) + ' gil',
    percent: (v) => `${(v ?? 0).toFixed(2)}%`,
  };

  const getWorld = () => {
    const url = new URL(window.location.href);
    const w = url.searchParams.get('world') || localStorage.getItem('ffxiv_world') || 'Phoenix';
    localStorage.setItem('ffxiv_world', w);
    return w;
  };

  const json = async (url, opts = {}) => {
    const resp = await fetch(url, opts);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return await resp.json();
  };

  const api = {
    advice: (world, { roi_min = 0, limit = 20 } = {}) =>
      json(`/advice?world=${encodeURIComponent(world)}&roi_min=${roi_min}&limit=${limit}`),
    marketItem: (itemId, world) => json(`/market/item/${itemId}?world=${encodeURIComponent(world)}`),
    overview: (world, limit = 8) => json(`/dashboard/data/overview?world=${encodeURIComponent(world)}&limit=${limit}`),
    worlds: (dataCenter = null) => {
      const url = dataCenter ? 
        `/dashboard/data/worlds?data_center=${encodeURIComponent(dataCenter)}` : 
        `/dashboard/data/worlds`;
      return json(url);
    },
    dataCenters: () => json(`/dashboard/data/data-centers`),
  };

  onReady(async () => {
    // Tooltips via data-notify
    document.querySelectorAll('[data-notify]')?.forEach((btn) => {
      btn.addEventListener('click', () => notify(btn.getAttribute('data-notify')));
    });

    // Data Center and World selectors in navbar
    const dataCenterSelect = document.getElementById('data-center-select');
    const worldSelect = document.getElementById('world-select');
    
    if (dataCenterSelect && worldSelect) {
      try {
        // Carica Data Centers
        const dataCentersData = await api.dataCenters();
        const dataCenters = Array.isArray(dataCentersData.data_centers) ? dataCentersData.data_centers : [];
        
        dataCenterSelect.innerHTML = '<option value="">Seleziona...</option>' + 
          dataCenters.map(dc => `<option value="${dc}">${dc}</option>`).join('');
        
        // Handler per cambio Data Center
        dataCenterSelect.addEventListener('change', async () => {
          const selectedDC = dataCenterSelect.value;
          
          if (selectedDC) {
            try {
              const worldsData = await api.worlds(selectedDC);
              const worlds = Array.isArray(worldsData.worlds) ? worldsData.worlds : [];
              
              worldSelect.innerHTML = '<option value="">Seleziona World...</option>' +
                worlds.map(w => `<option value="${w}">${w}</option>`).join('');
              worldSelect.disabled = false;
              
              // Reset world selection
              worldSelect.value = '';
              localStorage.removeItem('ffxiv_world');
            } catch (error) {
              console.error('Error loading worlds:', error);
              worldSelect.innerHTML = '<option value="">Errore caricamento</option>';
              worldSelect.disabled = true;
            }
          } else {
            worldSelect.innerHTML = '<option value="">Seleziona Data Center</option>';
            worldSelect.disabled = true;
            worldSelect.value = '';
            localStorage.removeItem('ffxiv_world');
          }
        });
        
        // Handler per cambio World
        worldSelect.addEventListener('change', () => {
          const selectedWorld = worldSelect.value;
          if (selectedWorld) {
            localStorage.setItem('ffxiv_world', selectedWorld);
            const url = new URL(window.location.href);
            url.searchParams.set('world', selectedWorld);
            window.location.assign(url.toString());
          }
        });
        
        // Carica stato salvato
        const savedWorld = localStorage.getItem('ffxiv_world');
        if (savedWorld) {
          // Trova il Data Center del world salvato
          for (const [dc, worlds] of Object.entries({
            "Light": ["Phoenix", "Shiva", "Zodiark", "Twintania", "Alpha", "Raiden"],
            "Chaos": ["Cerberus", "Louisoix", "Moogle", "Omega", "Ragnarok", "Sagittarius"],
            "Elemental": ["Aegis", "Atomos", "Carbuncle", "Garuda", "Gungnir", "Kujata", "Ramuh", "Tonberry", "Typhon", "Unicorn"],
            "Gaia": ["Alexander", "Bahamut", "Durandal", "Fenrir", "Ifrit", "Ridill", "Tiamat", "Ultima", "Valefor", "Yojimbo", "Zeromus"],
            "Mana": ["Anima", "Asura", "Belias", "Chocobo", "Hades", "Ixion", "Mandragora", "Masamune", "Pandaemonium", "Shinryu", "Titan"],
            "Meteor": ["Balmung", "Brynhildr", "Coeurl", "Diabolos", "Goblin", "Malboro", "Mateus", "Seraph", "Ultros"],
            "Dynamis": ["Halicarnassus", "Maduin", "Marilith", "Seraph"],
            "Crystal": ["Balmung", "Brynhildr", "Coeurl", "Diabolos", "Goblin", "Malboro", "Mateus", "Seraph", "Ultros"],
            "Aether": ["Adamantoise", "Cactuar", "Faerie", "Gilgamesh", "Jenova", "Midgardsormr", "Sargatanas", "Siren"],
            "Primal": ["Behemoth", "Excalibur", "Exodus", "Famfrit", "Hyperion", "Lamia", "Leviathan", "Ultros"],
            "Materia": ["Bismarck", "Ravana", "Sephirot", "Sophia", "Zurvan"]
          })) {
            if (worlds.includes(savedWorld)) {
              dataCenterSelect.value = dc;
              dataCenterSelect.dispatchEvent(new Event('change'));
              setTimeout(() => {
                worldSelect.value = savedWorld;
              }, 100);
              break;
            }
          }
        }
        
      } catch (error) {
        console.error('Error initializing selectors:', error);
        dataCenterSelect.innerHTML = '<option value="">Errore caricamento</option>';
        worldSelect.innerHTML = '<option value="">Errore caricamento</option>';
      }
    }
  });

  return { onReady, withLoading, tooltip, notify, fmt, getWorld, api };
})();
