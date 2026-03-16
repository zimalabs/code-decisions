---
name: engram:visualize
description: "Generate an interactive HTML dashboard visualizing all engram signals — timeline, type distribution, tag frequency, link graph, and searchable table. Opens in browser."
---

# @engram:visualize

Generate a self-contained HTML dashboard from the engram index and open it in the browser.

## Execution Steps

### 1. Ensure index exists

Check if `.engram/index.db` exists. If not, rebuild:

```bash
source ${CLAUDE_PLUGIN_ROOT}/lib.sh && engram_reindex .engram
```

### 2. Run 4 queries

Run each query via Bash and capture the JSON output into shell variables:

**All signals:**
```bash
sqlite3 -json .engram/index.db "SELECT id, type, title, date, tags, excerpt, status, file_stem, private FROM signals ORDER BY date ASC"
```

**Tag frequency:**
```bash
sqlite3 -json .engram/index.db "SELECT value as tag, COUNT(*) as count FROM signals, json_each(signals.tags) GROUP BY value ORDER BY count DESC"
```

**Links:**
```bash
sqlite3 -json .engram/index.db "SELECT source_file, target_file, rel_type FROM links"
```

**Signal metadata (for graph labels):**
```bash
sqlite3 -json .engram/index.db "SELECT file_stem, title, type FROM signals"
```

If any query returns empty, use `[]` as the default value.

### 3. Build the HTML file

Write a single self-contained HTML file to `.engram/visualize.html` using the Write tool. Embed the query results as JavaScript constants.

The HTML file MUST follow this exact structure:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Engram Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
  <style>
    /* CSS custom properties for dark theme */
    :root {
      --bg: #0d1117;
      --surface: #161b22;
      --border: #30363d;
      --text: #e6edf3;
      --text-muted: #8b949e;
      --decision: #4cc9f0;
      --finding: #06d6a0;
      --issue: #ef476f;
      --link-supersedes: #ffd166;
      --link-related: #8b949e;
      --link-blocks: #ef476f;
      --link-blocked-by: #f77f00;
    }

    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; padding: 24px; }

    h1 { text-align: center; font-size: 1.5rem; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 24px; color: var(--text-muted); }

    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
    .card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
    .card h2 { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-muted); margin-bottom: 12px; }
    .full-width { grid-column: 1 / -1; }

    /* Timeline */
    .timeline { position: relative; height: 120px; overflow-x: auto; }
    .timeline-track { position: absolute; top: 50%; left: 0; right: 0; height: 2px; background: var(--border); }
    .timeline-dot { position: absolute; top: 50%; width: 12px; height: 12px; border-radius: 50%; transform: translate(-50%, -50%); cursor: pointer; transition: transform 0.15s; }
    .timeline-dot:hover { transform: translate(-50%, -50%) scale(1.6); z-index: 10; }
    .timeline-tooltip { display: none; position: absolute; bottom: calc(50% + 16px); left: 50%; transform: translateX(-50%); background: var(--bg); border: 1px solid var(--border); border-radius: 4px; padding: 6px 10px; font-size: 0.75rem; white-space: nowrap; z-index: 20; pointer-events: none; }
    .timeline-dot:hover .timeline-tooltip { display: block; }
    .timeline-label { position: absolute; top: calc(50% + 16px); font-size: 0.65rem; color: var(--text-muted); transform: translateX(-50%); }
    .empty-state { color: var(--text-muted); font-style: italic; text-align: center; padding: 32px 0; }

    /* Chart containers */
    .chart-container { position: relative; height: 200px; }

    /* Link graph */
    .graph-container { position: relative; height: 260px; }
    .graph-container svg { width: 100%; height: 100%; }

    /* Signal table */
    .controls { display: flex; gap: 8px; margin-bottom: 12px; }
    .controls input, .controls select { background: var(--bg); color: var(--text); border: 1px solid var(--border); border-radius: 4px; padding: 6px 10px; font-size: 0.85rem; }
    .controls input { flex: 1; }

    table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
    th { text-align: left; color: var(--text-muted); font-weight: 600; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; padding: 8px; border-bottom: 1px solid var(--border); }
    td { padding: 8px; border-bottom: 1px solid var(--border); vertical-align: top; }
    tr:hover td { background: rgba(255,255,255,0.02); }
    .type-badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 0.7rem; font-weight: 600; text-transform: uppercase; }
    .type-badge.decision { background: rgba(76,201,240,0.15); color: var(--decision); }
    .type-badge.finding { background: rgba(6,214,160,0.15); color: var(--finding); }
    .type-badge.issue { background: rgba(239,71,111,0.15); color: var(--issue); }
    .tag { display: inline-block; background: rgba(255,255,255,0.06); padding: 1px 6px; border-radius: 3px; font-size: 0.7rem; margin: 1px; color: var(--text-muted); }
  </style>
