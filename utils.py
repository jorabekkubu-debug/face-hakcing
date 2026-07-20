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
    if "cloclo" in public_url:
        return public_url
    
    # Check if it's a cloud.mail.ru public link
    if "cloud.mail.ru/public/" in public_url:
        print("Mail.ru ommaviy havolasi aniqlandi. To'g'ridan-to'g'ri yuklash havolasi olinmoqda...")
        req = urllib.request.Request(
            public_url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        try:
            with urllib.request.urlopen(req) as response:
                html = response.read().decode('utf-8')
        except Exception as e:
            print(f"Ogohlantirish: Ommaviy sahifani ochib bo'lmadi ({e}). Havolani o'zi ishlatiladi.")
            return public_url
            
        # Search for window.cloudSettings or weblink_get
        match_url = re.search(r'"weblink_get"\s*:\s*\[\s*\{\s*"url"\s*:\s*"(https://[^"]+)"', html)
        if not match_url:
            match_settings = re.search(r'window\.cloudSettings\s*=\s*(\{.*?\});', html)
            if match_settings:
                try:
                    settings = json.loads(match_settings.group(1))
                    if 'weblink_get' in settings and len(settings['weblink_get']) > 0:
                        base_url = settings['weblink_get'][0]['url']
                        suffix = public_url.split('/public/')[-1]
                        direct = f"{base_url.rstrip('/')}/{suffix}"
                        print(f"To'g'ridan-to'g'ri havola olindi: {direct}")
                        return direct
                except Exception:
                    pass
            print("Ogohlantirish: Sahifadan yuklash manzili topilmadi. Havolaning o'zi ishlatiladi.")
            return public_url
            
        base_url = match_url.group(1)
        suffix = public_url.split('/public/')[-1]
        direct = f"{base_url.rstrip('/')}/{suffix}"
        print(f"To'g'ridan-to'g'ri havola olindi: {direct}")
        return direct
        
    return public_url

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
