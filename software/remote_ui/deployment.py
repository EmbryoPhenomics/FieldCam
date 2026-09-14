import json
import os
import cv2
import time
import RPi.GPIO as GPIO
import csv
import glob
import multiprocessing
import datetime

import camera
from app import app, rpi2c, picam2, led

# GPIO pins
LED_ON = 22
MODE_SWITCH = 26

class Deployment:
    def __init__(self, acq_path='/home/pi/imseq', led_pin=22):
        '''
        Deployment class for capturing video from JHam-Cam units

        Parameters
        ----------
        acq_path : str
            Folder path to save video.
        led_pin : int
            LED GPIO pin.

        '''

        if not os.path.exists(acq_path):
            os.mkdir(acq_path)

        # Set up mode switch
        GPIO.setup(MODE_SWITCH, GPIO.IN)

        # Read mode switch and launch app if necessary (2 seconds monitoring at startup)
        streaming_mode = False
        for i in range(5):
            if GPIO.input(MODE_SWITCH):
                streaming_mode = True
            time.sleep(0.4)
                
        if streaming_mode:
            print('Launching webserver...')
            app.run_server(host='0.0.0.0', debug=False)

        picam2.close()

        self.acq_path = acq_path
        
        config_files = glob.glob(f'{acq_path}/acquisition_config*') # Grab latest config file
        self.config_file = f'{acq_path}/acquisition_config_{len(config_files)}.json'
        with open(self.config_file, 'r') as conf:
            self.acq_conf = json.load(conf)
            self.current = self.acq_conf['current']
            self.frequency = self.acq_conf['frequency']
            self.duration = self.acq_conf['duration'] * 60 # convert to seconds
            self.interval = self.acq_conf['interval']
            self.continuous = self.acq_conf['continuous']
            self.camera_controls = self.acq_conf['camera_controls']
            self.led_on = self.acq_conf['led_on']
            self.led_brightness = self.acq_conf['led_brightness']
            self.led_on_time = self.acq_conf['led_on_time']
            self.led_off_time = self.acq_conf['led_off_time']
            self.camera_mode = self.acq_conf['camera_mode']

        if self.current >= self.frequency:
            self.shutdown()          

        rpi2c.set_watch_dog(0) # Disable watchdog

        os.system('sudo ifconfig wlan0 down') #  Turn wifi off to reduce power consumption

        self.camera_log = f'{acq_path}/camera_capture_log.csv'
        self.power_log = f'{acq_path}/system_log.csv'

        if not os.path.exists(self.camera_log):
            self.log2txt(self.camera_log, 'datetime, status')

        if not os.path.exists(self.power_log):
            self.log2txt(self.power_log, 'datetime, batt1_volts, batt2_volts, rpi_volts, rpi_amps, rpi_watts, uc_volts, uc_amps, uc_watts, water_temp, light_lux')

    def log2txt(self, path, line):
        with open(path, 'a+') as log:
            log.write(f'{line}\n')

    def get_datetime(self):
        rtc_now = f'{rpi2c.ts_2_dt(rpi2c.read_rtc())}'
        return rtc_now

    def _acquire_step(self):
        dt = datetime.datetime.fromtimestamp(rpi2c.read_rtc())

        if ((dt.hour >= 12) and (dt.hour >= self.led_on_time)) or ((dt.hour <= 12) and (dt.hour <= self.led_off_time)):
            if self.led_on:
                led.on()
                rpi2c.set_led_brightness(self.led_brightness)
                time.sleep(1)
        else:
            rpi2c.set_led_brightness(0)
            led.off()

        uc_datetime = self.get_datetime()
        video_path = f'{self.acq_path}/{uc_datetime}.mp4'

        wtemp, wlight = rpi2c.read_env_sensors()
        batt1, batt2 = rpi2c.read_battery()
        rpi_voltage, rpi_current, rpi_power, uc_voltage, uc_current, uc_power = rpi2c.read_power()
        self.log2txt(self.power_log,
                     f'{uc_datetime}, {batt1}, {batt2}, {rpi_voltage}, {rpi_current}, {rpi_power}, '
                     f'{uc_voltage}, {uc_current}, {uc_power}, {wtemp}, {wlight}')

        success = picam2.video_capture(video_path, self.duration, self.camera_controls, self.camera_mode)

        if not success:
            print("[WARN] All capture retries failed. Rebooting system.")
            self.log2txt(self.camera_log, f'{video_path}, FAILED')
            os.system('sudo reboot')
            time.sleep(5)
            return

        self.log2txt(self.camera_log, f'{video_path}, SUCCESS')

        if not self.continuous:
            rpi2c.set_led_brightness(0)
            led.off()

        self.current += 1
        with open(self.config_file, 'w') as conf:
            self.acq_conf['current'] = self.current
            json.dump(self.acq_conf, conf, indent=4)

    def acquire(self):
        if self.continuous:
            for i in range(self.frequency):
                self._acquire_step()
                time.sleep(self.interval * 60)
        else:
            self._acquire_step()

            timestamp = rpi2c.read_rtc()
            rpi2c.set_watch_dog(timestamp + round(self.interval * 60))
            
        self.shutdown()

    def shutdown(self):
        # Shut down the RPi
        rpi2c.set_power_off(20)
        time.sleep(1)
        os.system('sudo halt')
        time.sleep(5)

if __name__ == '__main__':
    deployment = Deployment()
    deployment.acquire()


