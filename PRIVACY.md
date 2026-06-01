# Privacy Notes

LeanLogiLens should be deployed with tenant-owned operational data. The repository contains code, public reference metadata, and import templates only.

## Data Minimization

For prototype and trial runs, prefer these fields:

- Batch ID
- Channel type
- Origin and destination region
- Piece count and CBM
- Milestone timestamps

Avoid committing or importing personally identifiable information unless a production privacy review approves it.

## Operational Data Boundary

- User business data enters through the admin import endpoint.
- Public datasets remain model references and are not displayed as tenant operations.
- Local runtime files, backups, exports, and raw office documents are ignored by Git.

## Recommended Sanitization

Before sharing a dataset, remove or hash:

- Customer names
- Phone numbers
- Email addresses
- Full street addresses
- Tracking numbers
- Invoice and payment references
- Carrier account numbers

Keep the mapping table in a private system outside this repository.
