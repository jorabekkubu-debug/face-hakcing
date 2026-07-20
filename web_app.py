import os
import tempfile
import shutil
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import task_db

app = FastAPI(title="Video Face Analytics Web Portal")

os.makedirs("web_uploads", exist_ok=True)

HTML_CONTENT = """<!DOCTYPE html>
<html lang="uz">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Video Yuz Tahlil Portali</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0f172a;
            --card-bg: rgba(30, 41, 59, 0.7);
            --accent-color: #6366f1;
            --accent-hover: #4f46e5;
            --text-color: #f8fafc;
            --text-muted: #94a3b8;
        }

        body {
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            min-height: 100vh;
            margin: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            background-image: radial-gradient(circle at 50% -20%, #312e81, transparent);
        }

        .container {
            width: 100%;
            max-width: 540px;
            background: var(--card-bg);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 24px;
            padding: 40px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
            box-sizing: border-box;
        }

        h1 {
            font-size: 28px;
            font-weight: 700;
            margin-bottom: 8px;
            text-align: center;
            background: linear-gradient(135deg, #a5b4fc, #6366f1);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        p.subtitle {
            text-align: center;
            color: var(--text-muted);
            font-size: 15px;
            margin-bottom: 32px;
        }

        .tab-buttons {
            display: flex;
            background: rgba(15, 23, 42, 0.6);
            border-radius: 12px;
            padding: 4px;
            margin-bottom: 24px;
        }

        .tab-btn {
            flex: 1;
            padding: 12px;
            border: none;
            background: transparent;
            color: var(--text-muted);
            font-size: 14px;
            font-weight: 600;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s;
        }

        .tab-btn.active {
            background: var(--accent-color);
            color: white;
        }

        .form-group {
            margin-bottom: 20px;
        }

        label {
            display: block;
            font-size: 14px;
            font-weight: 600;
            margin-bottom: 8px;
            color: var(--text-muted);
        }

        input[type="text"], input[type="file"] {
            width: 100%;
            padding: 14px;
            background: rgba(15, 23, 42, 0.8);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            color: white;
            font-size: 15px;
            box-sizing: border-box;
            outline: none;
            transition: border-color 0.3s;
        }

        input[type="text"]:focus {
            border-color: var(--accent-color);
        }

        .submit-btn {
            width: 100%;
            padding: 16px;
            background: linear-gradient(135deg, #6366f1, #4f46e5);
            border: none;
            border-radius: 12px;
            color: white;
            font-size: 16px;
            font-weight: 700;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
            box-shadow: 0 10px 20px -5px rgba(99, 102, 241, 0.4);
        }

        .submit-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 15px 25px -5px rgba(99, 102, 241, 0.6);
        }

        #resultBox {
            display: none;
            margin-top: 28px;
            padding: 20px;
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.3);
            border-radius: 16px;
            text-align: center;
        }

        .code-display {
            font-size: 32px;
            font-weight: 800;
            letter-spacing: 2px;
            color: #34d399;
            margin: 12px 0;
            user-select: all;
        }

        .instructions {
            font-size: 13px;
            color: var(--text-muted);
            line-height: 1.5;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>AI Video Analytics</h1>
        <p class="subtitle">Videolarni yuklang va Telegram Bot uchun kod oling</p>

        <div class="tab-buttons">
            <button class="tab-btn active" onclick="switchTab(this, 'urlTab')">🌐 Bulutli Havola</button>
            <button class="tab-btn" onclick="switchTab(this, 'fileTab')">📁 ZIP Fayl Yuklash</button>
        </div>

        <form id="urlForm" onsubmit="submitUrl(event)">
            <div class="form-group">
                <label>Cloud.Mail.ru yoki To'g'ridan-to'g'ri Havola</label>
                <input type="text" id="cloudUrl" placeholder="https://cloud.mail.ru/public/..." required>
            </div>
            <button type="submit" class="submit-btn">Vazifa Kodini Olish 🚀</button>
        </form>

        <form id="fileForm" style="display: none;" onsubmit="submitFile(event)">
            <div class="form-group">
                <label>ZIP Arxivini Tanlang (Har qanday hajmda)</label>
                <input type="file" id="zipFileInput" accept=".zip" required>
            </div>
            <button type="submit" class="submit-btn">Faylni Yuklash va Kod Olish 📤</button>
        </form>

        <div id="resultBox">
            <div style="font-size: 14px; color: #a7f3d0; font-weight: 600;">✅ VAZIFA KODI YARATILDI:</div>
            <div class="code-display" id="generatedCode">RUN-0000</div>
            <div class="instructions">
                Ushbu kodni nusxalab oling va <b>Telegram Botga</b> yuboring!<br>
                Bot darhol ushbu vazifani tahlil qilishni boshlaydi.
            </div>
        </div>
    </div>

    <script>
        function switchTab(element, tabId) {
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            element.classList.add('active');
            if (tabId === 'urlTab') {
                document.getElementById('urlForm').style.display = 'block';
                document.getElementById('fileForm').style.display = 'none';
            } else {
                document.getElementById('urlForm').style.display = 'none';
                document.getElementById('fileForm').style.display = 'block';
            }
            document.getElementById('resultBox').style.display = 'none';
        }

        async function submitUrl(e) {
            e.preventDefault();
            const url = document.getElementById('cloudUrl').value;
            const res = await fetch('/api/create-url-task', {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: new URLSearchParams({'url': url})
            });
            const data = await res.json();
            showResult(data.task_code);
        }

        function submitFile(e) {
            e.preventDefault();
            const fileInput = document.getElementById('zipFileInput');
            if (!fileInput.files[0]) return;
            const file = fileInput.files[0];
            const formData = new FormData();
            formData.append('file', file);

            const btn = document.querySelector('#fileForm button');
            btn.disabled = true;

            const xhr = new XMLHttpRequest();
            xhr.open('POST', '/api/upload-zip-task', true);

            xhr.upload.onprogress = function(event) {
                if (event.lengthComputable) {
                    const percent = Math.round((event.loaded / event.total) * 100);
                    const loadedMB = (event.loaded / (1024 * 1024)).toFixed(1);
                    const totalMB = (event.total / (1024 * 1024)).toFixed(1);
                    btn.innerText = `Yuklanmoqda: ${percent}% (${loadedMB} MB / ${totalMB} MB) ⏳`;
                }
            };

            xhr.onload = function() {
                btn.disabled = false;
                btn.innerText = 'Faylni Yuklash va Kod Olish 📤';
                if (xhr.status === 200) {
                    const data = JSON.parse(xhr.responseText);
                    showResult(data.task_code);
                } else {
                    alert('Fayl yuklashda xatolik bo\'ldi');
                }
            };

            xhr.onerror = function() {
                btn.disabled = false;
                btn.innerText = 'Faylni Yuklash va Kod Olish 📤';
                alert('Tarmoq xatoligi yuz berdi');
            };

            xhr.send(formData);
        }

        function showResult(code) {
            document.getElementById('generatedCode').innerText = code;
            document.getElementById('resultBox').style.display = 'block';
        }
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def serve_home():
    return HTML_CONTENT

@app.post("/api/create-url-task")
async def create_url_task(url: str = Form(...)):
    task_code = task_db.create_task(source_type="URL", source_path_or_url=url.strip())
    return {"task_code": task_code}

@app.post("/api/upload-zip-task")
async def upload_zip_task(file: UploadFile = File(...)):
    filename = f"{file.filename}"
    save_path = os.path.join("web_uploads", filename)
    CHUNK_SIZE = 1024 * 1024  # 1MB per chunk
    with open(save_path, "wb") as buffer:
        while chunk := await file.read(CHUNK_SIZE):
            buffer.write(chunk)
    
    task_code = task_db.create_task(source_type="FILE", source_path_or_url=os.path.abspath(save_path))
    return {"task_code": task_code}

if __name__ == "__main__":
    import uvicorn
    print("🌐 Web Portal kompyuterizda ishga tushmoqda: http://127.0.0.1:8000")
    uvicorn.run("web_app:app", host="127.0.0.1", port=8000, reload=True)
