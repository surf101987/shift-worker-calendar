from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
from datetime import datetime, timedelta
import io
import uuid

app = FastAPI(title="Shift Worker Calendar")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def create_ics(events):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Shift Worker Calendar//EN", "CALSCALE:GREGORIAN"]
    for ev in events:
        uid = str(uuid.uuid4())
        dtstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        lines += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{dtstamp}",
                  f"DTSTART:{ev['dtstart'].strftime('%Y%m%dT%H%M%S')}",
                  f"DTEND:{ev['dtend'].strftime('%Y%m%dT%H%M%S')}",
                  f"SUMMARY:{ev.get('summary', 'Shift')}",
                  f"DESCRIPTION:{ev.get('description', '')}".replace("\n", "\\n"),
                  f"LOCATION:{ev.get('location', '')}", "END:VEVENT"]
    lines += ["END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n"

@app.post("/upload-and-convert")
async def upload(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(('.csv', '.xlsx', '.xls')):
        raise HTTPException(400, "Only CSV/Excel files")
    content = await file.read()
    df = pd.read_csv(io.BytesIO(content)) if file.filename.endswith('.csv') else pd.read_excel(io.BytesIO(content))

    # auto-detect columns
    cols = {k.lower(): c for c in df.columns for k in [c.lower()]}
    title_col = next((c for k, c in cols.items() if any(x in k for x in ['title','subject','event','name','summary'])), None)
    start_date = next((c for k, c in cols.items() if any(x in k for x in ['start date','date','startdate'])), None)
    start_time = next((c for k, c in cols.items() if 'time' in k or 'starttime' in k), None)
    end_time = next((c for k, c in cols.items() if 'endtime' in k or 'end time' in k), None)
    desc_col = cols.get('description', cols.get('notes', ''))
    loc_col = cols.get('location', cols.get('place', ''))

    events = []
    for _, row in df.iterrows():
        try:
            sdate = pd.to_datetime(row[start_date]).date()
            stime = pd.to_datetime(row[start_time]).time() if pd.notna(row.get(start_time, '')) else datetime.min.time()
            dtstart = datetime.combine(sdate, stime)
            dtend = dtstart + timedelta(hours=8)  # default 8-hour shift
            if end_time and pd.notna(row.get(end_time)):
                etime = pd.to_datetime(row[end_time]).time()
                dtend = datetime.combine(sdate, etime)
            events.append({"summary": str(row[title_col]), "dtstart": dtstart, "dtend": dtend,
                           "description": str(row[desc_col]) if desc_col else "",
                           "location": str(row[loc_col]) if loc_col else ""})
        except:
            continue

    if not events:
        raise HTTPException(400, "No valid shifts found")
    ics = create_ics(events)
    return StreamingResponse(io.BytesIO(ics.encode()), media_type="text/calendar",
                             headers={"Content-Disposition": f'attachment; filename="shifts.ics"'})

@app.get("/")
async def home():
    return HTMLResponse("""
    <html><head><title>Shift Worker Calendar</title>
    <style>body{font-family:Arial;background:#355E3B;color:white;text-align:center;padding:50px}
    h1{color:#fff} button{padding:15px 30px;font-size:18px;background:#fff;color:#355E3B;border:none;border-radius:8px}</style></head>
    <body><h1>Shift Worker Calendar</h1><p>Upload your roster → get .ics file</p>
    <input type="file" id="f" accept=".csv,.xlsx"><br><br>
    <button onclick="upload()">Convert & Download</button>
    <script>
    async function upload(){let file=document.getElementById('f').files[0];
    let fd=new FormData();fd.append("file",file);
    let r=await fetch("/upload-and-convert",{method:"POST",body:fd});
    if(!r.ok){alert(await r.text());return;}
    let blob=await r.blob();let url=URL.createObjectURL(blob);
    let a=document.createElement('a');a.href=url;a.download="shifts.ics";a.click();}
    </script></body></html>
    """)
