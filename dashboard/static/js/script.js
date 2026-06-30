/*
 * This file is part of NeuraSelf-UwU.
 * Copyright (c) 2025-Present Routo
 *
 * NeuraSelf-UwU is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * You should have received a copy of the GNU General Public License
 * along with NeuraSelf-UwU. If not, see <https://www.gnu.org/licenses/>.
 */


let currentConfig = {}, originalConfig = null, globalAnalyticsData = null;
let lineChart = null, sessChart = null, cashChart = null, pieChart = null, captchaChart = null;
let currentAccountId = null;
let accountsList = [];

function showToast(message, type = 'success') {
    const toast = document.getElementById('neura-toast');
    const msgEl = document.getElementById('toast-message');
    if (!toast || !msgEl) return;

    msgEl.innerText = message;
    toast.className = `neura-toast show ${type}`;
    
    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

function checkDirty() {
    const bar = document.getElementById('floating-save-bar');
    if (!bar) return;

    const isDirty = JSON.stringify(currentConfig) !== JSON.stringify(originalConfig);
    if (isDirty) {
        bar.classList.add('visible');
    } else {
        bar.classList.remove('visible');
    }
}

window.discardChanges = function() {
    if (originalConfig) {
        currentConfig = JSON.parse(JSON.stringify(originalConfig));
        renderSettings(currentConfig);
        checkDirty();
        showToast("Changes Discarded", "info");
    }
};

async function testSecurity(btn) {
    const q = currentAccountId ? `?id=${currentAccountId}` : '';
    const original = btn.innerHTML;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> TESTING...';
    btn.disabled = true;

    try {
        const res = await fetch(`/api/security/test${q}`, { method: 'POST' });
        const d = await res.json();
        if (d.status === 'success') {
            btn.style.borderColor = 'var(--success)';
            btn.innerHTML = '<i class="fa-solid fa-check"></i> SIGNALS SENT';
        } else {
            alert("Test failed: " + d.message);
            btn.innerHTML = original;
        }
    } catch (e) {
        alert("Request failed");
        btn.innerHTML = original;
    } finally {
        setTimeout(() => {
            btn.innerHTML = original;
            btn.disabled = false;
            btn.style.border = '';
        }, 3000);
    }
}

function nav(id, el) {
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active-view'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.getElementById(id).classList.add('active-view');
    el.classList.add('active');

    const mobileControls = document.querySelector('.mobile-top-controls');
    if (mobileControls) {
        mobileControls.style.display = (id === 'dash') ? 'flex' : 'none';
    }

    if (id === 'dash') {
        document.body.classList.add('active-dash-header');
    } else {
        document.body.classList.remove('active-dash-header');
    }

    if (window.innerWidth <= 768) {
        const sidebar = document.querySelector('.sidebar');
        if (sidebar && sidebar.classList.contains('active')) {
            toggleMobileMenu();
        }
    }

    if (id === 'config') loadConfig();
    if (id === 'history') loadHistory();
}

function toggleMobileMenu() {
    const s = document.querySelector('.sidebar'), o = document.querySelector('.sidebar-overlay'), t = document.querySelector('.mobile-menu-toggle');
    s.classList.toggle('active'); o.classList.toggle('active'); t.classList.toggle('active');
    document.body.style.overflow = s.classList.contains('active') ? 'hidden' : '';
}

async function fetchAccounts() {
    try {
        const res = await fetch('/api/accounts/list');
        const data = await res.json();
        accountsList = data;

        if (data.length > 0) {
            if (!currentAccountId || !data.find(a => a.id === currentAccountId)) {
                currentAccountId = data[0].id;
            }
            renderAccountDropdown();
            updateAccountHeader();
        }
    } catch (e) { console.error("Failed to fetch accounts", e); }
}

function toggleAccountDropdown() {
    const opts = document.getElementById('accountOptions');
    opts.classList.toggle('open');
    const icon = document.querySelector('#accountDropdownHeader i.fa-chevron-down');
    icon.style.transform = opts.classList.contains('open') ? 'rotate(180deg)' : 'rotate(0deg)';
}

function selectAccount(id) {
    currentAccountId = id;
    updateAccountHeader();
    toggleAccountDropdown();
    if (lineChart) lineChart.data.datasets[0].data = Array(30).fill(0);
    
    // Refresh context-dependent views
    if (document.getElementById('config').classList.contains('active-view')) loadConfig();
    update();
}

function updateAccountHeader() {
    const acc = accountsList.find(a => a.id === currentAccountId);
    if (acc) {
        document.getElementById('currentAccountName').innerText = acc.username;
    }
}

function renderAccountDropdown() {
    const container = document.getElementById('accountOptions');
    container.innerHTML = accountsList.map(acc => `
        <div class="custom-option ${acc.id === currentAccountId ? 'selected' : ''}" onclick="selectAccount('${acc.id}')">
            ${acc.avatar ? `<img src="${acc.avatar}" class="account-avatar">` : '<i class="fa-brands fa-discord"></i>'}
            <span>${acc.username}</span>
            ${acc.paused ? '<span style="margin-left:auto; font-size:0.7em; color:var(--warning)">PAUSED</span>' : ''}
        </div>
    `).join('');
}

async function loadConfig() {
    const q = currentAccountId ? `?id=${currentAccountId}` : '';
    const r = await fetch(`/api/settings${q}`);
    currentConfig = await r.json();
    originalConfig = JSON.parse(JSON.stringify(currentConfig));
    renderSettings(currentConfig);
    checkDirty();
}

function renderSettings(cfg) {
    const grid = document.getElementById('settings-grid');
    grid.innerHTML = '';

    const filterBar = document.getElementById('config-filter-bar');
    if (filterBar) {
        filterBar.innerHTML = '';
        
        let categories = [];
        Object.keys(cfg).forEach(key => {
            if (key === 'commands') {
                Object.keys(cfg[key]).forEach(cmd => {
                    categories.push({ id: `cmd-${cmd}`, name: cmd.toUpperCase() });
                });
            } else if (typeof cfg[key] === 'object' && !Array.isArray(cfg[key])) {
                categories.push({ id: `cat-${key}`, name: key.toUpperCase() });
            }
        });
        
        const allBtn = document.createElement('button');
        allBtn.className = 'filter-btn active';
        allBtn.innerHTML = '<i class="fa-solid fa-layer-group"></i> ALL';
        allBtn.onclick = () => filterConfig('all', allBtn);
        filterBar.appendChild(allBtn);
        
        categories.forEach(cat => {
            const btn = document.createElement('button');
            btn.className = 'filter-btn';
            btn.innerText = cat.name;
            btn.onclick = () => filterConfig(cat.id, btn);
            filterBar.appendChild(btn);
        });
    }

    Object.keys(cfg).forEach(key => {
        if (key === 'commands') {
            Object.keys(cfg[key]).forEach(cmd => {
                const card = createModuleCard(cmd.toUpperCase(), cfg[key][cmd], `commands.${cmd}`);
                card.dataset.categoryId = `cmd-${cmd}`;
                grid.appendChild(card);
            });
        } else if (typeof cfg[key] === 'object' && !Array.isArray(cfg[key])) {
            const card = createModuleCard(key.toUpperCase(), cfg[key], key);
            card.dataset.categoryId = `cat-${key}`;
            grid.appendChild(card);
        }
    });

    // Expand all dropdowns by default
    setTimeout(() => {
        document.querySelectorAll('#config .dropdown-content').forEach(el => el.classList.add('active'));
        document.querySelectorAll('#config .module-header i').forEach(el => el.style.transform = 'rotate(180deg)');
        document.querySelectorAll('#config .module-header').forEach(el => el.classList.add('active'));
    }, 50);
}

function filterConfig(categoryId, btnEl) {
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    if (btnEl) btnEl.classList.add('active');
    
    const cards = document.querySelectorAll('#settings-grid .module-card');
    cards.forEach(card => {
        if (categoryId === 'all' || card.dataset.categoryId === categoryId) {
            card.style.display = 'block';
            card.classList.add('fade-in');
        } else {
            card.style.display = 'none';
            card.classList.remove('fade-in');
        }
    });
}

function createModuleCard(title, data, path) {
    const card = document.createElement('div');
    card.className = 'module-card';
    card.innerHTML = `
        <div class="module-header" onclick="toggleDropdown(this, event)">
            <span class="module-title">${title}</span>
            <span class="icon-svg" style="--icon: url('/static/assets/neura_icons/chevron-down.svg');"></span>
        </div>
        <div class="dropdown-content">
            ${renderCategory(data, path)}
        </div>
    `;
    return card;
}

function renderCategory(obj, path) {
    let h = '';
    let keys = Object.keys(obj);
    const isTiers = path.includes('tiers');
    const isTypes = path.includes('types');

    if (isTiers) {
        const tierOrder = ['common', 'uncommon', 'rare', 'epic', 'mythical', 'legendary', 'fabled'];
        keys.sort((a, b) => tierOrder.indexOf(a) - tierOrder.indexOf(b));
    }

    if (isTiers || isTypes) h += '<div class="gem-tier-group">';

    keys.forEach(key => {
        const val = obj[key];
        const fullPath = `${path}.${key}`;

        if ((isTiers || isTypes) && typeof val === 'boolean') {
            h += `
                <div class="gem-tier-item ${key}">
                    <span class="gem-label">${key}</span>
                    <div class="module-toggle ${val ? 'on' : 'off'}" onclick="toggleMod('${fullPath}', this, event)">
                        <span class="icon-svg" style="--icon: url('/static/assets/neura_icons/toggle-${val ? 'on' : 'off'}.svg');"></span> ${val ? 'ON' : 'OFF'}
                    </div>
                </div>
            `;
        } else if (typeof val === 'boolean') {
            h += renderField(fullPath, { l: key, type: 'toggle' }, val);
        } else if (Array.isArray(val) && val.length === 2 && typeof val[0] === 'number') {
            h += renderField(fullPath, { l: key, type: 'range' }, val);
        } else if (typeof val === 'object' && val !== null && !Array.isArray(val)) {
            h += `
                <div class="module-header" onclick="toggleDropdown(this, event)" style="margin-top: 15px; border: none; padding: 10px 0;">
                    <span class="module-title" style="font-size: 0.85rem;">${key}</span>
                    <span class="icon-svg" style="--icon: url('/static/assets/neura_icons/chevron-down.svg');"></span>
                </div>
                <div class="dropdown-content">
                    ${renderCategory(val, fullPath)}
                </div>
            `;
        } else {
            h += renderField(fullPath, { l: key, type: key.includes('url') ? 'password' : 'text' }, val);
        }
    });

    if (isTiers || isTypes) h += '</div>';
    return h;
}

function renderField(path, f, v) {
    if (path === 'commands.shop.itemsToBuy') {
        return renderRingSelection(path, v);
    }
    
    if (f.type === 'toggle') return `<div class="field-group"><label class="field-label">${f.l}</label><div class="module-toggle ${v ? 'on' : 'off'}" onclick="toggleMod('${path}', this, event)"><span class="icon-svg" style="--icon: url('/static/assets/neura_icons/toggle-${v ? 'on' : 'off'}.svg');"></span> ${v ? 'ON' : 'OFF'}</div></div>`;

    if (f.type === 'range' || (Array.isArray(v) && v.length === 2 && typeof v[0] === 'number')) {
        return `
            <div class="field-row">
                ${renderStepper(`${path}.0`, 'Min', v[0])}
                ${renderStepper(`${path}.1`, 'Max', v[1])}
            </div>
        `;
    }

    if (typeof v === 'string' || (Array.isArray(v) && v.length > 0 && typeof v[0] === 'string') || (Array.isArray(v) && v.length === 0)) {
        return `<div class="field-group"><label class="field-label">${f.l}</label><input type="${f.type === 'password' ? 'password' : 'text'}" class="field-input" value="${v}" onclick="event.stopPropagation()" onchange="updateDeepVal('${path}',this.value)"></div>`;
    }
    
    if (typeof v === 'number') {
        let unit = '';
        const lowerLabel = f.l.toLowerCase();
        const isPriority = path.includes('priorities');
        
        if (!isPriority) {
            if (['interval', 'cooldown', 'duration', 'delay', 'min', 'max'].some(tf => lowerLabel.includes(tf))) unit = 's';
            if (lowerLabel.endsWith('_h')) unit = 'h';
            if (lowerLabel.endsWith('_m') || lowerLabel.endsWith('_min')) unit = 'm';
            if (lowerLabel.endsWith('_s') || lowerLabel.endsWith('_sec')) unit = 's';
        }
        
        if (lowerLabel.includes('rate') || lowerLabel.includes('reaction') || lowerLabel.includes('amount') || lowerLabel.includes('chance') || lowerLabel.includes('length')) unit = '';
        
        const finalLabel = (isPriority && f.l === 'radar') ? `${f.l} (1 is lowest)` : f.l;
        return renderStepper(path, finalLabel, v, unit);
    }
    
    return `<div class="field-group"><label class="field-label">${f.l}</label><input type="text" class="field-input" value="${v}" onclick="event.stopPropagation()" onchange="updateDeepVal('${path}',this.value)"></div>`;
}

function renderStepper(path, label, value, unit = '') {
    return `
        <div class="field-group">
            <label class="field-label">${label}</label>
            <div class="stepper-container">
                <button class="stepper-btn" onclick="updateStepper('${path}', -1, event)"><span class="icon-svg" style="--icon: url('/static/assets/neura_icons/minus.svg');"></span></button>
                <input type="number" class="stepper-input" value="${value}" onchange="updateValueFromInput('${path}', this)" onclick="event.stopPropagation()">
                ${unit ? `<span class="stepper-label">${unit}</span>` : ''}
                <button class="stepper-btn" onclick="updateStepper('${path}', 1, event)"><span class="icon-svg" style="--icon: url('/static/assets/neura_icons/plus.svg');"></span></button>
            </div>
        </div>
    `;
}

window.updateValueFromInput = function(path, input) {
    let val = parseFloat(input.value);
    if (isNaN(val)) val = 0;
    
    const parts = path.split('.');
    const lastPart = parts[parts.length - 1];
    if (parts.length > 1 && !isNaN(lastPart)) {
        const index = parseInt(parts.pop());
        updateArrVal(parts.join('.'), index, val);
    } else {
        updateDeepVal(path, val);
    }
};

window.updateStepper = function (path, delta, ev) {
    if (ev) ev.stopPropagation();
    const btn = ev.currentTarget;
    const input = btn.parentElement.querySelector('input');
    let val = parseFloat(input.value) || 0;
    val = Math.max(0, val + delta);
    input.value = val;
    
    const parts = path.split('.');
    const lastPart = parts[parts.length - 1];
    if (parts.length > 1 && !isNaN(lastPart)) {
        const index = parseInt(parts.pop());
        updateArrVal(parts.join('.'), index, val);
    } else {
        updateDeepVal(path, val);
    }
};

function toggleMod(p, el, ev) {
    if (ev) ev.stopPropagation();
    const v = !el.classList.contains('on');
    setDeep(currentConfig, p.split('.'), v);
    el.className = `module-toggle ${v ? 'on' : 'off'}`;
    el.innerHTML = `<span class="icon-svg" style="--icon: url('/static/assets/neura_icons/toggle-${v ? 'on' : 'off'}.svg');"></span> ${v ? 'ON' : 'OFF'}`;
    checkDirty();
}
function updateDeepVal(p, v) {
    let val = v;
    const arrayFields = ['channels', 'targets', 'active_commands', 'ignore_guilds'];
    const fieldName = p.split('.').pop();

    if (arrayFields.includes(fieldName)) {
        val = v.split(',').map(item => item.trim()).filter(item => item !== "");
    } else if (!isNaN(v) && v !== "") {
        val = (v.length < 15) ? Number(v) : v;
    }
    setDeep(currentConfig, p.split('.'), val);
    checkDirty();
}
function updateArrVal(p, i, v) {
    const a = getDeep(currentConfig, p.split('.'));
    if (a) {
        let val = v;
        if (!isNaN(v) && v !== "") {
            val = (v.length < 15) ? Number(v) : v;
        }
        a[i] = val;
    }
}

function saveAllConfigs() {
    const q = currentAccountId ? `?id=${currentAccountId}` : '';
    fetch(`/api/settings${q}`, { 
        method: 'POST', 
        headers: { 'Content-Type': 'application/json' }, 
        body: JSON.stringify(currentConfig) 
    }).then(() => {
        originalConfig = JSON.parse(JSON.stringify(currentConfig));
        checkDirty();
        showToast(`Settings Saved for Account: ${currentAccountId}`);
    });
}

function renderRingSelection(path, selectedId) {
    const ringIds = [1, 2, 3, 4, 5, 6, 7];
    let h = `<div class="field-group"><label class="field-label">SELECT SHOP RING</label><div class="ring-selection-grid">`;
    ringIds.forEach(id => {
        // Handle both integer 1 and array [1]
        const isSelected = selectedId == id || (Array.isArray(selectedId) && selectedId.includes(id));
        const ext = id >= 6 ? 'gif' : 'webp';
        h += `
            <div class="ring-item ${isSelected ? 'selected' : ''}" data-id="${id}" onclick="selectRing('${path}', ${id}, this)">
                <img src="/static/assets/owo_rings/ring_${id}.${ext}" title="Ring ${id}">
            </div>
        `;
    });
    h += `</div></div>`;
    return h;
}

window.selectRing = function(path, id, el) {
    // We treat it as a single integer choice now as per user request
    setDeep(currentConfig, path.split('.'), id);
    
    // UI Update
    el.parentElement.querySelectorAll('.ring-item').forEach(r => r.classList.remove('selected'));
    el.classList.add('selected');
    
    checkDirty();
};

function setDeep(o, p, v) { if (p.length === 1) o[p[0]] = v; else { if (!o[p[0]]) o[p[0]] = {}; setDeep(o[p[0]], p.slice(1), v); } }
function getDeep(o, p) { if (!o || p.length === 0) return o; return getDeep(o[p[0]], p.slice(1)); }

function initDashCharts() {
    try {
        const c2 = document.getElementById('lineChart').getContext('2d');
        lineChart = new Chart(c2, {
            type: 'line',
            data: { labels: Array(30).fill(''), datasets: [{ data: Array(30).fill(0), borderColor: '#ff1f1f', backgroundColor: 'rgba(255,31,31,0.05)', fill: true, pointRadius: 2, pointHoverRadius: 5, tension: 0.3 }] },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: { x: { display: false }, y: { min: 0, suggestedMax: 10, grid: { color: '#222' }, ticks: { color: '#555', font: { size: 10 } } } },
                plugins: { legend: { display: false } }
            }
        });
    } catch (e) { console.warn("Dashboard charts blocked"); }
}

