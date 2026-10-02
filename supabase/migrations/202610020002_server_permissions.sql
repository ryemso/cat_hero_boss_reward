-- Required server access; client roles remain revoked and RLS stays enabled.
grant select on public.admin_members to service_role;
grant select, insert, update on public.submissions to service_role;
grant select on public.submission_rewards, public.submission_images, public.review_events to service_role;
