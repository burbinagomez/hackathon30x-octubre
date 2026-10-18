-- Spec 007: un email por lead, la constancia del --dry-run y la tasa de respuesta por canal.
-- Número PROVISIONAL: el final es el siguiente libre en main al mergear (DDL aprobado por Daniel, plan.md §Migración).

create table public.contactos (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references public.tenants(id),
  lead_id      uuid not null,
  busqueda_id  uuid not null,
  canal        text not null check (canal = 'email'),
  asunto       text not null,
  cuerpo       text not null,
  estado       text not null default 'aprobado' check (estado in
               ('pendiente_aprobacion','aprobado','enviando','enviado',
                'rebotado','no_entregable','descartado')),
  enviado_en   timestamptz,
  respondio_en timestamptz,
  bloqueo      boolean not null default false,
  creado_en    timestamptz not null default now(),
  unique (tenant_id, lead_id, canal),
  foreign key (tenant_id, lead_id) references public.leads (tenant_id, id),
  foreign key (tenant_id, busqueda_id) references public.busquedas (tenant_id, id),
  check ((estado in ('enviado','rebotado')) = (enviado_en is not null)),
  check (respondio_en is null or enviado_en is not null)
);
alter table public.contactos enable row level security;   -- sin FORCE, como la 0002
create policy tenant_aislado on public.contactos
  using (tenant_id = current_setting('app.tenant_id')::uuid)
  with check (tenant_id = current_setting('app.tenant_id')::uuid);
grant select, insert, update on public.contactos to app_rt;   -- sin delete

create view public.v_leads_con_opt_out with (security_invoker = true) as
  select tenant_id, lead_id, opt_out_at from public.cumplimiento where opt_out_at is not null;

create view public.v_tasa_respuesta_canal with (security_invoker = true) as
  select canal,
         count(*) filter (where enviado_en is not null)   as contactados,
         count(*) filter (where respondio_en is not null) as respondieron,
         round(count(*) filter (where respondio_en is not null)::numeric
               / nullif(count(*) filter (where enviado_en is not null), 0), 4) as tasa
  from public.contactos group by canal;
grant select on public.v_leads_con_opt_out, public.v_tasa_respuesta_canal to app_rt;

-- Roles de Supabase: el default privilege les da ALL en todo lo nuevo de public. Solo si existen.
DO $$
BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon')
     AND EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
    REVOKE ALL ON public.contactos, public.v_leads_con_opt_out, public.v_tasa_respuesta_canal FROM anon, authenticated;
  END IF;
END
$$;
