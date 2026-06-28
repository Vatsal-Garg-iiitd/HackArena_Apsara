create extension if not exists pgcrypto;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text unique,
  full_name text,
  avatar_url text,
  provider text default 'email',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

drop policy if exists "Users can read own profile" on public.profiles;
drop policy if exists "Users can insert own profile" on public.profiles;
drop policy if exists "Users can update own profile" on public.profiles;

create policy "Users can read own profile"
  on public.profiles
  for select
  using (auth.uid() = id);

create policy "Users can insert own profile"
  on public.profiles
  for insert
  with check (auth.uid() = id);

create policy "Users can update own profile"
  on public.profiles
  for update
  using (auth.uid() = id)
  with check (auth.uid() = id);

create table if not exists public.portfolio_items (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  symbol text not null,
  ticker text,
  name text not null,
  sector text,
  index_key text,
  index_name text,
  market_cap numeric,
  price numeric,
  change numeric,
  change_percent numeric,
  open numeric,
  high numeric,
  low numeric,
  previous_close numeric,
  volume numeric,
  spot_price numeric,
  strike_price numeric,
  risk_free_rate numeric,
  expiry_date date,
  revenue numeric,
  health_status text,
  health_reason text,
  source_reference text default 'nsetools.Nse with yahoo_fin.stock_info fallback',
  stock_snapshot jsonb not null default '{}'::jsonb,
  config jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, symbol)
);

alter table public.portfolio_items add column if not exists spot_price numeric;
alter table public.portfolio_items add column if not exists strike_price numeric;
alter table public.portfolio_items add column if not exists risk_free_rate numeric;
alter table public.portfolio_items add column if not exists expiry_date date;
alter table public.portfolio_items add column if not exists revenue numeric;
alter table public.portfolio_items add column if not exists health_status text;
alter table public.portfolio_items add column if not exists health_reason text;
alter table public.portfolio_items add column if not exists source_reference text default 'nsetools.Nse with yahoo_fin.stock_info fallback';

alter table public.portfolio_items enable row level security;

drop policy if exists "Users can read own portfolio" on public.portfolio_items;
drop policy if exists "Users can insert own portfolio" on public.portfolio_items;
drop policy if exists "Users can update own portfolio" on public.portfolio_items;
drop policy if exists "Users can delete own portfolio" on public.portfolio_items;

create policy "Users can read own portfolio"
  on public.portfolio_items
  for select
  using (auth.uid() = user_id);

create policy "Users can insert own portfolio"
  on public.portfolio_items
  for insert
  with check (auth.uid() = user_id);

create policy "Users can update own portfolio"
  on public.portfolio_items
  for update
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "Users can delete own portfolio"
  on public.portfolio_items
  for delete
  using (auth.uid() = user_id);
