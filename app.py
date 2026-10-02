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

TABLE = "attendance_logs"
COLUMNS = ["emp_id", "emp_name", "dept_name", "work_date", "check_in_time",
           "check_out_time", "anomaly_type", "status", "notified_at"]

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

def read_logs_df() -> pd.DataFrame:
    sb = get_supabase()
    rows, page, size = [], 0, 1000
    while True:
        res = sb.table(TABLE).select(",".join(COLUMNS)).range(page * size, (page + 1) * size - 1).execute()
        rows.extend(res.data)
        if len(res.data) < size:
            break
        page += 1
    df = pd.DataFrame(rows, columns=COLUMNS)
    return df.fillna("").astype(str)

def upsert_log(row: dict):
    get_supabase().table(TABLE).upsert(row, on_conflict="emp_id,work_date").execute()

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
    mask = (df["emp_id"] == emp_id) & (df["work_date"] == today)

    if mask.any():
        idx = df[mask].index[0]
        df.at[idx, "check_in_time"] = now_time
        if df.at[idx, "status"] == "미조치" or not df.at[idx, "status"]:
            df.at[idx, "status"] = "조치완료"
        upsert_log(df.loc[idx, COLUMNS].to_dict())
        emp_name = str(df.at[idx, "emp_name"])
        dept_name = str(df.at[idx, "dept_name"])
    else:
        emp_match = df[df["emp_id"] == emp_id]
        if not emp_match.empty:
            emp_name = str(emp_match.iloc[0]["emp_name"])
            dept_name = str(emp_match.iloc[0]["dept_name"])
        else:
            emp_name = "안송이"
            dept_name = "AI산업팀"

        new_row = {
            "emp_id": emp_id,
            "emp_name": emp_name,
            "dept_name": dept_name,
            "work_date": today,
            "check_in_time": now_time,
            "check_out_time": "",
            "anomaly_type": "정상출근",
            "status": "조치완료",
            "notified_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        upsert_log(new_row)

    return {
        "success": True,
        "message": f"[{emp_id}] {emp_name}({dept_name}) {today} {now_time} 출근 처리가 완료되었습니다. (Supabase 저장 완료)",
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
    mask = (df["emp_id"] == emp_id) & (df["work_date"] == today)

    if mask.any():
        idx = df[mask].index[0]
        df.at[idx, "check_out_time"] = now_time
        df.at[idx, "status"] = "조치완료"
        upsert_log(df.loc[idx, COLUMNS].to_dict())
        emp_name = str(df.at[idx, "emp_name"])
        dept_name = str(df.at[idx, "dept_name"])
    else:
        emp_match = df[df["emp_id"] == emp_id]
        if not emp_match.empty:
            emp_name = str(emp_match.iloc[0]["emp_name"])
            dept_name = str(emp_match.iloc[0]["dept_name"])
        else:
            emp_name = "안송이"
            dept_name = "AI산업팀"

        new_row = {
            "emp_id": emp_id,
            "emp_name": emp_name,
            "dept_name": dept_name,
            "work_date": today,
            "check_in_time": "",
            "check_out_time": now_time,
            "anomaly_type": "정상퇴근",
            "status": "조치완료",
            "notified_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        upsert_log(new_row)

    return {
        "success": True,
        "message": f"[{emp_id}] {emp_name}({dept_name}) {today} {now_time} 퇴근 처리가 완료되었습니다. (Supabase 저장 완료)",
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
