# Backup and restore drill: latest result

Written by `scripts/backup-restore-drill.py`. Re-run it to refresh this file.

- Date: 2026-10-22 21:13 UTC
- Source: database `isd_sim` (synthetic data only)
- Dump size: 337 KiB; dump took 0.2 s; restore took 0.6 s
- Result: **PASS**

| Check | Result | Detail |
|---|---|---|
| every table has the same number of rows | pass | 53 tables, 3705 rows |
| audit chain verifies in the restored copy | pass | 1210 entries |
| ledgers reconcile in the restored copy | pass |  |
| append-only trigger came back (UPDATE refused) | pass |  |
| app role still cannot UPDATE or DELETE protected tables | pass | 12 tables |
| schema version matches | pass | 0013 |

Timings come from a small synthetic database on one machine. They show the procedure works, not
how long a real facility's restore will take; repeat the drill on a production-sized copy.
