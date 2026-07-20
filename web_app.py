import os
import uuid
import asyncio
from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import task_db

app = FastAPI(title="Video Face Analytics Web Portal")

# CORS — tunnel orqali ishlashi uchun
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Yuklash holati: upload_id -> {percent, done, task_code, error}
upload_status = {}

HTML_CONTENT = """<!DOCTYPE html>
<html lang="uz">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Video Yuz Tahlil Portali</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700;800&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }

        :root {
            --bg: #0a0f1e;
            --card: rgba(22, 30, 52, 0.85);
            --accent: #6366f1;
            --accent2: #8b5cf6;
            --green: #10b981;
            --red: #ef4444;
            --text: #f1f5f9;
            --muted: #94a3b8;
            --border: rgba(99,102,241,0.2);
        }

        body {
            font-family: 'Outfit', sans-serif;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            background-image:
                radial-gradient(ellipse at 20% 10%, rgba(99,102,241,0.15) 0%, transparent 50%),
                radial-gradient(ellipse at 80% 80%, rgba(139,92,246,0.12) 0%, transparent 50%);
        }

        .card {
            width: 100%;
            max-width: 520px;
            background: var(--card);
            backdrop-filter: blur(24px);
            border: 1px solid var(--border);
            border-radius: 28px;
            padding: 44px 40px;
            box-shadow: 0 32px 64px -12px rgba(0,0,0,0.6),
                        0 0 0 1px rgba(255,255,255,0.04) inset;
        }

        .logo {
            text-align: center;
            font-size: 48px;
            margin-bottom: 12px;
            filter: drop-shadow(0 0 20px rgba(99,102,241,0.5));
        }

        h1 {
            font-size: 26px;
            font-weight: 800;
            text-align: center;
            background: linear-gradient(135deg, #c4b5fd, #6366f1, #818cf8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 6px;
        }

        .subtitle {
            text-align: center;
            color: var(--muted);
            font-size: 14px;
            margin-bottom: 36px;
            line-height: 1.5;
        }

        /* Drop zone */
        .dropzone {
            border: 2px dashed rgba(99,102,241,0.4);
            border-radius: 18px;
            padding: 36px 20px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
            background: rgba(10,15,30,0.5);
            position: relative;
            margin-bottom: 20px;
        }
        .dropzone:hover, .dropzone.dragover {
            border-color: var(--accent);
            background: rgba(99,102,241,0.08);
            transform: scale(1.01);
        }
        .dropzone input[type="file"] {
            position: absolute;
            inset: 0;
            opacity: 0;
            cursor: pointer;
            width: 100%;
            height: 100%;
        }
        .dropzone-icon { font-size: 40px; margin-bottom: 10px; }
        .dropzone-text { font-size: 15px; font-weight: 600; color: var(--text); }
        .dropzone-hint { font-size: 13px; color: var(--muted); margin-top: 4px; }
        .file-info {
            display: none;
            margin-top: 10px;
            padding: 10px 14px;
            background: rgba(99,102,241,0.15);
            border-radius: 10px;
            font-size: 13px;
            color: #a5b4fc;
            font-weight: 600;
        }

        /* Status box */
        .status-box {
            display: none;
            margin-bottom: 20px;
            padding: 16px 18px;
            border-radius: 14px;
            background: rgba(99,102,241,0.1);
            border: 1px solid rgba(99,102,241,0.25);
        }
        .status-label {
            font-size: 13px;
            font-weight: 600;
            color: var(--muted);
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .spinner {
            width: 14px; height: 14px;
            border: 2px solid rgba(99,102,241,0.3);
            border-top-color: var(--accent);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            display: inline-block;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        /* Progress bar */
        .progress-wrap {
            background: rgba(255,255,255,0.07);
            border-radius: 100px;
            height: 8px;
            overflow: hidden;
            margin-bottom: 8px;
        }
        .progress-bar {
            height: 100%;
            background: linear-gradient(90deg, #6366f1, #8b5cf6);
            border-radius: 100px;
            transition: width 0.4s ease;
            width: 0%;
        }
        .progress-bar.indeterminate {
            width: 40% !important;
            animation: slide 1.4s ease-in-out infinite;
        }
        @keyframes slide {
            0%   { transform: translateX(-150%); }
            100% { transform: translateX(350%); }
        }
        .progress-text {
            font-size: 13px;
            color: var(--muted);
            text-align: right;
        }

        /* Button */
        .btn {
            width: 100%;
            padding: 17px;
            background: linear-gradient(135deg, #6366f1, #4f46e5);
            border: none;
            border-radius: 14px;
            color: white;
            font-size: 16px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.25s;
            box-shadow: 0 8px 24px -4px rgba(99,102,241,0.5);
            font-family: 'Outfit', sans-serif;
        }
        .btn:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 14px 32px -4px rgba(99,102,241,0.65);
        }
        .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }

        /* Error box */
        .error-box {
            display: none;
            margin-top: 16px;
            padding: 14px 16px;
            background: rgba(239,68,68,0.1);
            border: 1px solid rgba(239,68,68,0.3);
            border-radius: 12px;
            color: #fca5a5;
            font-size: 14px;
        }

        /* Result box */
        .result-box {
            display: none;
            margin-top: 24px;
            padding: 28px 24px;
            background: rgba(16,185,129,0.08);
            border: 1px solid rgba(16,185,129,0.25);
            border-radius: 20px;
            text-align: center;
        }
        .result-label {
            font-size: 13px;
            font-weight: 600;
            color: #6ee7b7;
            letter-spacing: 1px;
            text-transform: uppercase;
            margin-bottom: 10px;
        }
        .code-display {
            font-size: 42px;
            font-weight: 800;
            letter-spacing: 4px;
            color: #34d399;
            margin: 8px 0 14px;
            cursor: pointer;
            transition: opacity 0.2s;
            text-shadow: 0 0 30px rgba(52,211,153,0.4);
        }
        .code-display:hover { opacity: 0.8; }
        .copy-hint {
            font-size: 12px;
            color: var(--muted);
            margin-bottom: 12px;
        }
        .result-desc {
            font-size: 14px;
            color: var(--muted);
            line-height: 1.6;
        }
        .result-desc b { color: #a5b4fc; }

        /* Copied toast */
        .toast {
            position: fixed;
            bottom: 30px;
            left: 50%;
            transform: translateX(-50%) translateY(20px);
            background: #10b981;
            color: white;
            padding: 10px 22px;
            border-radius: 100px;
            font-size: 14px;
            font-weight: 600;
            opacity: 0;
            transition: all 0.3s;
            pointer-events: none;
        }
        .toast.show {
            opacity: 1;
            transform: translateX(-50%) translateY(0);
        }
    </style>
</head>
<body>
<div class="card">
    <div class="logo">🎭</div>
    <h1>AI Yuz Tahlil Portali</h1>
    <p class="subtitle">ZIP arxivini yuklang → Telegram bot uchun vazifa kodi oling</p>

    <!-- Drop zone -->
    <div class="dropzone" id="dropzone">
        <input type="file" id="zipInput" accept=".zip">
        <div class="dropzone-icon">📁</div>
        <div class="dropzone-text">ZIP faylni tanlang yoki bu yerga tashlang</div>
        <div class="dropzone-hint">Faqat .zip formatdagi fayllar qabul qilinadi</div>
        <div class="file-info" id="fileInfo"></div>
    </div>

    <!-- Status -->
    <div class="status-box" id="statusBox">
        <div class="status-label">
            <span class="spinner" id="spinner"></span>
            <span id="statusText">Tayorlanmoqda...</span>
        </div>
        <div class="progress-wrap">
            <div class="progress-bar" id="progressBar"></div>
        </div>
        <div class="progress-text" id="progressText"></div>
    </div>

    <!-- Upload button -->
    <button class="btn" id="uploadBtn" onclick="startUpload()">
        📤 Yuklash va Kod Olish
    </button>

    <!-- Error -->
    <div class="error-box" id="errorBox"></div>

    <!-- Result -->
    <div class="result-box" id="resultBox">
        <div class="result-label">✅ Vazifa kodi yaratildi</div>
        <div class="code-display" id="codeDisplay" onclick="copyCode()">RUN-0000</div>
        <div class="copy-hint">👆 Kodni bosib nusxalang</div>
        <div class="result-desc">
            Bu kodni <b>Telegram botga</b> yuboring.<br>
            Bot darhol videolarni tahlil qilishni boshlaydi!
        </div>
    </div>
</div>

<div class="toast" id="toast">✅ Kod nusxalandi!</div>

<script>
    let selectedFile = null;
    let uploadId = null;
    let pollTimer = null;

    // Drop zone
    const dropzone = document.getElementById('dropzone');
    const zipInput = document.getElementById('zipInput');

    dropzone.addEventListener('dragover', e => { e.preventDefault(); dropzone.classList.add('dragover'); });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
    dropzone.addEventListener('drop', e => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        const f = e.dataTransfer.files[0];
        if (f && f.name.endsWith('.zip')) setFile(f);
        else showError("⚠️ Faqat .zip fayl qabul qilinadi!");
    });
    zipInput.addEventListener('change', () => {
        if (zipInput.files[0]) setFile(zipInput.files[0]);
    });

    function setFile(f) {
        selectedFile = f;
        const mb = (f.size / 1024 / 1024).toFixed(1);
        const info = document.getElementById('fileInfo');
        info.style.display = 'block';
        info.textContent = `📦 ${f.name}  —  ${mb} MB`;
        hideError();
        document.getElementById('resultBox').style.display = 'none';
    }

    function showError(msg) {
        const box = document.getElementById('errorBox');
        box.textContent = msg;
        box.style.display = 'block';
    }
    function hideError() {
        document.getElementById('errorBox').style.display = 'none';
    }

    function setStatus(text, percent, indeterminate) {
        document.getElementById('statusBox').style.display = 'block';
        document.getElementById('statusText').textContent = text;
        const bar = document.getElementById('progressBar');
        if (indeterminate) {
            bar.classList.add('indeterminate');
            document.getElementById('progressText').textContent = '';
        } else {
            bar.classList.remove('indeterminate');
            bar.style.width = percent + '%';
            document.getElementById('progressText').textContent = percent + '%';
        }
    }

    function hideStatus() {
        document.getElementById('statusBox').style.display = 'none';
    }

    async function startUpload() {
        if (!selectedFile) { showError("⚠️ Avval ZIP fayl tanlang!"); return; }
        hideError();

        const btn = document.getElementById('uploadBtn');
        btn.disabled = true;

        // Step 1: Upload ID olish
        setStatus("⚙️ Yuklash tayyorlanmoqda...", 0, true);

        let initResp;
        try {
            initResp = await fetch('/api/init-upload', { method: 'POST' });
            const initData = await initResp.json();
            uploadId = initData.upload_id;
        } catch(e) {
            showError("❌ Server bilan bog'lanib bo'lmadi: " + e.message);
            btn.disabled = false;
            hideStatus();
            return;
        }

        // Step 2: Chunked upload
        const CHUNK = 2 * 1024 * 1024; // 2MB
        const total = selectedFile.size;
        const totalChunks = Math.ceil(total / CHUNK);
        let uploaded = 0;

        setStatus("📤 Yuklanyapti...", 0, false);

        for (let i = 0; i < totalChunks; i++) {
            const start = i * CHUNK;
            const end = Math.min(start + CHUNK, total);
            const chunk = selectedFile.slice(start, end);

            const fd = new FormData();
            fd.append('chunk', chunk);
            fd.append('upload_id', uploadId);
            fd.append('chunk_index', i);
            fd.append('total_chunks', totalChunks);

            try {
                const resp = await fetch('/api/upload-chunk', { method: 'POST', body: fd });
                if (!resp.ok) {
                    const err = await resp.json();
                    throw new Error(err.detail || resp.statusText);
                }
            } catch(e) {
                showError("❌ Yuklashda xatolik (chunk " + (i+1) + "/" + totalChunks + "): " + e.message);
                btn.disabled = false;
                hideStatus();
                return;
            }

            uploaded = end;
            const pct = Math.round(uploaded / total * 100);
            const loadedMB = (uploaded / 1024 / 1024).toFixed(1);
            const totalMB = (total / 1024 / 1024).toFixed(1);
            setStatus(`📤 Yuklanyapti... ${loadedMB} MB / ${totalMB} MB`, pct, false);
        }

        // Step 3: Finalize
        setStatus("⏳ Server faylni qayta ishlayapti...", 100, false);

        try {
            const resp = await fetch('/api/finalize-upload', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ upload_id: uploadId })
            });
            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || resp.statusText);
            }
            const data = await resp.json();
            hideStatus();
            showResult(data.task_code);
        } catch(e) {
            showError("❌ Yakunlashda xatolik: " + e.message);
            hideStatus();
        }

        btn.disabled = false;
    }

    function showResult(code) {
        document.getElementById('codeDisplay').textContent = code;
        document.getElementById('resultBox').style.display = 'block';
        document.getElementById('resultBox').scrollIntoView({ behavior: 'smooth' });
    }

    function copyCode() {
        const code = document.getElementById('codeDisplay').textContent;
        navigator.clipboard.writeText(code).then(() => {
            const t = document.getElementById('toast');
            t.classList.add('show');
            setTimeout(() => t.classList.remove('show'), 2000);
        });
    }
</script>
</body>
</html>
"""