function update() {
    const q = currentAccountId ? `?id=${currentAccountId}` : '';
    fetch(`/api/stats${q}`).then(r => r.json()).then(d => {
        if (!d || Object.keys(d).length === 0) return;
        
        if (d.bot) {
            console.log(`[Stats Update] ${d.bot.username} (#${d.bot.user_id}): ${Object.keys(d.cmd_states || {}).length} commands in scheduler.`);
        }

        if (d.cash) document.getElementById('cash').innerText = d.cash.toLocaleString();
        if (d.uptime) document.getElementById('uptimeDisplay').innerText = d.uptime;
        if (d.logs) renderLogs(d.logs);
        const dot = document.getElementById('statusDot'), lbl = document.getElementById('botStatus');
        lbl.innerText = d.status; dot.className = "ping-dot " + (d.status === "PAUSED" ? "paused" : "");
        
        if (d.status === "PAUSED" && d.security) {
            document.getElementById('securityAlert').style.display = 'flex';
            const msgEl = document.getElementById('captchaMsg');
            if (msgEl) msgEl.innerText = d.security.last_message || "No details available";
        } else {
            document.getElementById('securityAlert').style.display = 'none';
        }

        if (d.chart_data) {
            document.getElementById('huntsToday').innerHTML = `${d.chart_data.hunt} <span style="font-size:0.5em; color:var(--success);" id="huntsSession">(${d.chart_data.session_hunt} this session)</span>`;
            document.getElementById('battlesToday').innerHTML = `${d.chart_data.battle} <span style="font-size:0.5em; color:#3b82f6;" id="battlesSession">(${d.chart_data.session_battle} this session)</span>`;
            document.getElementById('cpm').innerText = d.chart_data.perf_bpm;
            if (document.getElementById('totalOwO')) document.getElementById('totalOwO').innerHTML = `${d.chart_data.owo} <span style="font-size:0.5em; color:#a855f7;" id="owoSession">(${d.chart_data.session_owo} this session)</span>`;
        }

        // Only update these if the security view is active to save resources, 
        // but we'll call renderSecurityCards nonetheless if data is available
        if (d.security) {
            const sc = document.getElementById('sec-captchas'); if (sc) sc.innerText = d.security.captchas;
            const sb = document.getElementById('sec-bans'); if (sb) sb.innerText = d.security.bans;
            const sw = document.getElementById('sec-warns'); if (sw) sw.innerText = d.security.warnings;
        }

        if (lineChart && d.chart_data) {
            lineChart.data.datasets[0].data.push(d.chart_data.perf_bpm);
            lineChart.data.datasets[0].data.shift();
            lineChart.update('none');
        }

        try { renderQuests(d.quest_data, d.next_quest_timer); } catch(e) { console.error("Quest Render Error:", e); }
        try { if (d.cmd_states) renderScheduler(d.cmd_states); } catch(e) { console.error("Scheduler Render Error in update():", e); }
        
        // Fetch ALL accounts' stats for the Security Center list
        try { fetchSecuritySummary(); } catch(e) { console.error("Security Summary Error:", e); }
    });
}

