<![CDATA[# Search Module — `search/`

## Owner: P4 (AI / Search / Data / Integration)

## Purpose
Hybrid search combining PostgreSQL full-text search with optional semantic search via embeddings.

## Strategy (MVP)
1. **Primary**: PostgreSQL `tsvector` + `tsquery` full-text search
2. **Autocomplete**: Prefix matching on indexed fields
3. **Future**: pgvector for semantic similarity (post-MVP)

## Pipeline
```
Query → Normalize → Typo Check → FTS Query → Rank → Filter → Results
```

## Searched Entities
- Space objects (name, description, category)
- Lessons (title, summary, content)
- Missions catalog (name, description)
]]>
