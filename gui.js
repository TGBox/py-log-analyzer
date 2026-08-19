let logData = null;
let activeEntry = null;
let activeFilter = 'all';
let activeEntityFilter = null;
let collapseNoise = true;

document.addEventListener('DOMContentLoaded', () => {
    initEvents();
    loadSampleLog();
});

function initEvents() {
    // Buttons
    document.getElementById('btn-load-sample').addEventListener('click', loadSampleLog);
    document.getElementById('file-input').addEventListener('change', handleFileSelect);
    
    // Search
    const searchInput = document.getElementById('search-input');
    const btnClearSearch = document.getElementById('btn-clear-search');
    
    searchInput.addEventListener('input', (e) => {
        const val = e.target.value.trim();
        btnClearSearch.style.display = val ? 'block' : 'none';
        renderTimeline();
    });
    
    btnClearSearch.addEventListener('click', () => {
        searchInput.value = '';
        btnClearSearch.style.display = 'none';
        renderTimeline();
    });

    // Chips
    document.querySelectorAll('.filter-chips .chip').forEach(chip => {
        chip.addEventListener('click', (e) => {
            document.querySelectorAll('.filter-chips .chip').forEach(c => c.classList.remove('active'));
            e.target.classList.add('active');
            activeFilter = e.target.dataset.filter;
            renderTimeline();
        });
    });

    // Remove Entity Filter
    document.getElementById('btn-remove-entity-filter').addEventListener('click', () => {
        activeEntityFilter = null;
        document.getElementById('entity-active-badge').style.display = 'none';
        renderTimeline();
    });

    // Noise toggle
    document.getElementById('toggle-collapse-noise').addEventListener('change', (e) => {
        collapseNoise = e.target.checked;
        renderTimeline();
    });

    // Inspector Tabs
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            btn.classList.add('active');
            const tabName = btn.dataset.tab;
            document.getElementById(`tab-${tabName}`).classList.add('active');
        });
    });

    // Copy Raw
    document.getElementById('btn-copy-raw').addEventListener('click', () => {
        if (activeEntry && activeEntry.raw) {
            navigator.clipboard.writeText(activeEntry.raw);
            alert("Rohdaten in Zwischenablage kopiert!");
        }
    });

    // Resizer Split-Screen
    initResizer();
}

function initResizer() {
    const resizer = document.getElementById('resizer');
    const masterPanel = document.querySelector('.master-panel');
    let isResizing = false;

    resizer.addEventListener('mousedown', (e) => {
        isResizing = true;
        document.body.style.cursor = 'col-resize';
    });

    document.addEventListener('mousemove', (e) => {
        if (!isResizing) return;
        const containerWidth = document.querySelector('.main-split-container').clientWidth;
        const newMasterWidth = (e.clientX / containerWidth) * 100;
        if (newMasterWidth > 20 && newMasterWidth < 80) {
            masterPanel.style.flex = `${newMasterWidth}`;
        }
    });

    document.addEventListener('mouseup', () => {
        isResizing = false;
        document.body.style.cursor = 'default';
    });
}

function loadSampleLog() {
    fetch('/api/sample')
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                alert(data.error);
                return;
            }
            logData = data;
            updateStats();
            renderTimeline();
        })
        .catch(err => {
            console.error("Error loading sample log:", err);
        });
}

function handleFileSelect(e) {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function(evt) {
        const text = evt.target.result;
        fetch('/api/parse', {
            method: 'POST',
            headers: { 'Content-Type': 'text/plain; charset=utf-8' },
            body: text
        })
        .then(res => res.json())
        .then(data => {
            logData = data;
            updateStats();
            renderTimeline();
        })
        .catch(err => console.error("Error parsing file:", err));
    };
    reader.readAsText(file);
}

function updateStats() {
    if (!logData) return;
    document.getElementById('stat-total').textContent = logData.total_count || 0;
    document.getElementById('stat-entities').textContent = Object.keys(logData.entity_index || {}).length;
    
    let anomalyCount = 0;
    (logData.all_entries || []).forEach(e => {
        anomalyCount += (e.anomalies || []).length;
    });
    document.getElementById('stat-anomalies').textContent = anomalyCount;
}

