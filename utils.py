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
    """cloud.mail.ru/public/... havolasidan to'g'ridan-to'g'ri yuklab olish manzilini oladi."""
    if "cloclo" in public_url:
        return public_url

    if "cloud.mail.ru/public/" not in public_url:
        return public_url

    print("Mail.ru ommaviy havolasi aniqlandi. Direct download link olinmoqda...")
    try:
        # Mail.ru public path (masalan: key1/key2 yoki key1/key2/filename.zip)
        key = public_url.split("/public/")[-1].strip("/")

        # 1-USUL: Mail.ru API v2 orqali yuklash havolasini olish
        api_url = f"https://cloud.mail.ru/api/v2/tokens/download"
        req = urllib.request.Request(
            api_url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req) as resp:
            res_data = json.loads(resp.read().decode('utf-8'))
            download_token = res_data.get('body', {}).get('token')
            url_server = res_data.get('body', {}).get('url')

        if url_server and download_token:
            direct_url = f"{url_server.rstrip('/')}/{key}?key={download_token}"
            print(f"Direct link olindi (API): {direct_url[:60]}...")
            return direct_url
    except Exception as e:
        print(f"Mail.ru API orqali olishda ogohlantirish: {e}")

    # 2-USUL: Sahifa HTML parser fallback
    try:
        req = urllib.request.Request(
            public_url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req) as response:
            html = response.read().decode('utf-8')

        match_url = re.search(r'"weblink_get"\s*:\s*\[\s*\{\s*"url"\s*:\s*"(https://[^"]+)"', html)
        if match_url:
            base_url = match_url.group(1)
            suffix = public_url.split('/public/')[-1]
            direct = f"{base_url.rstrip('/')}/{suffix}"
            print(f"Direct link olindi (HTML): {direct[:60]}...")
            return direct

        match_settings = re.search(r'window\.cloudSettings\s*=\s*(\{.*?\});', html)
        if match_settings:
            settings = json.loads(match_settings.group(1))
            if 'weblink_get' in settings and len(settings['weblink_get']) > 0:
                base_url = settings['weblink_get'][0]['url']
                suffix = public_url.split('/public/')[-1]
                direct = f"{base_url.rstrip('/')}/{suffix}"
                print(f"Direct link olindi (Settings): {direct[:60]}...")
                return direct
    except Exception as e:
        print(f"HTML parsing ogohlantirish: {e}")

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
