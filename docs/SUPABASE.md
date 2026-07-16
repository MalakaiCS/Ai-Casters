<p align="center">
  <img src="../src/ai_caster/ui/assets/logo.png" alt="AI Casters" width="220">
</p>

# AI Casters — Supabase Setup

AI Casters can use **Supabase Auth (GoTrue)** for the login/sign-up system. This
guide gets you from a new Supabase project to working sign-up + sign-in in the
desktop app, and includes an optional database schema for taking licensing and
settings-sync onto Supabase too.

The app talks to Supabase through the standard Auth REST API using your project's
**anon (public) key**, which is designed to be embedded in client apps — access is
governed by Row Level Security (RLS) on the database, not by hiding the key.

---

## 1. Create a project

1. Sign in at <https://supabase.com> and create a new project.
2. Choose a strong database password and a region near your users.

## 2. Get the URL and anon key

In the project dashboard: **Project Settings → API**. Copy:

- **Project URL** — `https://<your-ref>.supabase.co`
- **Project API keys → `anon` `public`** — a long JWT.

> ⚠️ **Never** put the `service_role` key in the app or the repo. It bypasses RLS.
> Only the **anon** key belongs in the desktop client.

## 3. Enable email auth

**Authentication → Providers → Email**: make sure it's enabled.

- **Confirm email ON** (default): after sign-up the user gets a confirmation
  email and must click it before they can sign in. The app shows
  *"Account created — check your email to confirm, then sign in."*
- **Confirm email OFF**: sign-up signs the user straight in (handy for testing).

Optionally set your site URL and email templates under **Authentication → URL
Configuration** / **Email Templates**.

## 4. Point the app at Supabase

In the app: **Settings → Account** and set:

| Setting | Value |
|---------|-------|
| `provider` | `supabase` |
| `supabase_url` | `https://<your-ref>.supabase.co` |
| `supabase_anon_key` | your **anon** key |

…or edit `settings.json` directly (see [SETUP.md §13](SETUP.md) for its location):

```json
{
  "account": {
    "provider": "supabase",
    "supabase_url": "https://YOUR-REF.supabase.co",
    "supabase_anon_key": "YOUR-ANON-KEY",
    "remember": true,
    "auto_login": true
  }
}
```

Restart the app. In **Account & License**, **Create account** registers via
Supabase and **Sign in** authenticates against it. If Supabase is selected but the
URL/key are missing, the app safely falls back to offline auth.

---

## 5. (Optional) Back licensing & settings sync with Supabase

Licensing (subscription tier + devices) and cloud settings-sync can run on your
Supabase project too. This is **built in** — you just create the tables and switch
the providers on.

**a. Create the tables.** Run the SQL below in **SQL Editor → New query → Run**.
RLS ensures each user only sees their own rows.

**b. Turn the providers on** in `settings.json` (they reuse the Account
`supabase_url` + `supabase_anon_key`, so no extra keys):

```json
{
  "licensing": { "provider": "supabase" },
  "sync": { "provider": "supabase", "enabled": true, "auto_sync": true }
}
```

The licensing client then reads the signed-in user's `profiles.tier` (and
registers/lists their devices); the sync client reads/writes their
`user_settings.settings` row. Both authenticate with the user's access token, so
**RLS** is what secures the data — never a database password. Cloud sync also
requires the `CLOUD_SYNC` entitlement (Studio tier), so set that user's
`profiles.tier` to `studio` to exercise it.

```sql
-- Per-user profile with subscription tier and RBAC role. Created automatically
-- on sign-up. `role` drives in-app permissions (see "User roles" below).
create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  email text,
  display_name text,
  tier text not null default 'free',
  tier_expires_at timestamptz,  -- null = perpetual/lifetime; else the tier lapses to free
  role text not null default 'user'
    check (role in ('owner','founder','admin','staff','partner','user')),
  created_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

-- Read the caller's role WITHOUT triggering RLS. This is the key to avoiding
-- "infinite recursion detected in policy for relation profiles": a policy on
-- profiles must NOT run a plain sub-select on profiles (that re-evaluates the
-- policies forever). A SECURITY DEFINER function bypasses RLS, so it's safe to
-- call from inside a profiles policy.
create or replace function public.is_manager()
returns boolean language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.profiles
    where id = auth.uid() and role in ('owner','founder','admin')
  );
$$;

-- A user can always read their own row.
create policy "profiles are readable by owner"
  on public.profiles for select using (auth.uid() = id);

-- Managers (admin/founder/owner) can read every profile for the Team view.
-- Uses the SECURITY DEFINER helper above, so there is no recursion.
create policy "profiles are readable by managers"
  on public.profiles for select using (public.is_manager());

-- Role/tier are changed ONLY through the set_user_role RPC and the server, so
-- there is deliberately no direct UPDATE policy for users (a self-update policy
-- that sub-selects profiles would recurse; leaving it out is simpler and safer).

-- Auto-create a profile row when a new auth user is created (role defaults to
-- 'user'; the very first Owner is set once by hand — see "User roles").
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, email) values (new.id, new.email)
  on conflict (id) do nothing;
  return new;
end; $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Registered devices (seats) per account.
create table if not exists public.devices (
  device_id text not null,
  user_id uuid not null references auth.users (id) on delete cascade,
  name text,
  last_seen timestamptz not null default now(),
  primary key (user_id, device_id)
);
alter table public.devices enable row level security;
create policy "devices are owned by user"
  on public.devices for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- Cloud settings sync: one JSON document per account.
create table if not exists public.user_settings (
  user_id uuid primary key references auth.users (id) on delete cascade,
  settings jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);
alter table public.user_settings enable row level security;
create policy "settings are owned by user"
  on public.user_settings for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
```