const securityCache = {};
async function fetchSecuritySummary() {
    if (!document.getElementById('security').classList.contains('active-view')) return;
    
    const container = document.getElementById('security-accounts-grid');
    if (!container) return;

    let html = '';
    for (const acc of accountsList) {
        try {
            const res = await fetch(`/api/stats?id=${acc.id}`);
            const d = await res.json();
            if (!d || !d.security) continue;
            
            const isActive = acc.id === currentAccountId;
            const statusColor = d.status === "PAUSED" ? "var(--danger)" : "var(--success)";
            
            html += `
                <div class="sec-account-card ${d.status === "PAUSED" ? 'alert-active' : ''} ${isActive ? 'selected' : ''}" onclick="selectAccount('${acc.id}')">
                    <div class="sec-acc-header">
                        <div class="sec-acc-info">
                            ${acc.avatar ? `<img src="${acc.avatar}" class="account-avatar-lg">` : '<span class="icon-svg" style="--icon: url(\'/static/assets/neura_icons/discord.svg\');"></span>'}
                            <div class="sec-acc-text">
                                <div class="sec-acc-name">${acc.username}</div>
                                <div class="sec-acc-status" style="color:${statusColor}">${d.status}</div>
                            </div>
                        </div>
                        <div class="sec-acc-id">ID: ${acc.id}</div>
                    </div>
                    <div class="sec-acc-stats">
                        <div class="sec-mini-stat">
                            <span class="icon-svg" style="--icon: url('/static/assets/neura_icons/check-to-slot.svg'); background-color: var(--success);"></span>
                            <div class="val">${d.security.captchas}</div>
                            <div class="lbl">Solved</div>
                        </div>
                        <div class="sec-mini-stat">
                            <span class="icon-svg" style="--icon: url('/static/assets/neura_icons/user-slash.svg'); background-color: var(--danger);"></span>
                            <div class="val">${d.security.bans}</div>
                            <div class="lbl">Bans</div>
                        </div>
                        <div class="sec-mini-stat">
                            <span class="icon-svg" style="--icon: url('/static/assets/neura_icons/warning.svg'); background-color: var(--warning);"></span>
                            <div class="val">${d.security.warnings}</div>
                            <div class="lbl">Warns</div>
                        </div>
                    </div>
                </div>
            `;
        } catch (e) {}
    }
    container.innerHTML = html || '<div class="no-data">Initializing system details...</div>';
}
setInterval(update, 1000);

