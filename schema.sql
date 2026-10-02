-- 1. 직원 관리 전용 테이블 (employees)
create table if not exists public.employees (
  emp_id     text primary key,
  emp_name   text not null,
  dept_name  text not null,
  position   text default '선임연구원',
  email      text default '',
  phone      text default '',
  status     text default '재직',
  created_at timestamptz default now()
);

-- RLS 활성화 및 권한 설정
alter table public.employees enable row level security;
create policy "Allow all operations on employees" on public.employees
  for all using (true) with check (true);

-- 기본 직원 데이터 등록
insert into public.employees (emp_id, emp_name, dept_name, position, status)
values
  ('GBSA2018012', '안송이', 'AI산업팀', '선임연구원', '재직'),
  ('GBSA2019024', '김민준', '기획조정실', '책임연구원', '재직'),
  ('GBSA2020045', '이서연', '인사총무팀', '선임연구원', '재직'),
  ('GBSA2021077', '박도현', 'AI산업팀', '주임연구원', '재직'),
  ('GBSA2022091', '최유진', '기획조정실', '선임연구원', '재직'),
  ('GBSA2023105', '정다은', '인사총무팀', '주임연구원', '재직')
on conflict (emp_id) do nothing;

-- 2. 근태 리더기 로그 관리 테이블 (attendance)
create table if not exists public.attendance (
  log_id      text primary key,
  emp_id      text not null references public.employees(emp_id),
  emp_name    text,
  dept_name   text,
  tag_date    text not null,
  tag_time    text not null,
  event_type  text not null, -- 'CHECK_IN' or 'CHECK_OUT'
  gate_name   text default '본관1층 중앙게이트 #01',
  device_id   text default 'FP-GATE-1F-MAIN',
  auth_method text default '지문인식',
  raw_status  text default 'SUCCESS',
  ip_address  text default '10.120.10.11',
  created_at  timestamptz default now()
);

alter table public.attendance enable row level security;
create policy "Allow all operations on attendance" on public.attendance
  for all using (true) with check (true);
