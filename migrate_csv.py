"""erp_attendance_logs.csv -> Supabase attendance_logs 업로드 (1회 실행)"""
import pandas as pd
from app import get_supabase, COLUMNS, TABLE

df = pd.read_csv("erp_attendance_logs.csv", dtype=str, encoding="utf-8-sig").fillna("")
df = df[COLUMNS].drop_duplicates(subset=["emp_id", "work_date"], keep="last")
rows = df.to_dict(orient="records")
sb = get_supabase()
for i in range(0, len(rows), 500):
    sb.table(TABLE).upsert(rows[i:i+500], on_conflict="emp_id,work_date").execute()
print(f"{len(rows)}건 업로드 완료")