function renderScheduler(states) {
    const list = document.getElementById('schedulerList');
    if (!list) return;

    try {
        const now = Date.now() / 1000;
        const items = Object.entries(states || {}).map(([id, s]) => {
            try {
                const lastRan = s.last_ran || 0;
                const delay = s.delay || 1;
                const nextRun = lastRan + delay;
                const remaining = Math.max(0, nextRun - now);
                return { id, priority: s.priority || 3, delay: delay, in_queue: !!s.in_queue, remaining };
            } catch(e) {
                console.warn(`Error parsing scheduler item ${id}:`, e);
                return null;
            }
        }).filter(item => item !== null);

        items.sort((a, b) => (a.remaining || 0) - (b.remaining || 0));

        if (items.length === 0) {
            list.innerHTML = '<div style="color:#666; font-style:italic; font-size:0.9rem; text-align:center; padding-top:20px;">No scheduled actions</div>';
            return;
        }

    list.innerHTML = items.map(item => {
        const name = item.id.toUpperCase();
        let statusHtml = '';
        let progress = 0;

        if (item.in_queue) {
            statusHtml = `<span style="color:var(--success); font-size:0.8rem; font-weight:bold;"><span class="icon-svg" style="--icon: url('/static/assets/neura_icons/sync.svg'); animation: spin 2s linear infinite;"></span> QUEUED</span>`;
            progress = 100;
        } else {
            const displayTime = Math.ceil(item.remaining);
            const timeStr = displayTime > 60 ? `${Math.floor(displayTime / 60)}m ${displayTime % 60}s` : `${displayTime}s`;
            statusHtml = `<span style="color:#aaa; font-family:var(--font-mono); font-size:0.8rem;">in ${timeStr}</span>`;
            progress = Math.min(100, Math.max(0, 100 - (item.remaining / item.delay) * 100));
        }

        const pColor = item.priority <= 2 ? 'var(--primary)' : '#888';

            return `
                <div style="background:rgba(0,0,0,0.2); border:1px solid rgba(255,255,255,0.05); border-radius:6px; padding:8px 12px; display:flex; flex-direction:column; gap:6px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div style="display:flex; align-items:center; gap:8px;">
                            <span style="width:8px; height:8px; border-radius:50%; background:${pColor}; display:inline-block; box-shadow:0 0 5px ${pColor};"></span>
                            <span style="color:#ddd; font-weight:600; font-size:0.85rem;">${name}</span>
                        </div>
                        ${statusHtml}
                    </div>
                    <div style="height:3px; background:rgba(255,255,255,0.05); border-radius:2px; overflow:hidden;">
                        <div style="height:100%; width:${progress}%; background:${item.in_queue ? 'var(--success)' : '#444'}; transition:width 1s linear;"></div>
                    </div>
                </div>
            `;
        }).join('');
    } catch (e) {
        console.error("Scheduler Render Error:", e);
        list.innerHTML = '<div style="color:#666; font-style:italic; font-size:0.9rem; text-align:center; padding-top:20px;">Render Error (Check Console)</div>';
    }
}

