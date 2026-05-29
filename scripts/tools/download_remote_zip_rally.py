import io
import os
import requests
import zipfile

class RemoteFile(io.RawIOBase):
    def __init__(self, url, cache_size=4*1024*1024, meta_size=16*1024*1024):
        self.url = url
        self.pos = 0
        res = requests.head(url, allow_redirects=True)
        self.size = int(res.headers.get("Content-Length", 0))
        self.cache_size = cache_size
        self.meta_size = min(meta_size, self.size)
        self.cache_start = -1
        self.cache_data = b""
        
        # Pre-cache the metadata block at the end of the file!
        print(f"Remote file size: {self.size} bytes ({self.size/1024/1024:.2f} MB)")
        print(f"Pre-caching the last {self.meta_size/1024/1024:.2f} MB of the ZIP file (EOCD + Central Directory)...")
        self.meta_start = self.size - self.meta_size
        headers = {"Range": f"bytes={self.meta_start}-{self.size-1}"}
        res = requests.get(self.url, headers=headers)
        self.meta_data = res.content
        print(f"Pre-caching complete. Received {len(self.meta_data)} bytes.")

    def readable(self):
        return True

    def seekable(self):
        return True

    def seek(self, offset, whence=io.SEEK_SET):
        if whence == io.SEEK_SET:
            self.pos = offset
        elif whence == io.SEEK_CUR:
            self.pos += offset
        elif whence == io.SEEK_END:
            self.pos = self.size + offset
        return self.pos

    def tell(self):
        return self.pos

    def readinto(self, b):
        if self.pos >= self.size:
            return 0
        length = len(b)
        
        # Check if requested range is in the pre-cached metadata block
        if self.meta_start <= self.pos < self.size and self.pos + length <= self.size:
            offset = self.pos - self.meta_start
            data = self.meta_data[offset:offset+length]
            b[:len(data)] = data
            self.pos += len(data)
            return len(data)
            
        # Check if requested range is in the standard forward cache
        if self.cache_start <= self.pos < self.cache_start + len(self.cache_data) and self.pos + length <= self.cache_start + len(self.cache_data):
            offset = self.pos - self.cache_start
            data = self.cache_data[offset:offset+length]
            b[:len(data)] = data
            self.pos += len(data)
            return len(data)
        
        # Cache miss for forward read. Pull a new block
        pull_size = max(length, self.cache_size)
        end = min(self.pos + pull_size - 1, self.size - 1)
        headers = {"Range": f"bytes={self.pos}-{end}"}
        res = requests.get(self.url, headers=headers)
        self.cache_start = self.pos
        self.cache_data = res.content
        
        data = self.cache_data[:length]
        b[:len(data)] = data
        self.pos += len(data)
        return len(data)

def main():
    url = "https://nycu1-my.sharepoint.com/:u:/g/personal/tik_m365_nycu_edu_tw/EWisYhAiai9Ju7L-tQp0ykEBZJd9VQkKqsFrjcqqYIDP-g?download=1"
    rf = RemoteFile(url)
    
    print("Opening remote zipfile...")
    with zipfile.ZipFile(rf) as z:
        nl = z.namelist()
        print(f"Total files in ZIP: {len(nl)}")
        
        # Look for amateur dataset rally videos
        mp4_files = sorted([x for x in nl if x.endswith(".mp4")])
        print(f"Found {len(mp4_files)} mp4 files.")
        
        # Let's pick a specific amateur match rally: match1, rally 1_00_01
        target_video = None
        target_csv = None
        
        for name in nl:
            if "amateur_dataset" in name and "match1" in name:
                if name.endswith("1_00_01.mp4"):
                    target_video = name
                elif name.endswith("1_00_01_ball.csv"):
                    target_csv = name
                    
        # Fallback if names are slightly different (e.g. capitalized)
        if not target_video:
            for name in nl:
                if name.endswith(".mp4") and "1_00_01" in name:
                    target_video = name
                if name.endswith(".csv") and "1_00_01" in name:
                    target_csv = name

        # Print matches
        print(f"Target video found: {target_video} ({z.getinfo(target_video).file_size if target_video else 'Not found'} bytes)")
        print(f"Target CSV found: {target_csv} ({z.getinfo(target_csv).file_size if target_csv else 'Not found'} bytes)")
        
        if target_video:
            print(f"Extracting {target_video} to workspace...")
            video_data = z.read(target_video)
            out_video_path = os.path.basename(target_video)
            with open(out_video_path, "wb") as f:
                f.write(video_data)
            print(f"Saved extracted video to: {out_video_path}")
            
        if target_csv:
            print(f"Extracting {target_csv} to workspace...")
            csv_data = z.read(target_csv)
            out_csv_path = os.path.basename(target_csv)
            with open(out_csv_path, "wb") as f:
                f.write(csv_data)
            print(f"Saved extracted CSV to: {out_csv_path}")

if __name__ == "__main__":
    main()
