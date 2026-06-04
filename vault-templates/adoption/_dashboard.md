---
type: dashboard
tags: [adoption, agentops, dashboard]
---
# Adoption Dashboard

```dataview
TABLE WITHOUT ID
  date AS "date", machine AS "machine",
  acceptance_rate AS "overall", claudemd_committed AS "accepted", claudemd_pending AS "pending",
  pipeline_acceptance_rate AS "pipeline"
FROM "adoption"
WHERE type = "adoption"
SORT date DESC
LIMIT 40
```

```dataviewjs
const ps = dv.pages('"adoption"').where(p => p.type == "adoption").sort(p => p.date, 'asc');
const lab = p => { const d = p.date; return (d && d.toFormat) ? d.toFormat("MM-dd") : String(d).slice(0,10); };
const labels = ps.map(lab).array();
const pct = f => ps.map(p => { const v = p[f]; return v == null ? null : Math.round(Number(v)*100); }).array();
window.renderChart({ type:'line', data:{ labels, datasets:[ { label:'overall (%)', data:pct('acceptance_rate'), borderColor:'#3b82f6', fill:false }, { label:'pipeline (%)', data:pct('pipeline_acceptance_rate'), borderColor:'#10b981', fill:false } ] }, options:{ scales:{ y:{ beginAtZero:true, max:100 } } } }, this.container);
```