function renderQuests(quests, timer) {
    const list = document.getElementById('questList');
    const timerEl = document.getElementById('nextQuestTimer');
    if (!list || !timerEl) return;

    if (timer) {
        timerEl.innerHTML = `<span class="icon-svg" style="--icon: url('/static/assets/neura_icons/clock.svg'); width: 14px; height: 14px;"></span> Next quest in: ${timer}`;
        timerEl.style.display = 'block';
    } else {
        timerEl.style.display = 'none';
    }

    if (!quests || quests.length === 0) {
        list.innerHTML = '<div style="color:#666; font-style:italic;">No active quests found. Use oquest to refresh.</div>';
        return;
    }

    list.innerHTML = quests.map(q => {
        const percent = Math.min(100, Math.round((q.current / q.total) * 100));
        const color = q.completed ? 'var(--success)' : 'var(--primary)';
        return `
            <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.05); padding:15px; border-radius:8px;">
                <div style="display:flex; justify-content:space-between; margin-bottom:10px; font-size:0.9rem;">
                    <span style="color:#eee;">${q.description}</span>
                    <span style="color:${color}; font-weight:bold;">${q.current}/${q.total}</span>
                </div>
                <div style="height:6px; background:rgba(255,255,255,0.05); border-radius:3px; overflow:hidden;">
                    <div style="width:${percent}%; height:100%; background:${color}; box-shadow: 0 0 10px ${color}44; transition: width 0.5s ease;"></div>
                </div>
            </div>
        `;
    }).join('');
}

