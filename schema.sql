create table if not exists public.attendance_logs (
  emp_id         text not null,
  emp_name       text,
  dept_name      text,
  work_date      text not null,
  check_in_time  text default '',
  check_out_time text default '',
  anomaly_type   text default '',
  status         text default '',
  notified_at    text default '',
  primary key (emp_id, work_date)
);
alter table public.attendance_logs enable row level security;
