-- Non-destructive, repeatable initial collection schema. No client table writes.
create table if not exists public.admin_members (
  user_id uuid primary key references auth.users(id) on delete cascade,
  created_at timestamptz not null default now()
);
create table if not exists public.submissions (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id),
  client_record_id uuid not null,
  payload_hash text not null check (payload_hash ~ '^[a-f0-9]{64}$'),
  payload jsonb not null,
  original_hash text,
  status text not null default 'pending' check(status in ('pending','complete','withdrawn')),
  review_status text not null default 'unreviewed' check(review_status in ('unreviewed','accepted','duplicate','rejected')),
  created_at timestamptz not null default now(),
  completed_at timestamptz,
  unique(owner_id,client_record_id)
);
create index if not exists submissions_original_hash on public.submissions(original_hash);
create table if not exists public.submission_rewards (
  submission_id uuid not null references public.submissions(id) on delete cascade,
  row_number integer not null,
  reward_key text not null,
  quantity integer not null check(quantity >= 0),
  observation jsonb not null,
  primary key(submission_id,row_number)
);
create table if not exists public.submission_images (
  submission_id uuid not null references public.submissions(id) on delete cascade,
  kind text not null check(kind in ('original','annotated')),
  object_path text not null unique,
  sha256 text not null,
  mime text not null check(mime in ('image/png','image/jpeg')),
  bytes integer not null check(bytes > 0 and bytes <= 20971520),
  width integer not null,
  height integer not null,
  primary key(submission_id,kind)
);
create table if not exists public.review_events (
  id bigint generated always as identity primary key,
  submission_id uuid not null references public.submissions(id),
  reviewer_id uuid not null references auth.users(id),
  review_status text not null,
  note text not null default '',
  created_at timestamptz not null default now()
);
alter table public.admin_members enable row level security;
alter table public.submissions enable row level security;
alter table public.submission_rewards enable row level security;
alter table public.submission_images enable row level security;
alter table public.review_events enable row level security;
revoke all on public.admin_members, public.submissions, public.submission_rewards, public.submission_images, public.review_events from anon, authenticated;
-- Access is through JWT-checked Edge Function only; images are NEVER public.
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('raid-evidence','raid-evidence',false,20971520,array['image/png','image/jpeg'])
on conflict(id) do nothing;
create or replace function public.complete_submission(p_id uuid,p_owner uuid,p_hash text,p_images jsonb)
returns void language plpgsql security definer set search_path = public, pg_temp as $$
declare s public.submissions; r jsonb; im jsonb; n integer := 0;
begin
  select * into s from public.submissions where id=p_id and owner_id=p_owner for update;
  if not found or s.payload_hash<>p_hash then raise exception 'Submission mismatch'; end if;
  if s.status='withdrawn' then raise exception 'Submission withdrawn'; end if;
  if s.status='complete' then return; end if;
  for r in select * from jsonb_array_elements(s.payload->'rewards') loop
    insert into public.submission_rewards values(p_id,n,r->>'reward_key',(r->>'quantity')::integer,r);
    n := n+1;
  end loop;
  for im in select * from jsonb_array_elements(p_images) loop
    insert into public.submission_images values(p_id,im->>'kind',im->>'object_path',im->>'sha256',im->>'mime',(im->>'bytes')::integer,(im->>'width')::integer,(im->>'height')::integer);
  end loop;
  update public.submissions set status='complete',completed_at=now() where id=p_id;
end $$;
revoke all on function public.complete_submission(uuid,uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.complete_submission(uuid,uuid,text,jsonb) to service_role;
create or replace function public.review_submission(p_id uuid,p_reviewer uuid,p_status text,p_note text)
returns void language plpgsql security definer set search_path=public,pg_temp as $$
begin
  if not exists(select 1 from public.admin_members where user_id=p_reviewer) then raise exception 'Forbidden'; end if;
  if p_status not in ('unreviewed','accepted','duplicate','rejected') then raise exception 'Invalid status'; end if;
  update public.submissions set review_status=p_status where id=p_id and status='complete';
  if not found then raise exception 'Submission missing'; end if;
  insert into public.review_events(submission_id,reviewer_id,review_status,note) values(p_id,p_reviewer,p_status,left(p_note,500));
end $$;
revoke all on function public.review_submission(uuid,uuid,text,text) from public,anon,authenticated;
grant execute on function public.review_submission(uuid,uuid,text,text) to service_role;
