let logData = null;
let activeEntry = null;
let activeFilter = 'all';
let activeEntityFilter = null;
let activeFileFilter = '';
let collapseNoise = true;
let prettyPrintRaw = localStorage.getItem('pretty_print_raw') !== 'false';
let rawIndentSize = localStorage.getItem('raw_indent_size') || '2';

document.addEventListener('DOMContentLoaded', () => {
    initEvents();
    initThemeToggle();
    initSQLConsole();
    loadSampleLog();
});

function initEvents() {
    // Buttons
    document.getElementById('btn-load-sample').addEventListener('click', loadSampleLog);
    document.getElementById('file-input').addEventListener('change', handleFileSelect);
    const entitiesInput = document.getElementById('entities-input');
    if (entitiesInput) {
        entitiesInput.addEventListener('change', handleEntitiesImport);
    }
    
    // File Filter Dropdown
    const fileFilterSelect = document.getElementById('file-filter-select');
    if (fileFilterSelect) {
        fileFilterSelect.addEventListener('change', (e) => {
            activeFileFilter = e.target.value;
            renderTimeline();
        });
    }

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

    // Raw View Pretty Print & Indent Toggle
    const togglePrettyRaw = document.getElementById('toggle-pretty-raw');
    const selectIndentSize = document.getElementById('select-indent-size');
    const btnCopyRaw = document.getElementById('btn-copy-raw');

    if (togglePrettyRaw) {
        togglePrettyRaw.checked = prettyPrintRaw;
        togglePrettyRaw.addEventListener('change', (e) => {
            prettyPrintRaw = e.target.checked;
            localStorage.setItem('pretty_print_raw', prettyPrintRaw);
            if (activeEntry) renderRawView(activeEntry);
        });
    }

    if (selectIndentSize) {
        selectIndentSize.value = rawIndentSize;
        selectIndentSize.addEventListener('change', (e) => {
            rawIndentSize = e.target.value;
            localStorage.setItem('raw_indent_size', rawIndentSize);
            if (activeEntry) renderRawView(activeEntry);
        });
    }

    if (btnCopyRaw) {
        btnCopyRaw.addEventListener('click', () => {
            const rawContainer = document.getElementById('raw-container');
            if (!rawContainer || !rawContainer.textContent) return;
            navigator.clipboard.writeText(rawContainer.textContent).then(() => {
                const originalHtml = btnCopyRaw.innerHTML;
                btnCopyRaw.textContent = 'Kopiert!';
                btnCopyRaw.classList.add('btn-success');
                setTimeout(() => {
                    btnCopyRaw.innerHTML = originalHtml;
                    btnCopyRaw.classList.remove('btn-success');
                }, 1500);
            }).catch(err => {
                console.error('Kopieren fehlgeschlagen:', err);
            });
        });
    }

    // Modal Close handlers
    const btnCloseModal = document.getElementById('btn-close-modal');
    const btnCloseModalFooter = document.getElementById('btn-close-modal-footer');
    const btnOpenSqlTab = document.getElementById('btn-open-sql-tab');
    const modal = document.getElementById('import-results-modal');

    if (btnCloseModal) btnCloseModal.addEventListener('click', () => modal.style.display = 'none');
    if (btnCloseModalFooter) btnCloseModalFooter.addEventListener('click', () => modal.style.display = 'none');
    if (btnOpenSqlTab) {
        btnOpenSqlTab.addEventListener('click', () => {
            modal.style.display = 'none';
            const sqlTabBtn = document.querySelector('.tab-btn[data-tab="sql"]');
            if (sqlTabBtn) sqlTabBtn.click();
        });
    }

    // Inspector Tabs
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            btn.classList.add('active');
            const targetId = `tab-${btn.dataset.tab}`;
            const targetEl = document.getElementById(targetId);
            if (targetEl) targetEl.classList.add('active');

            if (btn.dataset.tab === 'sql') {
                const queryInput = document.getElementById('sql-query-input');
                if (queryInput && !queryInput.value.trim()) {
                    queryInput.value = 'SELECT * FROM logs LIMIT 50;';
                    runSQLQuery();
                }
            }
        });
    });

    // Resizer Dragging
    initTableColumnResizer();

    const resizer = document.getElementById('resizer');
    const masterPanel = document.querySelector('.master-panel');
    const detailPanel = document.querySelector('.detail-panel');
    let isDragging = false;

    if (!resizer || !masterPanel || !detailPanel) return;

    resizer.addEventListener('mousedown', (e) => {
        isDragging = true;
        resizer.classList.add('dragging');
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
    });

    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        const container = document.querySelector('.main-split-container');
        if (!container) return;
        const containerWidth = container.clientWidth;
        const pointerX = e.clientX;
        const minWidth = 350;
        
        let newMasterWidth = pointerX - 16;
        let newDetailWidth = containerWidth - newMasterWidth - 8;

        if (newMasterWidth >= minWidth && newDetailWidth >= minWidth) {
            const masterPercent = (newMasterWidth / containerWidth) * 100;
            const detailPercent = (newDetailWidth / containerWidth) * 100;
            masterPanel.style.flex = `0 0 ${masterPercent}%`;
            detailPanel.style.flex = `0 0 ${detailPercent}%`;
        }
    });

    document.addEventListener('mouseup', () => {
        if (isDragging) {
            isDragging = false;
            resizer.classList.remove('dragging');
            document.body.style.cursor = 'default';
            document.body.style.userSelect = 'auto';
        }
    });
}

