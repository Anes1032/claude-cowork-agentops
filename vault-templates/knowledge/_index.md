---
type: index
tags: [knowledge, index]
---
# Knowledge Index

## All notes (newest first)

```dataview
TABLE WITHOUT ID file.link AS "note", project AS "project", tags AS "tags", created AS "created"
FROM "knowledge"
WHERE type = "knowledge"
SORT created DESC
```

## By project

```dataview
TABLE rows.file.link AS "notes"
FROM "knowledge"
WHERE type = "knowledge"
GROUP BY project
SORT project ASC
```

## By tag

```dataview
TABLE rows.file.link AS "notes"
FROM "knowledge"
WHERE type = "knowledge"
FLATTEN tags AS tag
GROUP BY tag
SORT tag ASC
```
