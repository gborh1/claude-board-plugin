# Supabase Migration Rules

## Core Rules

- **NEVER use `supabase db reset`** — destroys all data
- **NEVER apply migration SQL directly** — no `psql -f`, no piping SQL
- **ALWAYS use `supabase migration up`** to apply migrations
- **ALWAYS use `supabase migration new <name>`** to create migrations (auto-timestamps, no manual numbering)
- Write migrations to be **idempotent** — use `IF NOT EXISTS`, `OR REPLACE`, `ON CONFLICT DO NOTHING`

## Parallel Worktree Workflow

All worktrees share one local Supabase. Other worktrees' migrations can cause ledger mismatches. Fix with:

```bash
# 1. Check for "remote only" entries from other worktrees
supabase migration list --local

# 2. Remove any "remote only" entries (keeps schema changes, just clears the ledger record)
supabase migration repair --status reverted <version>

# 3. Apply your migration (--include-all forces past any timestamp ordering issues)
supabase migration up --include-all
```

**Dev only:** Use `--include-all` in local dev. Never use it in staging/production — there, all migration files are present and apply in correct order without flags.

## Iterating on a Migration

1. Drop the object: `DROP FUNCTION IF EXISTS ...;`
2. Remove the tracking record: `DELETE FROM supabase_migrations.schema_migrations WHERE version = '<timestamp>';`
3. Edit the migration file
4. Re-run `supabase migration up`