function initTableColumnResizer() {
    const table = document.querySelector('.master-table');
    if (!table) return;

    const resizers = table.querySelectorAll('.col-resizer');
    resizers.forEach(resizer => {
        const th = resizer.parentElement;
        let startX = 0;
        let startWidth = 0;

        resizer.addEventListener('mousedown', (e) => {
            e.stopPropagation();
            startX = e.pageX;
            startWidth = th.offsetWidth;
            resizer.classList.add('resizing');
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';

            const onMouseMove = (ev) => {
                const diff = ev.pageX - startX;
                const newWidth = Math.max(35, startWidth + diff);
                th.style.width = `${newWidth}px`;
            };

            const onMouseUp = () => {
                resizer.classList.remove('resizing');
                document.body.style.cursor = 'default';
                document.body.style.userSelect = 'auto';
                document.removeEventListener('mousemove', onMouseMove);
                document.removeEventListener('mouseup', onMouseUp);
            };

            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
        });
    });
}

function initThemeToggle() {
    const themeBtn = document.getElementById('btn-theme-toggle');
    const sunIcon = document.getElementById('theme-icon-sun');
    const moonIcon = document.getElementById('theme-icon-moon');
    const themeLabel = document.getElementById('theme-label');

    if (!themeBtn) return;

    const savedTheme = localStorage.getItem('pylog_theme') || 'dark';
    setTheme(savedTheme);

    themeBtn.addEventListener('click', () => {
        const currentTheme = document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
        const newTheme = currentTheme === 'light' ? 'dark' : 'light';
        setTheme(newTheme);
    });

    function setTheme(theme) {
        if (theme === 'light') {
            document.documentElement.setAttribute('data-theme', 'light');
            if (sunIcon) sunIcon.style.display = 'none';
            if (moonIcon) moonIcon.style.display = 'inline';
            if (themeLabel) themeLabel.textContent = 'Darkmode';
            localStorage.setItem('pylog_theme', 'light');
        } else {
            document.documentElement.removeAttribute('data-theme');
            if (sunIcon) sunIcon.style.display = 'inline';
            if (moonIcon) moonIcon.style.display = 'none';
            if (themeLabel) themeLabel.textContent = 'Lightmode';
            localStorage.setItem('pylog_theme', 'dark');
        }
    }
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
            activeEntry = null;
            activeEntityFilter = null;
            activeFileFilter = '';
            document.getElementById('entity-active-badge').style.display = 'none';
            updateFileFilterDropdown();
            updateStats();
            renderTimeline();
        })
        .catch(err => {
            console.error("Error loading sample log:", err);
        });
}