</head>
<body>
  <h1>Engram Dashboard</h1>
  <div class="grid">
    <div class="card full-width">
      <h2>Timeline</h2>
      <div class="timeline" id="timeline"></div>
    </div>
    <div class="card">
      <h2>Type Distribution</h2>
      <div class="chart-container"><canvas id="typeChart"></canvas></div>
    </div>
    <div class="card">
      <h2>Tag Frequency</h2>
      <div class="chart-container"><canvas id="tagChart"></canvas></div>
    </div>
    <div class="card full-width" id="graphCard">
      <h2>Signal Links</h2>
      <div class="graph-container" id="graphContainer"></div>
    </div>
    <div class="card full-width">
      <h2>All Signals</h2>
      <div class="controls">
        <input type="text" id="search" placeholder="Search signals...">
        <select id="typeFilter">
          <option value="">All types</option>
          <option value="decision">Decisions</option>
          <option value="finding">Findings</option>
          <option value="issue">Issues</option>
        </select>
      </div>
      <table>
        <thead><tr><th>Date</th><th>Type</th><th>Title</th><th>Tags</th><th>Status</th></tr></thead>
        <tbody id="signalTable"></tbody>
      </table>
    </div>
  </div>

  <script>
    // --- Embedded data (replaced by skill) ---
    const SIGNALS = __SIGNALS_JSON__;
    const TAG_COUNTS = __TAG_COUNTS_JSON__;
    const LINKS = __LINKS_JSON__;
    const SIGNAL_META = __SIGNAL_META_JSON__;

    const TYPE_COLORS = { decision: '#4cc9f0', finding: '#06d6a0', issue: '#ef476f' };
    const LINK_COLORS = { supersedes: '#ffd166', related: '#8b949e', blocks: '#ef476f', 'blocked-by': '#f77f00' };

    // --- Timeline ---
    (function renderTimeline() {
      const el = document.getElementById('timeline');
      if (!SIGNALS.length) { el.innerHTML = '<div class="empty-state">No signals yet</div>'; return; }

      const dates = SIGNALS.map(s => new Date(s.date).getTime());
      const min = Math.min(...dates), max = Math.max(...dates);
      const range = max - min || 1;

      let html = '<div class="timeline-track"></div>';
      SIGNALS.forEach(s => {
        const pct = ((new Date(s.date).getTime() - min) / range) * 90 + 5;
        const color = TYPE_COLORS[s.type] || '#8b949e';
        html += `<div class="timeline-dot" style="left:${pct}%;background:${color}">` +
          `<div class="timeline-tooltip"><strong>${s.title}</strong><br>${s.date} &middot; ${s.type}</div></div>`;
      });

      // Date labels
      const uniqueDates = [...new Set(SIGNALS.map(s => s.date))];
      const labelDates = uniqueDates.length <= 6 ? uniqueDates : [uniqueDates[0], uniqueDates[Math.floor(uniqueDates.length/2)], uniqueDates[uniqueDates.length-1]];
      labelDates.forEach(d => {
        const pct = ((new Date(d).getTime() - min) / range) * 90 + 5;
        html += `<div class="timeline-label" style="left:${pct}%">${d}</div>`;
      });

      el.innerHTML = html;
    })();

    // --- Type Distribution (doughnut) ---
    (function renderTypeChart() {
      const counts = {};
      SIGNALS.forEach(s => { counts[s.type] = (counts[s.type] || 0) + 1; });
      const labels = Object.keys(counts);
      if (!labels.length) { document.getElementById('typeChart').parentElement.innerHTML = '<div class="empty-state">No signals yet</div>'; return; }

      new Chart(document.getElementById('typeChart'), {
        type: 'doughnut',
        data: {
          labels: labels.map(l => l.charAt(0).toUpperCase() + l.slice(1)),
          datasets: [{ data: labels.map(l => counts[l]), backgroundColor: labels.map(l => TYPE_COLORS[l] || '#8b949e'), borderWidth: 0 }]
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { color: '#e6edf3', padding: 12 } } } }
      });
    })();

    // --- Tag Frequency (horizontal bar) ---
    (function renderTagChart() {
      if (!TAG_COUNTS.length) { document.getElementById('tagChart').parentElement.innerHTML = '<div class="empty-state">No tags yet</div>'; return; }
      const top = TAG_COUNTS.slice(0, 12);

      new Chart(document.getElementById('tagChart'), {
        type: 'bar',
        data: {
          labels: top.map(t => t.tag),
          datasets: [{ data: top.map(t => t.count), backgroundColor: '#4cc9f0', borderRadius: 3 }]
        },
        options: {
          indexAxis: 'y', responsive: true, maintainAspectRatio: false,
          scales: { x: { ticks: { color: '#8b949e' }, grid: { color: '#30363d' } }, y: { ticks: { color: '#e6edf3' }, grid: { display: false } } },
          plugins: { legend: { display: false } }
        }
      });
    })();

    // --- Link Graph (SVG circular layout) ---
    (function renderGraph() {
      const container = document.getElementById('graphContainer');
      if (!LINKS.length) { container.innerHTML = '<div class="empty-state">No links yet</div>'; return; }

      // Collect unique nodes
      const nodeSet = new Set();
      LINKS.forEach(l => { nodeSet.add(l.source_file); nodeSet.add(l.target_file); });
      const nodes = [...nodeSet];
      const metaMap = {};
      SIGNAL_META.forEach(m => { metaMap[m.file_stem] = m; });

      const w = container.clientWidth || 400, h = 260;
      const cx = w / 2, cy = h / 2, r = Math.min(cx, cy) - 40;

      let svg = `<svg viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg">`;

      // Position nodes in circle
      const pos = {};
      nodes.forEach((n, i) => {
        const angle = (2 * Math.PI * i) / nodes.length - Math.PI / 2;
        pos[n] = { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) };
      });

      // Edges
      LINKS.forEach(l => {
        const from = pos[l.source_file], to = pos[l.target_file];
        if (!from || !to) return;
        const color = LINK_COLORS[l.rel_type] || '#8b949e';
        svg += `<line x1="${from.x}" y1="${from.y}" x2="${to.x}" y2="${to.y}" stroke="${color}" stroke-width="1.5" opacity="0.6"/>`;
      });

      // Nodes
      nodes.forEach(n => {
        const p = pos[n], meta = metaMap[n] || {};
        const color = TYPE_COLORS[meta.type] || '#8b949e';
        const label = (meta.title || n).substring(0, 20);
        svg += `<circle cx="${p.x}" cy="${p.y}" r="6" fill="${color}"/>`;
        svg += `<text x="${p.x}" y="${p.y - 10}" text-anchor="middle" fill="#e6edf3" font-size="10">${label}</text>`;
      });

      // Legend
      let ly = 16;
      Object.entries(LINK_COLORS).forEach(([type, color]) => {
        svg += `<line x1="8" y1="${ly}" x2="22" y2="${ly}" stroke="${color}" stroke-width="2"/>`;
        svg += `<text x="26" y="${ly + 4}" fill="#8b949e" font-size="10">${type}</text>`;
        ly += 16;
      });

      svg += '</svg>';
      container.innerHTML = svg;
    })();

    // --- Signal Table ---
    const tableBody = document.getElementById('signalTable');
    const searchInput = document.getElementById('search');
    const typeFilter = document.getElementById('typeFilter');

    function renderTable() {
      const q = searchInput.value.toLowerCase();
      const tf = typeFilter.value;
      const filtered = SIGNALS.filter(s => {
        if (tf && s.type !== tf) return false;
        if (q && !s.title.toLowerCase().includes(q) && !(s.excerpt || '').toLowerCase().includes(q) && !(s.tags || '').toLowerCase().includes(q)) return false;
        return true;
      });

      if (!filtered.length) {
        tableBody.innerHTML = '<tr><td colspan="5" class="empty-state">No matching signals</td></tr>';
        return;
      }

      tableBody.innerHTML = filtered.reverse().map(s => {
        const tags = (() => { try { return JSON.parse(s.tags || '[]'); } catch { return []; } })();
        return `<tr>
          <td style="white-space:nowrap">${s.date}</td>
          <td><span class="type-badge ${s.type}">${s.type}</span></td>
          <td>${s.title}</td>
          <td>${tags.map(t => `<span class="tag">${t}</span>`).join('')}</td>
          <td>${s.status || '-'}</td>
        </tr>`;
      }).join('');
    }

    searchInput.addEventListener('input', renderTable);
    typeFilter.addEventListener('change', renderTable);
    renderTable();
  </script>
</body>
</html>
```

**Important:** When writing the HTML file, replace the four placeholder tokens with the actual query results:
- `__SIGNALS_JSON__` → the JSON array from query 1 (or `[]` if empty)
- `__TAG_COUNTS_JSON__` → the JSON array from query 2 (or `[]` if empty)
- `__LINKS_JSON__` → the JSON array from query 3 (or `[]` if empty)
- `__SIGNAL_META_JSON__` → the JSON array from query 4 (or `[]` if empty)

Do NOT leave the placeholders as strings. The values must be raw JSON arrays embedded directly in the JavaScript.

### 4. Open in browser

```bash
open .engram/visualize.html
```

## Output

Confirm to the user:
- How many signals are visualized
- The path to the generated file
- That it has been opened in their default browser
