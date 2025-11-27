from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
from datetime import datetime, timedelta
import io
import uuid

app = FastAPI()

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def create_ics(events):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Shift Worker Calendar//EN"]
    for ev in events:
        uid = str(uuid.uuid4())
        dtstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        lines += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{dtstamp}",
                  f"DTSTART:{ev['dtstart'].strftime('%Y%m%dT%H%M%S')}",
                  f"DTEND:{ev['dtend'].strftime('%Y%m%dT%H%M%S')}",
                  f"SUMMARY:{ev.get('summary','Shift')}",
                  f"DESCRIPTION:{ev.get('description','')}".replace('\n','\\n'),
                  f"LOCATION:{ev.get('location','')}", "END:VEVENT"]
    lines += ["END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n"

@app.post("/upload-and-convert")
async def upload(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(('.csv','.xlsx','.xls')):
        raise HTTPException(400, "Only CSV/Excel files")
    content = await file.read()
    df = pd.read_csv(io.BytesIO(content)) if file.filename.endswith('.csv') else pd.read_excel(io.BytesIO(content))
    events = []
    cols = {c.lower():c for c in df.columns}
    title = next((cols[k] for k in cols if any(x in k for x in ['title','subject','event','name','summary'])), None)
    start = next((cols[k] for k in cols if any(x in k for x in ['start','date','startdate','start date'])), None)
    for _, row in df.iterrows():
        try:
            dtstart = pd.to_datetime(row[start]).replace(second=0, microsecond=0)
            dtend = dtstart + timedelta(hours=8)
            events.append({"summary": str(row[title]) if title else "Shift",
                           "dtstart": dtstart, "dtend": dtend,
                           "description": "", "location": ""})
        except:
            continue
    if not events:
        raise HTTPException(400, "No shifts found")
    return StreamingResponse(io.BytesIO(create_ics(events).encode()),
                             media_type="text/calendar",
                             headers={"Content-Disposition": 'attachment; filename="shifts.ics"'})

@app.get("/")
async def home():
    return HTMLResponse("""
    <html><head><title>Shift Worker Calendar</title>
    <style>body{font-family:Arial;background:#355E3B;color:white;text-align:center;padding:50px}
    button{padding:15px 30px;font-size:18px;background:#fff;color:#355E3B;border:none;border-radius:8px}</style></head>
    <body><h1>Shift Worker Calendar</h1><p>Upload roster → get .ics file</p>
    <input type="file" id="f" accept=".csv,.xlsx"><br><br>
    <button onclick="upload()">Convert & Download</button>
    <script>
    async function upload(){
      const file = document.getElementById('f').files[0];
      if (!file) return alert('Choose a file');
      const fd = new FormData(); fd.append('file', file);
      const r = await fetch('/upload-and-convert', {method:'POST', body:fd});
      if (!r.ok) { alert(await r.text()); return; }
      const blob = await r.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'shifts.ics';
      a.click();
    }
    </script></body></html>
    """)
