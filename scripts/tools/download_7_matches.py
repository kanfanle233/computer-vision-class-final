import io
import os
import sys
import requests
import zipfile

# Set up module path to import RemoteFile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from download_remote_zip_rally import RemoteFile

def main():
    url = "https://nycu1-my.sharepoint.com/:u:/g/personal/tik_m365_nycu_edu_tw/EWisYhAiai9Ju7L-tQp0ykEBZJd9VQkKqsFrjcqqYIDP-g?download=1"
    
    # Destination directory
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    dest_dir = os.path.join(project_root, "inputs")
    os.makedirs(dest_dir, exist_ok=True)
    
    print("Initiating connection to remote OneDrive ZIP file...")
    rf = RemoteFile(url)
    
    # Selected 7 professional match videos to download (from professional dataset)
    # Using match17 and match19, which are high-quality broadcast professional matches
    targets = [
        ("TrackNetV2/Professional/match17/video/1_02_02.mp4", "TrackNetV2/Professional/match17/csv/1_02_02_ball.csv", "pro_match17_1_02_02"),
        ("TrackNetV2/Professional/match17/video/1_15_13.mp4", "TrackNetV2/Professional/match17/csv/1_15_13_ball.csv", "pro_match17_1_15_13"),
        ("TrackNetV2/Professional/match17/video/2_01_01.mp4", "TrackNetV2/Professional/match17/csv/2_01_01_ball.csv", "pro_match17_2_01_01"),
        ("TrackNetV2/Professional/match17/video/2_08_05.mp4", "TrackNetV2/Professional/match17/csv/2_08_05_ball.csv", "pro_match17_2_08_05"),
        ("TrackNetV2/Professional/match17/video/2_15_11.mp4", "TrackNetV2/Professional/match17/csv/2_15_11_ball.csv", "pro_match17_2_15_11"),
        ("TrackNetV2/Professional/match17/video/2_18_11.mp4", "TrackNetV2/Professional/match17/csv/2_18_11_ball.csv", "pro_match17_2_18_11"),
        ("TrackNetV2/Professional/match19/video/1_01_01.mp4", "TrackNetV2/Professional/match19/csv/1_01_01_ball.csv", "pro_match19_1_01_01")
    ]
    
    print("Opening remote zipfile for streaming extraction...")
    with zipfile.ZipFile(rf) as z:
        namelist = z.namelist()
        
        for video_path, csv_path, out_prefix in targets:
            print("\n-------------------------------------------")
            # 1. Download and save the MP4 video
            if video_path in namelist:
                out_video_name = f"{out_prefix}.mp4"
                out_video_path = os.path.join(dest_dir, out_video_name)
                print(f"[1/2] Extracting remote video: {video_path}...")
                print(f"      Size: {z.getinfo(video_path).file_size/1024/1024:.2f} MB")
                
                video_data = z.read(video_path)
                with open(out_video_path, "wb") as f:
                    f.write(video_data)
                print(f"      -> Saved to: inputs/{out_video_name}")
            else:
                print(f"[ERROR] Video {video_path} not found in zip file!")
                
            # 2. Download and save the CSV ball trajectory
            # Let's search if the CSV path exists directly or has a slightly different extension
            actual_csv_path = None
            for p in [csv_path, csv_path.replace("_ball.csv", ".csv")]:
                if p in namelist:
                    actual_csv_path = p
                    break
                    
            if actual_csv_path:
                out_csv_name = f"{out_prefix}_ball.csv"
                out_csv_path = os.path.join(dest_dir, out_csv_name)
                print(f"[2/2] Extracting remote CSV: {actual_csv_path}...")
                
                csv_data = z.read(actual_csv_path)
                with open(out_csv_path, "wb") as f:
                    f.write(csv_data)
                print(f"      -> Saved to: inputs/{out_csv_name}")
            else:
                print(f"[ERROR] CSV trajectory {csv_path} not found in zip file!")
                
    print("\n===========================================")
    print(f"SUCCESS: 7 Match videos and trajectories downloaded to: {dest_dir}")
    print("===========================================")

if __name__ == "__main__":
    main()
