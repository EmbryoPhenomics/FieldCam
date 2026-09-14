import time
import cv2 
from tqdm import tqdm
import picamera2
from picamera2.encoders import JpegEncoder
from ffmpegoutput import FfmpegOutput
import simplejpeg
import re
import csv
import glob
import os
import pandas as pd
import fcntl
import gc

import subprocess

from camera_benchmark import CaptureBenchmark

# ------------------------------------------------------------
def video_config(controls, sensor_mode):
    w,h = sensor_mode['size']

    # Correct display aspect ratio
    lores_w = 320
    lores_h = round((h/w) * lores_w)
    lores_size = (lores_w, lores_h)

    if 'ExposureTime' in controls.keys():
        controls['FrameDurationLimits'] = (controls['ExposureTime'], controls['ExposureTime'])
    
    return dict(    
        sensor={"output_size": sensor_mode['size'], "bit_depth": sensor_mode['bit_depth']},
        main={"size": sensor_mode['size'], "format": 'RGB888'},
        lores={"size": lores_size, "format": "YUV420"},
        controls=controls
    )    

awb_mode_mapping = {
        0: 'auto',
        2: 'tungsten',
        3: 'fluorescent',
        4: 'indoor',
        5: 'daylight',
        6: 'cloudy',
}

def non_block_read(output):
    fd = output.fileno()
    fl = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
    try:
        return output.read()
    except:
        return ""

class Camera:
    def __init__(self):
        self.camera = picamera2.Picamera2()
        self.sensor_mode = 0
            
    def get_sensor_modes(self):
        modes = self.camera.sensor_modes
        return modes

    def set_controls(self, controls):
        self.camera.set_controls(controls)

    def video_capture(self, path, duration, controls, sensor_mode=0):
        if not path.endswith('.mp4'):
            raise ValueError('MP4 file format only currently supported.')

        rpicam_path = path.replace('.mp4', '.h264')

        if not self.camera or not self.camera.is_open:
            self.camera = picamera2.Picamera2()

        mode = self.camera.sensor_modes[sensor_mode]
        width, height = mode['size']
        if sensor_mode > 0:
            width, height = (1920, 1080) # To overcome hardware limit of encoder

        # Close any open camera instance before launching rpicam-vid
        self.camera.close()

        # Build command
        cmd = [
            "rpicam-vid",
            "-o", rpicam_path,
            "--width", str(width),
            "--height", str(height),
            "--codec", "h264",
            "--level", "4.2",
            "--denoise", "cdn_off",
            "--nopreview",
            "--buffer-count", "12",
            "--timeout", str(duration * 1000), 
            "--save-pts", path.replace('.mp4', '_frame_times.txt'),
        ]

        for key, value in controls.items():
            if key == "AwbMode":
                cmd += ["--awb", str(awb_mode_mapping[value])]
            elif key == "ExposureTime":
                cmd += ["--shutter", str(int(value))]  # microseconds
            elif key == "LensPosition":
                cmd += ["--lens-position", str(value)]
            elif key == "FrameRate":
                cmd += ["--framerate", str(value)]

        print(" ".join(cmd))

        for attempt in range(3):
            print(f"Attempt {attempt+1}")

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                universal_newlines=True
            )

            # Check for stalled file and any errors
            start_time = time.time()
            capture_success = True 
            capture_complete = False
            old_size = 0
            while process.poll() is None:
                # Read ALL currently available lines
                while True:
                    line = non_block_read(process.stdout)

                    if line == '':
                        break

                    print(line)

                    if 'Halting: reached timeout' in line:
                        capture_complete = True
                        break

                    if 'ERROR' in line:
                        capture_success = False
                        break

                if not capture_success or capture_complete:
                    break

                time.sleep(0.01)

            if not capture_complete:
                process.kill()
                time.sleep(5)
                continue
            else:
                print('Video captured successfully...')
                break

        print('Converting to MP4...')
        subprocess.run(['ffmpeg', '-y', '-i', rpicam_path, '-c:v', 'copy', path])

        print('Removing H264 file...')
        os.remove(rpicam_path)

        return capture_success

    def close(self):
        self.camera.close()
        del self.camera
        gc.collect()
        self.camera = None
        
        
def frame_to_bytes(frame):
    ret, jpeg = cv2.imencode('.jpg', frame)
    return jpeg.tobytes() 

class VideoGenerator:
    def __init__(self, camera, controls, sensor_mode=0, record_flag=False, video_dir='/home/pi/imseq/live_video'):
        self.camera = camera
        self.record_flag = record_flag
        mode = self.camera.sensor_modes[sensor_mode]
        config = self.camera.create_video_configuration(**video_config(controls, mode))
        self.camera.configure(config)
        self.benchmark = CaptureBenchmark()

        if self.record_flag:
            self.mjpeg_encoder = JpegEncoder(q=80)
            self.mjpeg_encoder.size = config["main"]["size"]
            self.mjpeg_encoder.format = config["main"]["format"]

            if not os.path.exists(video_dir):
                os.mkdir(video_dir)

            num_files = len(glob.glob(f'{video_dir}/*.mkv'))
            self.mjpeg_encoder.output = FfmpegOutput(f'{video_dir}/{num_files+1}.mkv')

    def __enter__(self):
        self.benchmark.clear()

        if self.record_flag:
            self.mjpeg_encoder.start()        

        self.camera.start()
        self.benchmark.record_start()
        while True:
            request = self.camera.capture_request()      
            img = request.make_array("lores")
            img = cv2.cvtColor(img, cv2.COLOR_YUV420p2RGBA)

            if self.record_flag:
                self.mjpeg_encoder.encode("main", request)

            request.release()

            self.benchmark.record_frame_time()
            self.benchmark.record_complete()

            yield img

    def __exit__(self, exc_type, exc_value, exc_tb):
        self.benchmark.record_end()

        if self.record_flag:
            self.mjpeg_encoder.stop()

        self.camera.stop()
        self.benchmark.print_log()


# This is for the Dash App but is not required for using the above API
class CameraSettings:
    def __init__(self):
        self.settings = {}

    def get(self, name):
        value = self.settings[name]
        return value

    def set(self, name, value):
        self.settings[name] = value
        
        
if __name__ == '__main__':
    import multiprocessing as mp
    import os

    camera_controls = {
        "AeEnable": 1,
        "AwbMode": 0,
        "AfMode": 2,
        "FrameRate": 30
    }

    def capture(path):
        picam2 = Camera()
        picam2.video_capture(path, 5, camera_controls)
        picam2.close()

    for i in range(30):
        capture(f'/home/pi/test.mp4')