# ─── Chunked upload uchun vaqtinchalik saqlash ───────────────────────────────
# upload_id -> {"path": str, "chunks_received": set, "total_chunks": int}
pending_uploads: dict = {}


@app.get("/", response_class=HTMLResponse)
async def serve_home():
    resp = HTMLResponse(content=HTML_CONTENT)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


@app.post("/api/init-upload")
async def init_upload():
    """Yangi upload session boshlaydi, upload_id qaytaradi."""
    uid = uuid.uuid4().hex
    tmp_path = os.path.join(UPLOAD_DIR, f"tmp_{uid}.zip")
    pending_uploads[uid] = {
        "path": tmp_path,
        "chunks_received": set(),
        "total_chunks": None,
    }
    return {"upload_id": uid}


@app.post("/api/upload-chunk")
async def upload_chunk(
    chunk: UploadFile = File(...),
    upload_id: str = File(...),
    chunk_index: int = File(...),
    total_chunks: int = File(...),
):
    """Har bir chunk ni qabul qilib, vaqtinchalik faylga yozadi."""
    if upload_id not in pending_uploads:
        return JSONResponse({"detail": "Noto'g'ri upload_id"}, status_code=400)

    state = pending_uploads[upload_id]
    state["total_chunks"] = total_chunks

    data = await chunk.read()

    # Chunk ni to'g'ri joyga yozamiz (append mode bilan emas, offset bilan)
    chunk_path = os.path.join(UPLOAD_DIR, f"tmp_{upload_id}_chunk_{chunk_index:06d}")
    with open(chunk_path, "wb") as f:
        f.write(data)

    state["chunks_received"].add(chunk_index)
    return {"received": chunk_index, "total": total_chunks}