function handleFileSelect(e) {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;

    let allParsedEntries = [];
    let promises = files.map(file => {
        return new Promise((resolve) => {
            const reader = new FileReader();
            reader.onload = function(evt) {
                const body = evt.target.result;
                fetch('/api/parse', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/octet-stream',
                        'X-File-Name': file.name
                    },
                    body: body
                })
                .then(res => res.json())
                .then(data => {
                    if (data.all_entries) {
                        allParsedEntries = allParsedEntries.concat(data.all_entries);
                    }
                    resolve();
                })
                .catch(err => {
                    console.error(`Error parsing file ${file.name}:`, err);
                    resolve();
                });
            };
            if (file.name.endsWith('.zip')) {
                reader.readAsArrayBuffer(file);
            } else {
                reader.readAsText(file);
            }
        });
    });

    Promise.all(promises).then(() => {
        fetch('/api/parse', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-File-Name': files.length === 1 ? files[0].name : 'multi_logs.log'
            },
            body: JSON.stringify({ entries: allParsedEntries })
        })
        .then(res => res.json())
        .then(data => {
            logData = data;
            activeEntry = null;
            activeEntityFilter = null;
            activeFileFilter = '';
            document.getElementById('entity-active-badge').style.display = 'none';
            updateFileFilterDropdown();
            updateStats();
            renderTimeline();
        })
        .catch(err => console.error("Error parsing combined files:", err));
    });
}

function updateFileFilterDropdown() {
    const select = document.getElementById('file-filter-select');
    if (!select) return;

    select.innerHTML = '<option value="">Alle Logdateien</option>';
    const files = (logData && logData.loaded_files) ? logData.loaded_files : [];
    if (files.length > 1) {
        files.forEach(f => {
            const opt = document.createElement('option');
            opt.value = f;
            opt.textContent = f;
            if (f === activeFileFilter) opt.selected = true;
            select.appendChild(opt);
        });
        select.style.display = 'inline-block';
    } else {
        select.style.display = 'none';
    }
}

function handleEntitiesImport(e) {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;

    let processedCount = 0;

    const promises = files.map(file => {
        return new Promise((resolve) => {
            const reader = new FileReader();
            reader.onload = function(evt) {
                const body = evt.target.result;
                fetch('/api/import_entities', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/octet-stream',
                        'X-File-Name': file.name
                    },
                    body: body
                })
                .then(res => res.json())
                .then(data => {
                    if (data.entity_names) {
                        if (!logData) logData = {};
                        if (!logData.entity_names) logData.entity_names = {};
                        Object.assign(logData.entity_names, data.entity_names);
                        processedCount++;
                    }
                    resolve();
                })
                .catch(err => {
                    console.error(`Error importing ${file.name}:`, err);
                    resolve();
                });
            };

            if (file.name.endsWith('.db') || file.name.endsWith('.sqlite') || file.name.endsWith('.sqlite3') || file.name.endsWith('.zip')) {
                reader.readAsArrayBuffer(file);
            } else {
                reader.readAsText(file);
            }
        });
    });

    Promise.all(promises).then(() => {
        const totalMapped = Object.keys(logData.entity_names || {}).length;
        renderTimeline();
        if (activeEntry) selectEntry(activeEntry);

        fetch('/api/schema')
            .then(res => res.json())
            .then(schemaData => {
                showImportResultsModal(processedCount, totalMapped, schemaData);
            })
            .catch(() => {
                showImportResultsModal(processedCount, totalMapped, null);
            });
    });
}

function updateStats() {
    if (!logData) return;
    document.getElementById('stat-total').textContent = logData.total_count || 0;
    document.getElementById('stat-entities').textContent = Object.keys(logData.entity_index || {}).length;
    
    const fileCount = (logData.loaded_files || []).length || (logData.all_entries ? 1 : 0);
    const statFiles = document.getElementById('stat-files');
    if (statFiles) statFiles.textContent = fileCount;

    let anomalyCount = 0;
    (logData.all_entries || []).forEach(e => {
        anomalyCount += (e.anomalies || []).length;
    });
    document.getElementById('stat-anomalies').textContent = anomalyCount;
}

