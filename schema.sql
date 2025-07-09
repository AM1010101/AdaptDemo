create table public.logs (
  id uuid not null default gen_random_uuid (),
  log_level text not null,
  message text not null,
  context jsonb null,
  created_at timestamp with time zone null default now(),
  user_id uuid null,
  source text null,
  constraint logs_pkey primary key (id),
  constraint fk_user foreign KEY (user_id) references auth.users (id) on delete set null
) TABLESPACE pg_default;

create table public.raw_product_scrapes (
  scrape_id uuid not null default gen_random_uuid (),
  source_id uuid null,
  entry_date timestamp with time zone null default CURRENT_TIMESTAMP,
  make text not null,
  model text not null,
  storage_capacity text null,
  grade text null,
  colour text null,
  ce_mark boolean null,
  partial_vat boolean null,
  purchase_price numeric(10, 2) null,
  trade_in_price numeric(10, 2) null,
  stock_count integer null,
  meta_data text null,
  scrape_instance uuid null,
  constraint raw_product_scrapes_pkey primary key (scrape_id),
  constraint raw_product_scrapes_source_id_fkey foreign KEY (source_id) references sources (source_id) on delete RESTRICT
) TABLESPACE pg_default;

create index IF not exists idx_scrape_instance on public.raw_product_scrapes using btree (scrape_instance) TABLESPACE pg_default;

create table public.sources (
  source_id uuid not null default gen_random_uuid (),
  source_base_url text not null,
  source_name text null,
  source_type text null,
  source_description text null,
  constraint sources_pkey primary key (source_id),
  constraint sources_source_base_url_key unique (source_base_url)
) TABLESPACE pg_default;