@app.post("/api/finalize-upload")
async def finalize_upload(request: Request):
    """Barcha chunklarni birlashtiradi va task yaratadi."""
    body = await request.json()
    upload_id = body.get("upload_id")

    if upload_id not in pending_uploads:
        return JSONResponse({"detail": "Noto'g'ri yoki muddati o'tgan upload_id"}, status_code=400)

    state = pending_uploads[upload_id]
    total = state["total_chunks"]
    received = state["chunks_received"]

    if total is None or len(received) < total:
        missing = set(range(total)) - received if total else set()
        return JSONResponse(
            {"detail": f"Chunklardan {len(received)}/{total} ta qabul qilindi. Yetishmaydi: {list(missing)[:5]}"},
            status_code=400
        )

    # Chunklarni tartib bilan birlashtirish
    final_name = f"{uuid.uuid4().hex}.zip"
    final_path = os.path.join(UPLOAD_DIR, final_name)

    with open(final_path, "wb") as out:
        for i in range(total):
            chunk_path = os.path.join(UPLOAD_DIR, f"tmp_{upload_id}_chunk_{i:06d}")
            with open(chunk_path, "rb") as ch:
                out.write(ch.read())
            os.remove(chunk_path)

    del pending_uploads[upload_id]

    task_code = task_db.create_task(
        source_type="FILE",
        source_path_or_url=os.path.abspath(final_path)
    )
    return {"task_code": task_code}


if __name__ == "__main__":
    import uvicorn
    print("🌐 Web Portal ishga tushmoqda: http://127.0.0.1:8000")
    uvicorn.run("web_app:app", host="0.0.0.0", port=8000, reload=False)