function formatDateString(val) {
    if (typeof val !== 'string' || !val) return val;

    const dtMatch = val.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}:\d{2}:\d{2})(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?$/);
    if (dtMatch) {
        return `${dtMatch[3]}.${dtMatch[2]}.${dtMatch[1]} ${dtMatch[4]}`;
    }

    const dtMinMatch = val.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}:\d{2})(?:Z|[+-]\d{2}:\d{2})?$/);
    if (dtMinMatch) {
        return `${dtMinMatch[3]}.${dtMinMatch[2]}.${dtMinMatch[1]} ${dtMinMatch[4]}`;
    }

    const dateMatch = val.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (dateMatch) {
        return `${dateMatch[3]}.${dateMatch[2]}.${dateMatch[1]}`;
    }

    return val.replace(/\b(\d{4})-(\d{2})-(\d{2})\b/g, (m, y, mo, d) => `${d}.${mo}.${y}`);
}

function resetInspector() {
    activeEntry = null;
    document.getElementById('inspector-line-num').textContent = 'Zeile ---';
    document.getElementById('inspector-title').textContent = 'Keine Zeile ausgewählt';
    document.getElementById('inspector-badges').innerHTML = '';
    document.getElementById('tree-container').innerHTML = '<div class="empty-state">Wählen Sie einen Log-Eintrag aus der linken Liste.</div>';
    document.getElementById('diff-container').innerHTML = '<div class="empty-state">Wählen Sie einen Update-Eintrag mit vorherigen Änderungen.</div>';
    document.getElementById('tracer-container').innerHTML = '<div class="empty-state">Keine verknüpften Entitäten in diesem Eintrag.</div>';
    document.getElementById('raw-container').textContent = '';
}

