import urllib.request
import re
import json
import io
import zipfile
import os

class RemoteFile:
    def __init__(self, url):
        self.url = url
        self.position = 0
        
        # Get content-length and follow redirect
        req = urllib.request.Request(self.url, method='HEAD')
        req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
        try:
            with urllib.request.urlopen(req) as resp:
                self.url = resp.geturl()  # Follow redirects
                self.length = int(resp.headers.get('Content-Length', 0))
        except Exception as e:
            # Fallback to GET if HEAD method is not allowed by CDN
            req_get = urllib.request.Request(self.url)
            req_get.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
            req_get.add_header('Range', 'bytes=0-0')
            with urllib.request.urlopen(req_get) as resp:
                self.url = resp.geturl()
                content_range = resp.headers.get('Content-Range', '')
                if content_range:
                    # Content-Range: bytes 0-0/1234567
                    self.length = int(content_range.split('/')[-1])
                else:
                    self.length = int(resp.headers.get('Content-Length', 0))

    def seek(self, offset, whence=io.SEEK_SET):
        if whence == io.SEEK_SET:
            self.position = offset
        elif whence == io.SEEK_CUR:
            self.position += offset
        elif whence == io.SEEK_END:
            self.position = self.length + offset
        else:
            raise ValueError("Invalid whence")
        return self.position
        
    def tell(self):
        return self.position
        
    def read(self, size=-1):
        if size == -1 or self.position + size > self.length:
            size = self.length - self.position
        if size <= 0:
            return b""
            
        req = urllib.request.Request(self.url)
        req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
        req.add_header('Range', f'bytes={self.position}-{self.position + size - 1}')
        try:
            with urllib.request.urlopen(req) as resp:
                data = resp.read()
        except Exception as e:
            # Retry once
            with urllib.request.urlopen(req) as resp:
                data = resp.read()
                
        self.position += len(data)
        return data

def resolve_mailru_link(public_url):
    """cloud.mail.ru/public/... havolasidan token va direct download link oladi."""
    if "cloclo" in public_url and "key=" in public_url:
        return public_url

    if "cloud.mail.ru/public/" not in public_url:
        return public_url

    print("Mail.ru ommaviy havolasi aniqlandi. Direct download link olinmoqda...")
    key = public_url.split("/public/")[-1].strip("/")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

    base_cdn = None
    token = None

    # 1-QADAM: Page HTML dan CDN server va Download Token olish
    try:
        req = urllib.request.Request(public_url, headers=headers)
        with urllib.request.urlopen(req) as response:
            html = response.read().decode('utf-8', errors='ignore')

        # CDN Server topish (masalan: https://cloclo53.cloud.mail.ru)
        server_match = re.search(r'https://cloclo\d+\.(?:cloud\.mail|mail)\.ru', html)
        if server_match:
            base_cdn = server_match.group(0)

        # Download Token topish (masalan: "download":"abc123token")
        token_match = re.search(r'"download"\s*:\s*"([a-zA-Z0-9_-]+)"', html)
        if token_match:
            token = token_match.group(1)
    except Exception as e:
        print(f"HTML parse error: {e}")

    # 2-QADAM: Agar token API orqali olinsa
    if not token or not base_cdn:
        try:
            api_url = "https://cloud.mail.ru/api/v2/tokens/download"
            req_api = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(req_api) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                token = data.get('body', {}).get('token')
                url_server = data.get('body', {}).get('url')
                if url_server and not base_cdn:
                    base_cdn = url_server.split('/weblink')[0].rstrip('/')
        except Exception as e:
            print(f"API token error: {e}")

    if not base_cdn:
        base_cdn = "https://cloclo1.cloud.mail.ru"

    # URL larni shakllantirish (key token bilan)
    token_param = f"?key={token}" if token else ""
    folder_zip_url = f"{base_cdn}/zip/v1/public/{key}{token_param}"
    file_url = f"{base_cdn}/weblink/get/{key}{token_param}"

    # Qaysi bir yangilanish javob berishini tekshiramiz (Folder ZIP birinchi)
    for test_url in [folder_zip_url, file_url]:
        try:
            test_req = urllib.request.Request(test_url, method='HEAD', headers=headers)
            with urllib.request.urlopen(test_req, timeout=5) as resp:
                if resp.status in (200, 302):
                    print(f"✅ Mail.ru link tayyor ({resp.status}): {test_url[:70]}...")
                    return test_url
        except Exception:
            pass

    print(f"⚠️ Direct link (default folder): {folder_zip_url[:70]}...")
    return folder_zip_url

def resolve_cloud_url(public_url):
    """Bulutli havolalarni (Mail.ru, Pixeldrain, Google Drive, va boshqalar) to'g'ridan-to'g'ri yuklash havolasiga o'giradi."""
    url = public_url.strip()

    # Pixeldrain: https://pixeldrain.com/u/ID -> https://pixeldrain.com/api/file/ID
    if "pixeldrain.com/u/" in url:
        file_id = url.split("/u/")[-1].split("?")[0].split("#")[0]
        return f"https://pixeldrain.com/api/file/{file_id}"

    # Google Drive: https://drive.google.com/file/d/ID/view -> direct download
    if "drive.google.com" in url:
        match = re.search(r'/d/([a-zA-Z0-9_-]+)', url)
        if match:
            file_id = match.group(1)
            return f"https://drive.google.com/uc?export=download&id={file_id}"

    # Mail.ru
    if "cloud.mail.ru/public/" in url:
        return resolve_mailru_link(url)

    return url

def open_zip(zip_path, password=None):
    if zip_path.startswith("http://") or zip_path.startswith("https://"):
        resolved_url = resolve_mailru_link(zip_path)
        print("Tarmoq orqali ZIP fayl oqimi yuklanmoqda...")
        file_obj = RemoteFile(resolved_url)
        z = zipfile.ZipFile(file_obj, 'r')
    else:
        if not os.path.exists(zip_path):
            raise FileNotFoundError(f"ZIP fayl topilmadi: {zip_path}")
        print(f"Mahalliy ZIP fayl ochilmoqda: {zip_path}")
        z = zipfile.ZipFile(zip_path, 'r')
        
    if password:
        z.setpassword(bytes(password, 'utf-8'))
    return z