const timeFormatter = new Intl.DateTimeFormat('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true
});

let lastLogsHash = '';
function renderLogs(logs) {
    const t = document.getElementById('term'); if (!t) return;


    const currentHash = logs.slice(0, 5).map(l => l.timestamp).join('|');
    if (currentHash === lastLogsHash) return;
    lastLogsHash = currentHash;

    t.innerHTML = logs.map(l => {
        const tagClass = l.type ? `tag-${l.type.toLowerCase()}` : '';
        const localTime = l.timestamp ? timeFormatter.format(new Date(l.timestamp * 1000)) : l.time;
        const botTag = l.bot_name ? `<span style="color:magenta; margin-right:5px;">[${l.bot_name}]</span>` : '';
        return `<div class="history-item ${l.type ? l.type.toLowerCase() : ''}">${botTag}<span class="history-time">[${localTime}]</span> <span class="history-tag ${tagClass}">${l.type}</span> <span class="history-msg">${l.message}</span></div>`;
    }).join('');
}


function toggleDropdown(element, event) {
    if (event) event.stopPropagation();
    const dropdown = element.nextElementSibling;
    const icon = element.querySelector('i');

    if (!dropdown || !dropdown.classList.contains('dropdown-content')) {

        const parent = element.closest('.module-card') || element.closest('.nested-category');
        const altDropdown = parent ? parent.querySelector('.dropdown-content') : null;
        if (altDropdown) {
            altDropdown.classList.toggle('active');
        }
    } else {
        dropdown.classList.toggle('active');
    }

    element.classList.toggle('active');

    const isActive = dropdown ? dropdown.classList.contains('active') : element.classList.contains('active');
    if (icon) {
        icon.style.transform = isActive ? 'rotate(180deg)' : 'rotate(0deg)';
    }
}