function renderTimeline() {
    const tbody = document.getElementById('timeline-tbody');
    tbody.innerHTML = '';

    if (!logData) {
        tbody.innerHTML = '<tr class="empty-row"><td colspan="8">Keine Daten geladen.</td></tr>';
        resetInspector();
        return;
    }

    const searchQuery = document.getElementById('search-input').value.trim().toLowerCase();
    const listToRender = collapseNoise ? logData.timeline : logData.all_entries;

    let filtered = listToRender.filter(entry => {
        if (activeFilter === 'insert' && entry.action !== 'insert') return false;
        if (activeFilter === 'update' && entry.action !== 'update') return false;
        if (activeFilter === 'delete' && !(entry.action === 'encdelete' || (entry.anomalies || []).some(a => a.type === 'deletion'))) return false;
        if (activeFilter === 'anomaly' && (!entry.anomalies || entry.anomalies.length === 0)) return false;

        if (activeFileFilter && entry.file_name && entry.file_name !== activeFileFilter) {
            return false;
        }

        if (activeEntityFilter) {
            const hasEntity = (entry.entities || []).includes(activeEntityFilter);
            if (!hasEntity) return false;
        }

        if (searchQuery) {
            const rawText = (entry.raw || '').toLowerCase();
            const descText = (entry.description || '').toLowerCase();
            const userText = (entry.user || '').toLowerCase();
            const userNameText = (entry.user_name || '').toLowerCase();
            const tableText = (entry.table || '').toLowerCase();
            const fileText = (entry.file_name || '').toLowerCase();
            return rawText.includes(searchQuery) || descText.includes(searchQuery) || userText.includes(searchQuery) || userNameText.includes(searchQuery) || tableText.includes(searchQuery) || fileText.includes(searchQuery);
        }

        return true;
    });

    if (filtered.length === 0) {
        tbody.innerHTML = '<tr class="empty-row"><td colspan="8">Keine Treffer für die aktuellen Filter.</td></tr>';
        resetInspector();
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

        const fileNameDisplay = entry.file_name || 'sample.log';
        const userName = entry.user_name || ((logData && logData.entity_names) ? logData.entity_names[entry.user] : null);
        const userDisplay = userName ? `<span class="user-name-tag" title="User ID: ${escapeHtml(entry.user || '')}">👤 ${escapeHtml(userName)}</span>` : escapeHtml(entry.user || '');

        tr.innerHTML = `
            <td class="mono">${entry.line_number}</td>
            <td class="mono"><span class="badge-file" title="${escapeHtml(fileNameDisplay)}">📁 ${escapeHtml(fileNameDisplay)}</span></td>
            <td class="mono">${formatDateString(entry.timestamp) || ''}</td>
            <td class="mono">${userDisplay}</td>
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

    // Auto-select active row or first visible row in filtered list
    const isCurrentActiveVisible = filtered.some(e => e.line_number === activeEntry?.line_number);
    if (!isCurrentActiveVisible && filtered.length > 0) {
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
    
    const userName = entry.user_name || ((logData && logData.entity_names) ? logData.entity_names[entry.user] : null);
    const userBadgeText = userName ? `Nutzer: ${userName} (${entry.user || ''})` : `Nutzer: ${entry.user || 'N/A'}`;

    const badgesContainer = document.getElementById('inspector-badges');
    badgesContainer.innerHTML = `
        <span class="badge badge-${entry.action === 'insert' ? 'insert' : entry.action === 'update' ? 'update' : 'sql'}">${entry.action}</span>
        <span class="badge badge-sql">${entry.table || 'N/A'}</span>
        <span class="badge badge-sql" title="Nutzer">${escapeHtml(userBadgeText)}</span>
    `;

    // Render Tab 1: JSON Tree
    renderJsonTree(entry);

    // Render Tab 2: Diff
    renderDiff(entry);

    // Render Tab 3: Entity Tracer
    renderTracer(entry);

    // Render Tab 4: Raw
    renderRawView(entry);
}

function renderRawView(entry) {
    const rawContainer = document.getElementById('raw-container');
    if (!rawContainer) return;
    if (!entry || !entry.raw) {
        rawContainer.textContent = '';
        return;
    }
    rawContainer.textContent = formatRawLog(entry, prettyPrintRaw, rawIndentSize);
}

function formatRawLog(entry, pretty = true, indentSize = '2') {
    if (!entry || !entry.raw) return '';
    if (!pretty) return entry.raw;

    const indent = indentSize === 'tab' ? '\t' : (parseInt(indentSize, 10) || 2);

    // 1. Check if entry has parsed payload object
    if (entry.payload && typeof entry.payload === 'object') {
        const rawStr = entry.raw;
        const firstBrace = rawStr.search(/[\{\[]/);
        if (firstBrace !== -1) {
            const prefix = rawStr.substring(0, firstBrace).trimEnd();
            const prettyJson = JSON.stringify(entry.payload, null, indent);
            return prefix ? `${prefix}\n${prettyJson}` : prettyJson;
        }
        return JSON.stringify(entry.payload, null, indent);
    }

    // 2. Fallback: try parsing JSON substring inside raw line
    const firstBrace = entry.raw.search(/[\{\[]/);
    if (firstBrace !== -1) {
        const prefix = entry.raw.substring(0, firstBrace).trimEnd();
        const jsonCandidate = entry.raw.substring(firstBrace);
        try {
            const parsed = JSON.parse(jsonCandidate);
            const prettyJson = JSON.stringify(parsed, null, indent);
            return prefix ? `${prefix}\n${prettyJson}` : prettyJson;
        } catch (e) {
            // Ignore parse error
        }
    }

    // 3. Fallback: try parsing full raw line as JSON
    try {
        const parsed = JSON.parse(entry.raw);
        return JSON.stringify(parsed, null, indent);
    } catch (e) {
        return entry.raw;
    }
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
        const resolvedName = (logData && logData.entity_names) ? logData.entity_names[val] : null;
        const nameTag = resolvedName ? ` <span class="tree-entity-name">👤 (${escapeHtml(resolvedName)})</span>` : '';
        node.innerHTML = `<span class="tree-key">${key}:</span> <span class="tree-string">"${escapeHtml(formatDateString(val))}"</span>${nameTag}`;
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
        return escapeHtml(formatDateString(JSON.stringify(val, null, 2)));
    }
    return `"${escapeHtml(formatDateString(String(val)))}"`;
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
        const name = (logData && logData.entity_names) ? logData.entity_names[eid] : null;
        const elabel = (logData && logData.entity_labels) ? logData.entity_labels[eid] : 'ID';
        const nameTag = name ? `<span class="tracer-entity-name">👤 ${escapeHtml(name)}</span>` : '';
        const typeTag = `<span class="badge badge-entity-type">${escapeHtml(elabel)}</span>`;

        const item = document.createElement('div');
        item.className = 'tracer-item';
        item.innerHTML = `
            <div class="tracer-item-header">
                <div>${typeTag}<strong>${eid}</strong> ${nameTag}</div>
                <span class="badge badge-sql">${occurrences} Log-Einträge</span>
            </div>
            <p style="font-size:11px; color:var(--text-secondary);">Klicken, um die gesamte Master-Timeline auf diese ${escapeHtml(elabel)} zu filtern.</p>
        `;

        item.addEventListener('click', () => {
            activeEntityFilter = eid;
            const filterLabel = `${elabel}: ${name ? `${name} (${eid})` : eid}`;
            document.getElementById('entity-active-id').textContent = filterLabel;
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

let lastSQLResult = null;

function initSQLConsole() {
    const btnRun = document.getElementById('btn-run-sql');
    const btnClear = document.getElementById('btn-clear-sql');
    const btnExport = document.getElementById('btn-export-sql-csv');
    const btnSchema = document.getElementById('btn-show-schema');
    const inputQuery = document.getElementById('sql-query-input');
    const selectTemplates = document.getElementById('sql-templates-select');

    if (!btnRun || !inputQuery) return;

    btnRun.addEventListener('click', runSQLQuery);
    btnClear.addEventListener('click', () => {
        inputQuery.value = '';
        document.getElementById('sql-status-bar').textContent = '';
        document.getElementById('sql-status-bar').className = 'sql-status';
        document.getElementById('sql-results-container').innerHTML = '<div class="empty-state">Geben Sie eine SQL-Abfrage ein und klicken Sie auf "Ausführen".</div>';
        btnExport.style.display = 'none';
    });

    inputQuery.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            e.preventDefault();
            runSQLQuery();
        }
    });

    if (selectTemplates) {
        selectTemplates.addEventListener('change', (e) => {
            if (e.target.value) {
                inputQuery.value = e.target.value;
                runSQLQuery();
            }
        });
    }

    if (btnSchema) btnSchema.addEventListener('click', toggleSchemaBrowser);
    if (btnExport) btnExport.addEventListener('click', exportSQLResultsCSV);
}

function toggleSchemaBrowser() {
    const box = document.getElementById('sql-schema-container');
    if (box.style.display !== 'none') {
        box.style.display = 'none';
        return;
    }

    fetch('/api/schema')
        .then(res => res.json())
        .then(data => {
            const tables = data.tables || {};
            box.innerHTML = '';
            const tableNames = Object.keys(tables);
            if (tableNames.length === 0) {
                box.innerHTML = '<em>Keine Tabellen geladen.</em>';
            } else {
                tableNames.forEach(t => {
                    const item = document.createElement('div');
                    item.className = 'sql-schema-table-item';
                    item.innerHTML = `<span class="sql-schema-table-name">${escapeHtml(t)}:</span> <span class="sql-schema-cols">${escapeHtml((tables[t] || []).join(', '))}</span>`;
                    box.appendChild(item);
                });
            }
            box.style.display = 'block';
        })
        .catch(err => console.error("Error fetching schema:", err));
}

function runSQLQuery() {
    const query = document.getElementById('sql-query-input').value.trim();
    const statusBar = document.getElementById('sql-status-bar');
    const container = document.getElementById('sql-results-container');
    const btnExport = document.getElementById('btn-export-sql-csv');

    if (!query) {
        statusBar.textContent = 'Bitte geben Sie eine SQL-Abfrage ein.';
        statusBar.className = 'sql-status error';
        return;
    }

    statusBar.textContent = 'Führe SQL-Abfrage aus...';
    statusBar.className = 'sql-status';

    fetch('/api/query_sql', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query })
    })
    .then(res => res.json())
    .then(data => {
        if (data.error) {
            statusBar.textContent = `Fehler: ${data.error}`;
            statusBar.className = 'sql-status error';
            container.innerHTML = `<div class="empty-state" style="color: #ef4444;">${escapeHtml(data.error)}</div>`;
            btnExport.style.display = 'none';
            lastSQLResult = null;
            return;
        }

        lastSQLResult = data;
        statusBar.textContent = `Erfolgreich (${data.row_count} Zeilen in ${data.execution_time_ms} ms)`;
        statusBar.className = 'sql-status success';
        btnExport.style.display = 'inline-flex';

        renderSQLResultsTable(data);
    })
    .catch(err => {
        statusBar.textContent = `Netzwerk-Fehler: ${err}`;
        statusBar.className = 'sql-status error';
    });
}

function renderSQLResultsTable(data) {
    const container = document.getElementById('sql-results-container');
    container.innerHTML = '';

    const cols = data.columns || [];
    const rows = data.rows || [];

    if (cols.length === 0 || rows.length === 0) {
        container.innerHTML = '<div class="empty-state">Die Abfrage lieferte 0 Zeilen zurück.</div>';
        return;
    }

    const table = document.createElement('table');
    table.className = 'sql-results-table';

    let theadHtml = '<thead><tr>';
    cols.forEach(c => {
        theadHtml += `<th>${escapeHtml(c)}</th>`;
    });
    theadHtml += '</tr></thead>';

    let tbodyHtml = '<tbody>';
    rows.forEach(r => {
        tbodyHtml += '<tr>';
        r.forEach(val => {
            const formatted = val === null ? 'null' : (typeof val === 'object' ? JSON.stringify(val) : String(val));
            tbodyHtml += `<td title="${escapeHtml(formatted)}">${escapeHtml(formatDateString(formatted))}</td>`;
        });
        tbodyHtml += '</tr>';
    });
    tbodyHtml += '</tbody>';

    table.innerHTML = theadHtml + tbodyHtml;
    container.appendChild(table);
}

function exportSQLResultsCSV() {
    if (!lastSQLResult || !lastSQLResult.columns || !lastSQLResult.rows) return;

    const cols = lastSQLResult.columns;
    const rows = lastSQLResult.rows;

    let csvContent = cols.map(c => `"${c.replace(/"/g, '""')}"`).join(';') + '\n';
    rows.forEach(r => {
        const rowStr = r.map(val => {
            const str = val === null ? '' : String(val);
            return `"${str.replace(/"/g, '""')}"`;
        }).join(';');
        csvContent += rowStr + '\n';
    });

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'sql_export.csv';
    a.click();
    URL.revokeObjectURL(url);
}

