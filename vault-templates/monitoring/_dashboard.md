---
type: dashboard
tags: [monitoring, dashboard]
---
# Monitoring Dashboard

## Daily trend (per machine)

```dataview
TABLE WITHOUT ID
  date AS "date", machine AS "machine", prompts_today AS "prompts",
  observations_today AS "obs", tokens_today AS "tokens", errors_real_today AS "err"
FROM "monitoring"
WHERE type = "monitoring"
SORT date DESC, machine ASC
LIMIT 40
```

```dataviewjs
const ps = dv.pages('"monitoring"').where(p => p.type == "monitoring").sort(p => p.date, 'asc');
const lab = p => { const d = p.date; return (d && d.toFormat) ? d.toFormat("MM-dd") : String(d).slice(0,10); };
const labels = ps.map(lab).array();
const num = f => ps.map(p => Number(p[f] ?? 0)).array();
window.renderChart({ type:'line', data:{ labels, datasets:[ { label:'tokens/day', data:num('tokens_today'), borderColor:'#3b82f6', fill:false } ] }, options:{ scales:{ y:{ beginAtZero:true } } } }, this.container);
```

```dataviewjs
const ps = dv.pages('"monitoring"').where(p => p.type == "monitoring").sort(p => p.date, 'asc');
const lab = p => { const d = p.date; return (d && d.toFormat) ? d.toFormat("MM-dd") : String(d).slice(0,10); };
const labels = ps.map(lab).array();
const num = f => ps.map(p => Number(p[f] ?? 0)).array();
window.renderChart({ type:'line', data:{ labels, datasets:[ { label:'prompts', data:num('prompts_today'), borderColor:'#10b981', fill:false }, { label:'observations', data:num('observations_today'), borderColor:'#f59e0b', fill:false } ] }, options:{ scales:{ y:{ beginAtZero:true } } } }, this.container);
```

## Cumulative snapshot (latest per machine)

```dataview
TABLE WITHOUT ID
  rows.machine[0] AS "machine", rows.observations_total[0] AS "obs total",
  rows.tokens_total[0] AS "tokens total", rows.db_size_mb[0] AS "DB(MB)", rows.stale_projects[0] AS "stale"
FROM "monitoring"
WHERE type = "monitoring"
SORT date DESC
GROUP BY machine
```

## Health (days with real errors / failures)

```dataview
TABLE WITHOUT ID
  date AS "date", machine AS "machine", errors_real_today AS "real errors", sessions_failed AS "failed"
FROM "monitoring"
WHERE type = "monitoring" AND (errors_real_today > 0 OR sessions_failed > 0)
SORT date DESC
```

```dataviewjs
const ps = dv.pages('"monitoring"').where(p => p.type == "monitoring").sort(p => p.date, 'asc');
const lab = p => { const d = p.date; return (d && d.toFormat) ? d.toFormat("MM-dd") : String(d).slice(0,10); };
const labels = ps.map(lab).array();
const num = f => ps.map(p => Number(p[f] ?? 0)).array();
window.renderChart({ type:'line', data:{ labels, datasets:[ { label:'real errors', data:num('errors_real_today'), borderColor:'#ef4444', fill:false } ] }, options:{ scales:{ y:{ beginAtZero:true } } } }, this.container);
```