function renderTimeline() {
    const tbody = document.getElementById('timeline-tbody');
    tbody.innerHTML = '';

    if (!logData) {
        tbody.innerHTML = '<tr class="empty-row"><td colspan="7">Keine Daten geladen.</td></tr>';
        return;
    }

    const searchQuery = document.getElementById('search-input').value.trim().toLowerCase();
    const listToRender = collapseNoise ? logData.timeline : logData.all_entries;

    let filtered = listToRender.filter(entry => {
        // Quick filter chip
        if (activeFilter === 'insert' && entry.action !== 'insert') return false;
        if (activeFilter === 'update' && entry.action !== 'update') return false;
        if (activeFilter === 'delete' && !(entry.action === 'encdelete' || (entry.anomalies || []).some(a => a.type === 'deletion'))) return false;
        if (activeFilter === 'anomaly' && (!entry.anomalies || entry.anomalies.length === 0)) return false;

        // Entity filter
        if (activeEntityFilter) {
            const hasEntity = (entry.entities || []).includes(activeEntityFilter);
            if (!hasEntity) return false;
        }

        // Search text
        if (searchQuery) {
            const rawText = (entry.raw || '').toLowerCase();
            const descText = (entry.description || '').toLowerCase();
            const userText = (entry.user || '').toLowerCase();
            const tableText = (entry.table || '').toLowerCase();
            return rawText.includes(searchQuery) || descText.includes(searchQuery) || userText.includes(searchQuery) || tableText.includes(searchQuery);
        }

        return true;
    });

    if (filtered.length === 0) {
        tbody.innerHTML = '<tr class="empty-row"><td colspan="7">Keine Treffer für die aktuellen Filter.</td></tr>';
        return;
    }

    filtered.forEach(entry => {
        const tr = document.createElement('tr');
        if (activeEntry && activeEntry.line_number === entry.line_number) {
            tr.classList.add('active-row');
        }

        let badgeClass = 'badge-sql';
        if (entry.action === 'insert') badgeClass = 'badge-insert';
        if (entry.action === 'update') badgeClass = 'badge-update';
        if (entry.action === 'encdelete') badgeClass = 'badge-delete';

        let anomalyBadgeHtml = '';
        if (entry.anomalies && entry.anomalies.length > 0) {
            anomalyBadgeHtml = `<span class="badge-anomaly" title="${entry.anomalies[0].message}">⚠️ ${entry.anomalies[0].title}</span>`;
        }

        tr.innerHTML = `
            <td class="mono">${entry.line_number}</td>
            <td class="mono">${entry.timestamp || ''}</td>
            <td class="mono">${entry.user || ''}</td>
            <td><span class="badge ${badgeClass}">${entry.action}</span></td>
            <td><strong>${entry.table || ''}</strong></td>
            <td>${escapeHtml(entry.description || '')}</td>
            <td>${anomalyBadgeHtml}</td>
        `;

        tr.addEventListener('click', () => {
            document.querySelectorAll('#timeline-tbody tr').forEach(r => r.classList.remove('active-row'));
            tr.classList.add('active-row');
            selectEntry(entry);
        });

        tbody.appendChild(tr);
    });

    // Auto-select first row if none active
    if (!activeEntry && filtered.length > 0) {
        selectEntry(filtered[0]);
        const firstTr = tbody.querySelector('tr');
        if (firstTr) firstTr.classList.add('active-row');
    }
}

function selectEntry(entry) {
    activeEntry = entry;
    
    // Header info
    document.getElementById('inspector-line-num').textContent = `Zeile ${entry.line_number}`;
    document.getElementById('inspector-title').textContent = entry.description || entry.raw;
    
    const badgesContainer = document.getElementById('inspector-badges');
    badgesContainer.innerHTML = `
        <span class="badge badge-${entry.action === 'insert' ? 'insert' : entry.action === 'update' ? 'update' : 'sql'}">${entry.action}</span>
        <span class="badge badge-sql">${entry.table || 'N/A'}</span>
    `;

    // Render Tab 1: JSON Tree
    renderJsonTree(entry);

    // Render Tab 2: Diff
    renderDiff(entry);

    // Render Tab 3: Entity Tracer
    renderTracer(entry);

    // Render Tab 4: Raw
    document.getElementById('raw-container').textContent = entry.raw || '';
}

function renderJsonTree(entry) {
    const container = document.getElementById('tree-container');
    container.innerHTML = '';

    const payload = entry.payload;
    if (!payload) {
        container.innerHTML = '<div class="empty-state">Keine JSON-Payload enthalten.</div>';
        return;
    }

    const treeEl = createTreeNode("payload", payload, true);
    container.appendChild(treeEl);
}