function showImportResultsModal(fileCount, totalNames, schemaData) {
    const modal = document.getElementById('import-results-modal');
    const summaryText = document.getElementById('import-summary-text');
    const tablesList = document.getElementById('import-tables-list');

    if (!modal) return;

    summaryText.innerHTML = `<strong>${fileCount} Datei(en)</strong> erfolgreich verarbeitet. Insgesamt stehen nun <strong>${totalNames} Entitäts-Namen</strong> im Speicher zur Verfügung.`;

    tablesList.innerHTML = '';
    const tables = (schemaData && schemaData.tables) || {};
    const counts = (schemaData && schemaData.row_counts) || {};

    const tableNames = Object.keys(tables);
    if (tableNames.length === 0) {
        tablesList.innerHTML = '<em>Keine Tabellen gefunden.</em>';
    } else {
        tableNames.forEach(t => {
            const card = document.createElement('div');
            card.className = 'table-badge-card';
            const cnt = counts[t] !== undefined ? `${counts[t]} Zeilen` : 'Tabelle';
            card.innerHTML = `
                <span class="table-badge-name">📁 ${escapeHtml(t)}</span>
                <span class="table-badge-count">${cnt}</span>
            `;
            card.addEventListener('click', () => {
                modal.style.display = 'none';
                openSQLTabWithTable(t);
            });
            tablesList.appendChild(card);
        });
    }

    modal.style.display = 'flex';
}

function openSQLTabWithTable(tableName) {
    const sqlTabBtn = document.querySelector('.tab-btn[data-tab="sql"]');
    if (sqlTabBtn) sqlTabBtn.click();

    const input = document.getElementById('sql-query-input');
    if (input) {
        input.value = `SELECT * FROM "${tableName}" LIMIT 50;`;
        runSQLQuery();
    }
}
