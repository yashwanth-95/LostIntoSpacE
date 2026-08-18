<![CDATA[# Deployment — `deployment/`

## Owner: P2 (Backend / DevOps)

## Structure
- `docker/` — Dockerfiles and docker-compose.yml
- `nginx/` — Nginx config for reverse proxy
- `scripts/` — Deploy scripts

## Local Development
```bash
docker-compose -f deployment/docker/docker-compose.dev.yml up
```

## Environments
| Env | Purpose | Database | AI |
|-----|---------|----------|-----|
| local | Development | Local PostgreSQL | Mock/optional |
| staging | Team testing | Shared PostgreSQL | Real provider |
| demo | SIH presentation | Pre-seeded, bundled fallbacks | Cached responses |
]]>
