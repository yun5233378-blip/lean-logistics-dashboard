# Security Policy

## Public Repository Rules

This repository is intended to be safe for public GitHub hosting. Do not commit:

- `.env` files or production environment files
- Admin tokens, Cloudflare tokens, SSH keys, API keys, database passwords
- SQLite databases, PostgreSQL dumps, backup archives, import/export files
- Raw customer shipment data, Excel files, Word source documents, screenshots with business identifiers
- Real server IP addresses, private hostnames, operator usernames, or deployment credentials

Use placeholders such as `<SERVER_IP>`, `<your-domain>`, and `<ADMIN_API_TOKEN>` in public examples.

## Required Production Secrets

Production values must be injected through the server environment or GitHub Secrets:

- `DATABASE_URL`
- `ADMIN_API_TOKEN`
- `BACKUP_DIR`
- `TENCENT_HOST`
- `TENCENT_SSH_PORT`
- `TENCENT_USER`
- `TENCENT_SSH_KEY`

Never paste these values into README files, deployment examples, issues, commits, or pull requests.

## Data Handling

The main dashboard only reads user-imported rows marked as `source_id = BUSINESS_UPLOAD`. Public reference datasets are used for model context only.

Before importing business data:

1. Remove customer names, phone numbers, addresses, tracking numbers, and invoice references unless they are essential.
2. Replace external business identifiers with internal batch IDs.
3. Keep raw CSV/Excel files outside the Git repository.
4. Store backups in the configured private backup directory, not in the repo.

## Release Checklist

Run before publishing:

```powershell
python scripts/security_scan.py
python -m backend.verify_backend
git status --short
```

If a real secret was committed, rotate it immediately and rewrite or replace the public repository history before continuing to use that credential.