function populateSessionDropdown() {
    const select = document.getElementById('session-select');
    const currentVal = select.value;
    select.innerHTML = '<option value="all">ALL SESSIONS IN RANGE</option>';
    if (!globalAnalyticsData || !globalAnalyticsData.sessions) return;


    const sorted = [...globalAnalyticsData.sessions].reverse();
    sorted.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.id;
        opt.innerText = `Session #${s.id}: ${s.date} ${s.start_time}`;
        select.appendChild(opt);
    });


    if (currentVal && Array.from(select.options).some(o => o.value === currentVal)) {
        select.value = currentVal;
    }
}

function renderCharts() {
    if (!globalAnalyticsData) return;
    const filterId = document.getElementById('session-select').value;
    let filtered = filterId === 'all'
        ? globalAnalyticsData.sessions.slice(-30)
        : [globalAnalyticsData.sessions.find(x => String(x.id) === filterId)].filter(Boolean);

    if (filtered.length === 0) return;


    const sctx = document.getElementById('sessionChart').getContext('2d');
    if (sessChart) sessChart.destroy();


    const huntGrad = sctx.createLinearGradient(0, 0, 0, 400);
    huntGrad.addColorStop(0, '#ff1f1f');
    huntGrad.addColorStop(1, '#880000');

    const batGrad = sctx.createLinearGradient(0, 0, 0, 400);
    batGrad.addColorStop(0, '#3b82f6');
    batGrad.addColorStop(1, '#1e3a8a');

    sessChart = new Chart(sctx, {
        type: 'bar',
        data: {
            labels: filtered.map(s => `S${s.id}`),
            datasets: [
                { label: 'Hunts', data: filtered.map(s => s.stats.hunts), backgroundColor: huntGrad, borderRadius: 4 },
                { label: 'Battles', data: filtered.map(s => s.stats.battles), backgroundColor: batGrad, borderRadius: 4 }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { grid: { display: false }, ticks: { color: '#888' } },
                y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#888' } }
            },
            plugins: { legend: { labels: { color: '#ccc' } } }
        }
    });


    const cashEl = document.getElementById('cashHistoryChart');
    if (cashEl && globalAnalyticsData.cash_history) {
        const cctx = cashEl.getContext('2d');
        if (cashChart) cashChart.destroy();
        cashChart = new Chart(cctx, {
            type: 'line',
            data: {
                labels: globalAnalyticsData.cash_history.map(c => c.timestamp.split(' ')[1]),
                datasets: [{
                    label: 'Cash Flow',
                    data: globalAnalyticsData.cash_history.map(c => c.amount),
                    borderColor: '#ffd700',
                    backgroundColor: 'rgba(255, 215, 0, 0.1)',
                    fill: true,
                    tension: 0.4,
                    pointRadius: globalAnalyticsData.cash_history.length > 50 ? 0 : 3
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { display: false },
                    y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#888' } }
                }
            }
        });
    }


    const pieEl = document.getElementById('pieChart');
    if (pieEl) {
        const pctx = pieEl.getContext('2d');
        if (pieChart) pieChart.destroy();


        let totalHunts = 0, totalBattles = 0, totalCaptchas = 0, totalOther = 0;
        filtered.forEach(s => {
            totalHunts += s.stats.hunts;
            totalBattles += s.stats.battles;
            totalCaptchas += s.stats.captchas;
            totalOther += Math.max(0, s.stats.commands - (s.stats.hunts + s.stats.battles + s.stats.captchas));
        });

        pieChart = new Chart(pctx, {
            type: 'doughnut',
            data: {
                labels: ['Hunts', 'Battles', 'Captchas', 'Other'],
                datasets: [{
                    data: [totalHunts, totalBattles, totalCaptchas, totalOther],
                    backgroundColor: ['#ff1f1f', '#3b82f6', '#00d16e', '#888'],
                    borderWidth: 0,
                    hoverOffset: 10
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '70%',
                plugins: {
                    legend: { position: 'right', labels: { color: '#ccc', padding: 20 } }
                }
            }
        });
    }


    const capEl = document.getElementById('captchaSuccessChart');
    if (capEl) {
        const cx = capEl.getContext('2d');
        if (captchaChart) captchaChart.destroy();

        const captchaSuccessRate = 98;
        const failRate = 100 - captchaSuccessRate;

        captchaChart = new Chart(cx, {
            type: 'doughnut',
            data: {
                labels: ['Solved', 'Failed'],
                datasets: [{
                    data: [captchaSuccessRate, failRate],
                    backgroundColor: ['#00d16e', '#ff1f1f'],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '80%',
                plugins: { legend: { display: false }, tooltip: { enabled: false } }
            }
        });
    }
}

async function loadHistory() {
    try {
        const start = document.getElementById('historyStartDate').value;
        const end = document.getElementById('historyEndDate').value;

        let url = '/api/history/analytics';
        const params = new URLSearchParams();
        if (start) params.append('start_date', start);
        if (end) params.append('end_date', end);

        if (params.toString()) {
            url += '?' + params.toString();
        }

        const res = await fetch(url);
        globalAnalyticsData = await res.json();
        const totals = globalAnalyticsData.totals || {};

        document.getElementById('total-sessions').innerText = totals.total_sessions || 0;
        document.getElementById('total-hunts').innerText = (totals.all_time_hunts || 0).toLocaleString();
        document.getElementById('total-battles').innerText = (totals.all_time_battles || 0).toLocaleString();
        document.getElementById('total-cmds').innerText = (totals.all_time_commands || 0).toLocaleString();
        const capSolvedEl = document.getElementById('totalCaptchasSolved');
        if (capSolvedEl) capSolvedEl.innerText = (totals.all_time_captchas || 0).toLocaleString();

        populateSessionDropdown();
        renderCharts();
    } catch (e) {
        console.error("History Error:", e);
    }
}

function resumeBot() { fetch('/api/security', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'resume', id: currentAccountId }) }).then(() => { document.getElementById('securityAlert').style.display = 'none'; update(); }); }
function action(a, el) { fetch('/api/control', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: a, id: currentAccountId }) }).then(() => update()); }

function initDynamicTilt() {
    const cards = document.querySelectorAll('.kpi-card');
    cards.forEach(card => {
        const icon = card.querySelector('.kpi-icon');
        if (!icon) return;
        
        card.addEventListener('mousemove', (e) => {
            const rect = card.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;

            const centerX = rect.width / 2;
            const centerY = rect.height / 2;

            const rotateX = -(y - centerY) / 5;
            const rotateY = (x - centerX) / 5;

            icon.style.transform = `rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateZ(10px)`;
        });

        card.addEventListener('mouseleave', () => {
            icon.style.transform = `rotateX(0deg) rotateY(0deg) translateZ(0px)`;
        });
    });
}

document.addEventListener('DOMContentLoaded', () => {
    initDashCharts();
    fetchAccounts();
    loadConfig();
    initDynamicTilt();
    setInterval(fetchAccounts, 5000);
});