function createTreeNode(key, val, isExpanded = true) {
    const node = document.createElement('div');
    node.className = 'tree-node';

    if (val === null) {
        node.innerHTML = `<span class="tree-key">${key}:</span> <span class="tree-null">null</span>`;
    } else if (typeof val === 'boolean') {
        node.innerHTML = `<span class="tree-key">${key}:</span> <span class="tree-boolean">${val}</span>`;
    } else if (typeof val === 'number') {
        node.innerHTML = `<span class="tree-key">${key}:</span> <span class="tree-number">${val}</span>`;
    } else if (typeof val === 'string') {
        node.innerHTML = `<span class="tree-key">${key}:</span> <span class="tree-string">"${escapeHtml(val)}"</span>`;
    } else if (typeof val === 'object') {
        const isArray = Array.isArray(val);
        const keys = Object.keys(val);
        const toggle = document.createElement('span');
        toggle.className = 'tree-toggle';
        toggle.textContent = isExpanded ? '▼ ' : '▶ ';

        const header = document.createElement('span');
        header.innerHTML = `<span class="tree-key">${key}:</span> ${isArray ? `Array(${keys.length}) [` : `Object {`}`;

        const childrenContainer = document.createElement('div');
        childrenContainer.style.display = isExpanded ? 'block' : 'none';
        childrenContainer.style.marginLeft = '16px';

        keys.forEach(k => {
            const childNode = createTreeNode(k, val[k], false);
            childrenContainer.appendChild(childNode);
        });

        const footer = document.createElement('div');
        footer.textContent = isArray ? ']' : '}';

        toggle.addEventListener('click', (e) => {
            e.stopPropagation();
            const isOpen = childrenContainer.style.display !== 'none';
            childrenContainer.style.display = isOpen ? 'none' : 'block';
            toggle.textContent = isOpen ? '▶ ' : '▼ ';
        });

        node.appendChild(toggle);
        node.appendChild(header);
        node.appendChild(childrenContainer);
        node.appendChild(footer);
    }

    return node;
}

function renderDiff(entry) {
    const container = document.getElementById('diff-container');
    container.innerHTML = '';

    const diff = entry.diff;
    if (!diff || Object.keys(diff).length === 0) {
        container.innerHTML = '<div class="empty-state">Keine Änderungen im Vergleich zur vorherigen Zeile festgestellt.</div>';
        return;
    }

    const table = document.createElement('table');
    table.className = 'diff-table';
    table.innerHTML = `
        <thead>
            <tr>
                <th>Feldname</th>
                <th>Vorheriger Wert</th>
                <th>Neuer Wert</th>
            </tr>
        </thead>
        <tbody></tbody>
    `;

    const tbody = table.querySelector('tbody');
    Object.keys(diff).forEach(key => {
        const item = diff[key];
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong style="color: #38bdf8;">${escapeHtml(key)}</strong></td>
            <td class="diff-old">${formatDiffValue(item.old)}</td>
            <td class="diff-new">${formatDiffValue(item.new)}</td>
        `;
        tbody.appendChild(tr);
    });

    container.appendChild(table);
}

function formatDiffValue(val) {
    if (val === null || val === undefined) {
        return '<span class="tree-null">null</span>';
    }
    if (typeof val === 'boolean') {
        return `<span class="tree-boolean">${val}</span>`;
    }
    if (typeof val === 'number') {
        return `<span class="tree-number">${val}</span>`;
    }
    if (typeof val === 'object') {
        return escapeHtml(JSON.stringify(val, null, 2));
    }
    return `"${escapeHtml(String(val))}"`;
}

function renderTracer(entry) {
    const container = document.getElementById('tracer-container');
    container.innerHTML = '';

    const entities = entry.entities || [];
    if (entities.length === 0) {
        container.innerHTML = '<div class="empty-state">Keine bekannten Entitäts-IDs in dieser Zeile.</div>';
        return;
    }

    const wrapper = document.createElement('div');
    wrapper.className = 'tracer-list';

    entities.forEach(eid => {
        const occurrences = (logData.entity_index[eid] || []).length;
        const item = document.createElement('div');
        item.className = 'tracer-item';
        item.innerHTML = `
            <div class="tracer-item-header">
                <strong>ID: ${eid}</strong>
                <span class="badge badge-sql">${occurrences} Log-Einträge</span>
            </div>
            <p style="font-size:11px; color:#9ca3af;">Klicken, um die gesamte Master-Timeline auf diese ID zu filtern.</p>
        `;

        item.addEventListener('click', () => {
            activeEntityFilter = eid;
            document.getElementById('entity-active-id').textContent = eid;
            document.getElementById('entity-active-badge').style.display = 'flex';
            renderTimeline();
        });

        wrapper.appendChild(item);
    });

    container.appendChild(wrapper);
}

function escapeHtml(str) {
    if (typeof str !== 'string') return str;
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