With those tables in place and the providers switched on (step 5b), the licensing
client reads `profiles.tier` via PostgREST at `/rest/v1/profiles` and the
settings-sync client reads/writes `user_settings.settings` — all authenticated
with the signed-in user's access token and enforced by RLS.

---

## 5c. User roles (Owner / Founder / Admin / Staff / Partner / User)

Roles form a strict hierarchy (Owner is highest, User is the default). They gate
in-app features:

| Role | Grants |
|------|--------|
| **Owner** | Everything, including assigning any role below Owner |
| **Founder** | Manage the team, train the AI |
| **Admin** | Manage the team (assign roles below Admin), train the AI |
| **Staff** | Train the AI (vocabulary / tone / excitement) |
| **Partner** | Standard access |
| **User** *(default)* | Standard access |

The app reads the signed-in user's `profiles.role` after login. Changing a role
goes through a **security-definer RPC** so the anon key can't be used to escalate:
the function re-checks the caller's own role and refuses to grant a role at or
above the caller's rank.

```sql
-- Rank helper: higher number = more privileged.
create or replace function public.role_rank(r text)
returns int language sql immutable as $$
  select case r
    when 'owner' then 6 when 'founder' then 5 when 'admin' then 4
    when 'staff' then 3 when 'partner' then 2 else 1 end;
$$;

-- Change a member's role. Only admin+ may call it, and only to grant a role
-- STRICTLY BELOW the caller's own rank (so no one can create a peer/superior).
create or replace function public.set_user_role(target_user uuid, new_role text)
returns void language plpgsql security definer set search_path = public as $$
declare
  caller_role text;
begin
  select role into caller_role from public.profiles where id = auth.uid();
  if caller_role is null or public.role_rank(caller_role) < public.role_rank('admin') then
    raise exception 'insufficient privileges' using errcode = '42501';
  end if;
  if new_role not in ('owner','founder','admin','staff','partner','user') then
    raise exception 'invalid role';
  end if;
  if public.role_rank(new_role) >= public.role_rank(caller_role) then
    raise exception 'cannot assign a role at or above your own' using errcode = '42501';
  end if;
  if public.role_rank((select role from public.profiles where id = target_user))
     >= public.role_rank(caller_role) then
    raise exception 'cannot modify a peer or superior' using errcode = '42501';
  end if;
  update public.profiles set role = new_role where id = target_user;
end; $$;

revoke all on function public.set_user_role(uuid, text) from public;
grant execute on function public.set_user_role(uuid, text) to authenticated;
```

### Subscription tiers & duration

Managers (Admin and above) can also set a member's **tier** and how long it lasts
from **Team & Roles** — 1 day, 7/30/90 days, 1 year, or lifetime. A dated grant
lapses back to `free` automatically (the app checks `tier_expires_at`; a null
expiry is perpetual). This goes through its own security-definer RPC:

```sql
-- (the tier_expires_at column is already in the profiles table above; if you
-- created profiles before adding it, run this once:)
alter table public.profiles add column if not exists tier_expires_at timestamptz;

create or replace function public.set_user_tier(
  target_user uuid, new_tier text, expires_at timestamptz
) returns void language plpgsql security definer set search_path = public as $$
begin
  if not public.is_manager() then
    raise exception 'insufficient privileges' using errcode = '42501';
  end if;
  if new_tier not in ('free','pro','studio') then
    raise exception 'invalid tier';
  end if;
  update public.profiles
    set tier = new_tier, tier_expires_at = expires_at
    where id = target_user;
end; $$;

revoke all on function public.set_user_tier(uuid, text, timestamptz) from public;
grant execute on function public.set_user_tier(uuid, text, timestamptz) to authenticated;
```

**Bootstrap the first Owner** (run once, after you've signed up your own account):

```sql
update public.profiles set role = 'owner'
where email = 'you@example.com';  -- your account's email
```

After that, sign in from the app and use **Team & Roles** to promote everyone
else — no more SQL needed.

---

## 6. Ship a pre-configured build (recommended for distribution)

So end users don't have to paste anything, the installer can be **baked** with your
Supabase URL + anon key — kept out of the (public) source via GitHub Actions
secrets:

1. In the repo: **Settings → Secrets and variables → Actions → New repository
   secret**, add:
   - `SUPABASE_URL` = `https://<your-ref>.supabase.co`
   - `SUPABASE_ANON_KEY` = your anon key
2. Build a release (push a `v*` tag or run the **Release**/**Build Windows
   installer** workflow). The build writes `ai_caster/deploy_defaults.json` from
   the secrets and bundles it.

On first launch the app seeds its settings from those defaults (a user's existing
`settings.json` is never overwritten). The file is git-ignored, so keys never enter
the repo. For local development you can instead set `AI_CASTER_SUPABASE_URL` and
`AI_CASTER_SUPABASE_ANON_KEY` environment variables.

> The baked defaults configure **auth**. Leave licensing/sync on `offline` until the
> tables from step 5 exist; enable them per step 5b (or add those sections to the
> bundled defaults) once the schema is in place.

## Security notes

- The **anon** key is safe to ship; the **service_role** key is not — keep it
  server-side only.
- Keep **RLS enabled** on every table; the policies above restrict each row to its
  owner (`auth.uid()`).
- The app stores the returned session locally for "remember me" (see
  [SETUP.md §13](SETUP.md)); sign out from **Account & License** to clear it.
