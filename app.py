import os
import io
import csv
import urllib.parse
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, Query, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

app = FastAPI(
    title="GBSA ERP 근태리더기내역조회 API",
    description="경기도경제과학진흥원(GBSA) 사내 ERP - 고전 레거시 ERP 버전",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TABLE = "attendance"

_supabase: Optional[Client] = None

def get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise HTTPException(status_code=500, detail="SUPABASE_URL / SUPABASE_KEY 환경변수가 설정되지 않았습니다.")
        _supabase = create_client(url, key)
    return _supabase

def generate_card_number(emp_id: str) -> str:
    """사번 기반 고정 13자리 카드번호 생성"""
    digits = "".join([c for c in str(emp_id) if c.isdigit()])
    raw = (digits * 3)[:9]
    return f"9410{raw}".ljust(13, '0')[:13]

class CheckInRequest(BaseModel):
    emp_id: str
    work_date: Optional[str] = None
    check_in_time: Optional[str] = None

class CheckOutRequest(BaseModel):
    emp_id: str
    work_date: Optional[str] = None
    check_out_time: Optional[str] = None

def insert_attendance_tag(emp_id: str, emp_name: str, dept_name: str, tag_date: str, tag_time: str, event_type: str):
    sb = get_supabase()
    log_id = f"ATT-LOG-{tag_date.replace('-', '')}-{datetime.now().strftime('%H%M%S%f')[:8]}"
    new_tag = {
        "log_id": log_id,
        "emp_id": emp_id,
        "emp_name": emp_name,
        "dept_name": dept_name,
        "tag_date": tag_date,
        "tag_time": tag_time,
        "event_type": event_type,
        "gate_name": "웹ERP 단말기",
        "device_id": "WEB-ERP-01",
        "auth_method": "웹인증",
        "raw_status": "SUCCESS",
        "ip_address": "127.0.0.1"
    }
    sb.table(TABLE).insert(new_tag).execute()

def read_logs_df() -> pd.DataFrame:
    try:
        sb = get_supabase()
        res = sb.table(TABLE).select("*").execute()
        raw_rows = res.data
        if not raw_rows:
            return pd.DataFrame(columns=["emp_id", "emp_name", "dept_name", "work_date", "check_in_time", "check_out_time", "anomaly_type", "status", "notified_at"])

        grouped = {}
        for r in raw_rows:
            emp_id = str(r.get("emp_id", ""))
            work_date = str(r.get("tag_date", ""))
            key = (emp_id, work_date)
            if key not in grouped:
                grouped[key] = {
                    "emp_id": emp_id,
                    "emp_name": str(r.get("emp_name", "")),
                    "dept_name": str(r.get("dept_name", "")),
                    "work_date": work_date,
                    "check_in_time": "",
                    "check_out_time": "",
                    "anomaly_type": "정상근무",
                    "status": "조치완료",
                    "notified_at": ""
                }

            event_type = str(r.get("event_type", "")).upper()
            tag_time = str(r.get("tag_time", ""))
            if event_type == "CHECK_IN":
                if not grouped[key]["check_in_time"] or tag_time < grouped[key]["check_in_time"]:
                    grouped[key]["check_in_time"] = tag_time
            elif event_type == "CHECK_OUT":
                if not grouped[key]["check_out_time"] or tag_time > grouped[key]["check_out_time"]:
                    grouped[key]["check_out_time"] = tag_time

        records = []
        for g in grouped.values():
            in_t = g["check_in_time"]
            out_t = g["check_out_time"]
            if in_t and in_t > "09:00:00":
                g["anomaly_type"] = "지각"
            elif out_t and out_t < "18:00:00":
                g["anomaly_type"] = "조퇴"
            elif in_t and not out_t:
                g["anomaly_type"] = "미퇴근"
            elif not in_t and out_t:
                g["anomaly_type"] = "미출근"
            else:
                g["anomaly_type"] = "정상근무"
            records.append(g)

        df = pd.DataFrame(records)
        return df.fillna("").astype(str)
    except Exception as e:
        print(f"[Supabase Read Error/Warning] {e}")
        return pd.DataFrame(columns=["emp_id", "emp_name", "dept_name", "work_date", "check_in_time", "check_out_time", "anomaly_type", "status", "notified_at"])

def get_filtered_logs(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    emp_name: Optional[str] = None,
    emp_id: Optional[str] = None
) -> pd.DataFrame:
    df = read_logs_df()
    filtered = df.copy()

    if start_date and isinstance(start_date, str) and start_date.strip():
        filtered = filtered[filtered["work_date"] >= start_date.strip()]

    if end_date and isinstance(end_date, str) and end_date.strip():
        filtered = filtered[filtered["work_date"] <= end_date.strip()]

    if emp_name and isinstance(emp_name, str) and emp_name.strip():
        q = emp_name.strip()
        filtered = filtered[
            filtered["emp_name"].str.contains(q, case=False, na=False) |
            filtered["emp_id"].str.contains(q, case=False, na=False) |
            filtered["dept_name"].str.contains(q, case=False, na=False)
        ]

    if emp_id and isinstance(emp_id, str) and emp_id.strip():
        filtered = filtered[filtered["emp_id"] == emp_id.strip()]

    filtered = filtered.sort_values(by=["work_date", "emp_id"], ascending=[False, True])
    return filtered

@app.get("/api/attendance/logs")
def get_attendance_logs(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    emp_name: Optional[str] = Query(None),
    emp_id: Optional[str] = Query(None)
):
    s_date = start_date if isinstance(start_date, str) else None
    e_date = end_date if isinstance(end_date, str) else None
    e_name = emp_name if isinstance(emp_name, str) else None
    e_id = emp_id if isinstance(emp_id, str) else None

    filtered = get_filtered_logs(s_date, e_date, e_name, e_id)
    
    result = []
    for idx, row in enumerate(filtered.to_dict(orient="records"), start=1):
        emp_id_val = str(row.get("emp_id", ""))
        card_num = generate_card_number(emp_id_val)
        result.append({
            "no": idx,
            "work_date": str(row.get("work_date", "")),
            "emp_name": str(row.get("emp_name", "")),
            "emp_id": emp_id_val,
            "dept_name": str(row.get("dept_name", "")),
            "card_number": card_num,
            "work_type": "일반근무",
            "work_shape": "일반근무",
            "check_in_time": str(row.get("check_in_time", "")) if row.get("check_in_time") else "",
            "check_out_time": str(row.get("check_out_time", "")) if row.get("check_out_time") else "",
            "anomaly_type": str(row.get("anomaly_type", "")),
            "status": str(row.get("status", ""))
        })

    return {
        "success": True,
        "total": len(result),
        "data": result
    }

@app.post("/api/attendance/check-in")
def process_check_in(req: CheckInRequest):
    df = read_logs_df()
    today = req.work_date or datetime.now().strftime("%Y-%m-%d")
    now_time = req.check_in_time or datetime.now().strftime("%H:%M:%S")

    emp_id = req.emp_id.strip()
    emp_match = df[df["emp_id"] == emp_id]
    if not emp_match.empty:
        emp_name = str(emp_match.iloc[0]["emp_name"])
        dept_name = str(emp_match.iloc[0]["dept_name"])
    else:
        emp_name = "안송이"
        dept_name = "AI산업팀"

    insert_attendance_tag(emp_id, emp_name, dept_name, today, now_time, "CHECK_IN")

    return {
        "success": True,
        "message": f"[{emp_id}] {emp_name}({dept_name}) {today} {now_time} 출근 처리가 완료되었습니다. (Supabase attendance 저장 완료)",
        "emp_id": emp_id,
        "emp_name": emp_name,
        "dept_name": dept_name,
        "work_date": today,
        "check_in_time": now_time
    }

@app.post("/api/attendance/check-out")
def process_check_out(req: CheckOutRequest):
    df = read_logs_df()
    today = req.work_date or datetime.now().strftime("%Y-%m-%d")
    now_time = req.check_out_time or datetime.now().strftime("%H:%M:%S")

    emp_id = req.emp_id.strip()
    emp_match = df[df["emp_id"] == emp_id]
    if not emp_match.empty:
        emp_name = str(emp_match.iloc[0]["emp_name"])
        dept_name = str(emp_match.iloc[0]["dept_name"])
    else:
        emp_name = "안송이"
        dept_name = "AI산업팀"

    insert_attendance_tag(emp_id, emp_name, dept_name, today, now_time, "CHECK_OUT")

    return {
        "success": True,
        "message": f"[{emp_id}] {emp_name}({dept_name}) {today} {now_time} 퇴근 처리가 완료되었습니다. (Supabase attendance 저장 완료)",
        "emp_id": emp_id,
        "emp_name": emp_name,
        "dept_name": dept_name,
        "work_date": today,
        "check_out_time": now_time
    }

@app.get("/api/attendance/export/csv")
def export_csv(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    emp_name: Optional[str] = Query(None)
):
    try:
        filtered = get_filtered_logs(start_date, end_date, emp_name)
        stream = io.StringIO()
        filtered.to_csv(stream, index=False, encoding="utf-8-sig")
        
        raw_filename = f"GBSA_attendance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        encoded_filename = urllib.parse.quote(f"GBSA_근태리더기내역_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")

        headers = {
            'Content-Disposition': f'attachment; filename="{raw_filename}"; filename*=UTF-8\'\'{encoded_filename}'
        }
        return Response(content=stream.getvalue(), media_type="text/csv", headers=headers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CSV export error: {str(e)}")

@app.get("/api/attendance/export/excel")
def export_excel(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    emp_name: Optional[str] = Query(None)
):
    try:
        filtered = get_filtered_logs(start_date, end_date, emp_name)

        rows = []
        for idx, r in enumerate(filtered.to_dict(orient="records"), start=1):
            emp_id_val = str(r.get("emp_id", ""))
            rows.append({
                "No": idx,
                "근무일": str(r.get("work_date", "")),
                "사원": str(r.get("emp_name", "")),
                "사번": emp_id_val,
                "부서": str(r.get("dept_name", "")),
                "카드번호": generate_card_number(emp_id_val),
                "근무유형(ERP)": "일반근무",
                "근무형태(ERP)": "일반근무",
                "출근시간": str(r.get("check_in_time", "")),
                "퇴근시간": str(r.get("check_out_time", ""))
            })

        excel_df = pd.DataFrame(rows)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            excel_df.to_excel(writer, sheet_name='근태리더기내역조회', index=False)
        output.seek(0)

        raw_filename = f"GBSA_attendance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        encoded_filename = urllib.parse.quote(f"GBSA_근태리더기내역_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")

        headers = {
            'Content-Disposition': f'attachment; filename="{raw_filename}"; filename*=UTF-8\'\'{encoded_filename}'
        }
        return Response(content=output.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers=headers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Excel generation error: {str(e)}")

@app.get("/api/employees")
def get_employees():
    df = read_logs_df()
    employees = df[["emp_id", "emp_name", "dept_name"]].drop_duplicates().to_dict(orient="records")
    return {"success": True, "employees": employees}

static_dir = os.path.join(BASE_DIR, "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)

app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def read_root():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse(content="<h1>GBSA ERP Legacy System API</h1>", status_code=200)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
