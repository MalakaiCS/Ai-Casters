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

## 5. (Optional) Move licensing & settings sync onto Supabase

The app already has pluggable licensing and cloud-sync backends. To back them with
Supabase Postgres, create the tables below (**SQL Editor → New query → Run**). RLS
ensures each user only sees their own rows. Wiring the app's licensing/sync clients
to these tables is a small follow-up (ask and it can be added).

```sql
-- Per-user profile with subscription tier. Created automatically on sign-up.
create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  email text,
  tier text not null default 'free',
  created_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

create policy "profiles are readable by owner"
  on public.profiles for select using (auth.uid() = id);
create policy "profiles are updatable by owner"
  on public.profiles for update using (auth.uid() = id);

-- Auto-create a profile row when a new auth user is created.
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

With those in place, the licensing client can read `profiles.tier` (via PostgREST
at `/rest/v1/profiles`) and the settings-sync client can read/write
`user_settings.settings` — all authenticated with the signed-in user's access
token and enforced by RLS.

---

## Security notes

- The **anon** key is safe to ship; the **service_role** key is not — keep it
  server-side only.
- Keep **RLS enabled** on every table; the policies above restrict each row to its
  owner (`auth.uid()`).
- The app stores the returned session locally for "remember me" (see
  [SETUP.md §13](SETUP.md)); sign out from **Account & License** to clear it.
