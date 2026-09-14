#!/usr/bin/python3
import dash
from dash import Dash, html, dcc, Input, Output, State, clientside_callback, callback
import os
import pwd
from datetime import datetime, date
from tqdm import tqdm
import dash_bootstrap_components as dbc
import re
import json
import glob

from flask import Flask, Response
import cv2
import numpy as np
import time
import csv
import types

import camera as picam2_backend
from camera import Camera
from libcamera import controls
from layout import layout
from rpi2c import RPi2C, LED

from dash.long_callback import DiskcacheLongCallbackManager

## Diskcache
import diskcache
import shutil

if os.path.exists('./cache'):
    shutil.rmtree('./cache')

cache = diskcache.Cache('./cache')
long_callback_manager = DiskcacheLongCallbackManager(cache)

rpi2c = RPi2C()

# Set datetime for RPi
ts = rpi2c.read_rtc()
datetime_sys = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
os.system(f"sudo date -s '{datetime_sys}'")

led = LED(led_pin=22)

# Initialise app
server = Flask(__name__)
app = dash.Dash(__name__, server=server, long_callback_manager=long_callback_manager, external_stylesheets=['./static/bootstrap.min.css', './static/fontawesome-free-6.3.0-web/css/all.css'])
trigger = ['']
app.layout = layout

# Callbacks --------------------------------------------------
clientside_callback(
    """
    (switchOn) => {
       document.documentElement.setAttribute('data-bs-theme', switchOn ? 'light' : 'dark');
       return window.dash_clientside.no_update
    }
    """,
    Output("switch", "id"),
    Input("switch", "value"),
)

# Camera control ---------------------------------------------
# Camera state for remote-view
class CameraState:
    def __init__(self):
        self.trigger = False
        self.record_flag = False

    def on_off(self):
        if self.trigger:
            self.trigger = False
        else:
            self.trigger = True

# Source: https://gist.github.com/IdeaKing/11cf5e146d23c5bb219ba3508cca89ec
def resize_with_pad(image, new_shape, padding_color=(0,0,0)):
    """Maintains aspect ratio and resizes with padding.
    Params:
        image: Image to be resized.
        new_shape: Expected (width, height) of new image.
        padding_color: Tuple in BGR of padding color
    Returns:
        image: Resized image with padding
    """
    original_shape = (image.shape[1], image.shape[0])
    ratio = float(max(new_shape))/max(original_shape)
    new_size = tuple([int(x*ratio) for x in original_shape])
    image = cv2.resize(image, new_size)
    delta_w = new_shape[0] - new_size[0]
    delta_h = new_shape[1] - new_size[1]
    top, bottom = delta_h//2, delta_h-(delta_h//2)
    left, right = delta_w//2, delta_w-(delta_w//2)
    image = cv2.copyMakeBorder(image, top, bottom, left, right, cv2.BORDER_CONSTANT, value=padding_color)
    return image

# Generator function for live stream
def gen(camera, camera_settings):
    while True:
        if camera_state.trigger:
            with picam2_backend.VideoGenerator(camera, camera_settings.settings, picam2.sensor_mode, camera_state.record_flag) as cap_gen:
                for frame in cap_gen:
                    if camera_state.trigger:
                        frame = resize_with_pad(frame, (300, 200))
                        frame = picam2_backend.frame_to_bytes(frame)
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')
                    else:
                        break
        else:
            time.sleep(0.1)

# Initialise instances 
camera_state = CameraState()
camera_settings = picam2_backend.CameraSettings()
picam2 = Camera()

# Callback functions -------
@server.route('/video_feed')
def video_feed():
    return Response(gen(picam2.camera, camera_settings),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.callback(
    output=Output('streaming-spinner', 'children'),
    inputs=[Input('camera-live-stream', 'n_clicks')],
    state=[State('record_sw', 'value')],
    prevent_initial_call=True
)
def start_stop_live_view(n_clicks, record_sw):
    camera_state.record_flag = record_sw

    if n_clicks is not None:
        if camera_state.trigger:
            camera_state.on_off()
            return ''
        else:
            camera_state.on_off()
            return dbc.Spinner(color='primary', size='md')
    else:
        return ''

@app.callback(
    output=Output('record_sw', 'disabled'),
    inputs=[Input('streaming-spinner', 'children')],
    prevent_initial_call=True
)
def update_record_sw(flag):
    if camera_state.trigger:
        return True
    else:
        return False

@app.callback(
    output=Output('exposure', 'disabled'),
    inputs=[Input('ae_switch', 'value')],
)
def exposure_slider_state(ae_mode):
    if ae_mode:
        return True
    else:
        return False

@app.callback(
    output=Output('hardware_brightness_callback', 'children'),
    inputs=[
        Input('led_brightness_switch', 'value'),
        Input('led_brightness', 'value')
    ],
)
def led_on_off(switch, value):
    if switch:
        print('LED brightness: ', value)
        led.on()
        rpi2c.set_led_brightness(value)
        return trigger
    else:
        led.off()
        return trigger

@app.callback(
    output=Output('lens_position', 'disabled'),
    inputs=[Input('focus_switch', 'value')],
)
def lens_position_slider_state(af_mode):
    if af_mode:
        return True
    else:
        return False

@app.callback(
    output=Output('adjust_datetime_callback', 'children'),
    inputs=[Input('adjust_datetime', 'n_clicks')],
    state=[
        State('date_adjust', 'date'),
        State('hour_adjust', 'value'),
        State('minute_adjust', 'value')
    ],
    prevent_initial_call=True
)
def adjust_datetime(n_clicks, date, hour, minute):
    if n_clicks is not None:
        date = datetime.strptime(date, "%Y-%m-%d").date()
        dt_adjust = datetime(
            year=date.year, 
            month=date.month, 
            day=date.day, 
            hour=hour,
            minute=minute,
            second=0)

        ts_adjust = int(dt_adjust.timestamp())
        rpi2c.write_datetime_adjust(ts_adjust)
    else:
        return ''


@app.long_callback(
    output=Output('uc_download_modal', 'is_open'),
    inputs=[Input('uc_download', 'n_clicks')],
    manager=long_callback_manager,
    running=[
        (Output('uc_download', 'children'), [dbc.Spinner(size='sm'), ' Downloading...'], 'Download log'),
        (Output('uc_download', 'disabled'), True, False)
    ],
    prevent_initial_call=True
)
def read_uc_log(n_clicks):
    if n_clicks:
        rpi2c.read_log()

        return True
    else:
        return False


@app.callback(
    output=Output('hidden-camera-settings-callback', 'children'),
    inputs=[
        Input('resolution_mode', 'value'),
        Input('ae_switch', 'value'),
        Input('exposure', 'value'),
        Input('awb_mode', 'value'),
        Input('focus_switch', 'value'),
        Input('lens_position', 'value'),
        Input('framerate', 'value'),
    ],
    prevent_initial_call=True
)
def update_camera_settings(sensor_mode, ae_mode, exposure, awb_mode, af_mode, lens_position, fps):
    live_stream_state = camera_state.trigger
    if picam2.sensor_mode != sensor_mode:
        if live_stream_state:
            camera_state.trigger = False # Stop live stream
            time.sleep(0.1)

        picam2.sensor_mode = sensor_mode

        if live_stream_state:
            camera_state.trigger = True # Restart live stream

    for setting in [exposure, awb_mode, lens_position]:
        if type(setting) == types.NoneType:
            return dash.no_update

    settings = {
        'AeEnable': 1 if ae_mode else 0,
        'AwbMode': awb_mode,
        'AfMode': 2 if af_mode else 0,
        'FrameRate': fps
    }

    if not ae_mode:
        settings['ExposureTime'] = round(exposure * 1000)

    if not af_mode:
        settings['LensPosition'] = round(lens_position)

    print(settings)

    camera_settings.settings = settings
    picam2.set_controls(settings)
    return trigger  

@app.callback(
    output=[
        Output('rtc_mcu', 'children'),
        Output('wtemp', 'children'),
        Output('wlight', 'children'),
        Output('batt1_volts', 'children'),
        Output('batt2_volts', 'children'),
        Output('start_date', 'min_date_allowed'),
        Output('start_date', 'max_date_allowed'),
        Output('start_date', 'initial_visible_month'),
    ],
    inputs=[Input('mcu_interval', 'n_intervals')],
    prevent_initial_call=True
)
def update_system_status(n):
    ts = rpi2c.read_rtc()
    wtemp, wlight = rpi2c.read_env_sensors()
    batt1_volts, batt2_volts = rpi2c.read_battery()

    rtc = f'{rpi2c.ts_2_dt(ts, for_filename=False)}'
    batt1_volts = f'{round(batt1_volts, 1)}V'
    batt2_volts = f'{round(batt2_volts, 1)}V'
    wtemp = f'{round(wtemp, 1)}°C'
    wlight = f'{round(wlight)} lux'

    # Set correct date and time for start select
    dt = datetime.fromtimestamp(ts)
    min_date_allowed = date(dt.year, dt.month, dt.day)
    max_date_allowed = date(dt.year+1, dt.month, dt.day)
    initial_visible_month = date(dt.year, dt.month, dt.day)

    print([rtc, wtemp, wlight, batt1_volts, batt2_volts])

    return [rtc, wtemp, wlight, batt1_volts, batt2_volts, min_date_allowed, max_date_allowed, initial_visible_month]


# Experiment setup callbacks ---------------------------------------------
@app.callback(
    output=[
        Output('interval', 'max'),
        Output('interval', 'marks')
    ],
    inputs=[Input('interval_switch', 'value')]
)
def update_interval_slider(switch):
    if switch:
        return [24, {i-1:i-1 for i in range(1,26,4) if i > 1}]
    else:
        return [60, {i-1:i-1 for i in range(1,62,10) if i > 1}]

@app.callback(
    output=Output('light_hour_input', 'disabled'),
    inputs=[
        Input('led_brightness_switch', 'value')
    ]
)
def update_led_schedule(switch):
    if switch: 
        return False
    else:
        return True

@app.callback(
    output=[
        Output('light_schedule_on_time', 'children'),
        Output('light_schedule_off_time', 'children')
    ],
    inputs=[
        Input('light_hour_input', 'value')
    ]
)
def update_led_calc(hr_range):
    on_time = hr_range[1] - hr_range[0]

    return f'ON: {on_time}hrs', f'OFF: {24-on_time}hrs'

@app.callback(
    output=[
        Output('config_check', 'className'),
        Output('config_check', 'color'),
        Output("start_date_modal", "is_open")
    ],
    inputs=[Input('export_config', 'n_clicks')],
    state=[
        State('duration', 'value'),
        State('interval', 'value'),
        State('interval_switch', 'value'),
        State('frequency', 'value'),
        State('acq_type_switch', 'value'),
        State('start_date', 'date'),
        State('start_hour', 'value'),
        State('start_minute', 'value'),
        State('led_brightness_switch', 'value'),
        State('led_brightness', 'value'),
        State('light_hour_input', 'value'),
        State('resolution_mode', 'value')
    ]
)
def export_config(n_clicks, duration, interval, interval_switch, frequency, acq_type, date, hour, minute, led_on, led_value, light_hr_range, sensor_mode):
    if n_clicks is not None:
        date = datetime.strptime(date, "%Y-%m-%d").date()
        start_date_dt = datetime(
            year=date.year, 
            month=date.month, 
            day=date.day, 
            hour=hour,
            minute=minute,
            second=0)

        ts_now = rpi2c.timestamp
        ts_start = int(start_date_dt.timestamp())
        print(start_date_dt, datetime.fromtimestamp(int(ts_now)).strftime('%Y-%m-%d_%H-%M-%S'))
        if ts_start < ts_now:
            return "fa-solid fa-circle-xmark", "#e01b24", True

        print('Timestamp start: ', ts_start)

        # Convert times to correct timescale
        led_on_time, led_off_time = light_hr_range
        led_on_time = led_on_time + 12 if led_on_time < 12 else led_on_time - 12
        led_off_time = led_off_time + 12 if led_off_time < 12 else led_off_time - 12

        if interval_switch:
            interval *= 60 # Convert hours to minutes

        try:
            acq_conf = {}
            acq_conf['current'] = 0
            acq_conf['frequency'] = frequency
            acq_conf['duration'] = duration
            acq_conf['interval'] = interval
            acq_conf['continuous'] = acq_type
            acq_conf['camera_controls'] = camera_settings.settings
            acq_conf['start_datetime'] = start_date_dt.strftime('%d/%m/%Y %H:%M')
            acq_conf['led_on'] = led_on
            acq_conf['led_brightness'] = led_value
            acq_conf['led_on_time'] = led_on_time
            acq_conf['led_off_time'] = led_off_time
            acq_conf['camera_mode'] = sensor_mode

            existing_configs = glob.glob('/home/pi/imseq/acquisition_config*')

            with open(f'/home/pi/imseq/acquisition_config_{len(existing_configs)+1}.json', 'w') as conf:
                json.dump(acq_conf, conf, indent=4)   

            rpi2c.duration = duration
            rpi2c.interval = interval
            rpi2c.frequency = frequency
            rpi2c.type = acq_type
            rpi2c.start_datetime = ts_start        
            rpi2c.write_config()

            # Check that config is correct
            while True:
                teensy_config = rpi2c.read_config() 
                print(teensy_config)

                if teensy_config == (duration, interval, frequency, acq_type, ts_start):
                    break

                time.sleep(0.1)

            return "fa-solid fa-circle-check", "#26a269", False
        except Exception as e:
            print(e)
            return "fa-solid fa-circle-xmark", "#e01b24", False
    else:
        return "fa-solid fa-circle-question", None, False

@app.callback(
    output=Output("start_acquisition", "disabled"),
    inputs=[Input("config_check", "color")],
)
def check_config_export(color):
    if color == "#26a269":
        return False
    else:
        return True

@app.callback(
    output=[Output("start_acquisition_modal", "is_open"), Output("rebooting_modal", "is_open")],
    inputs=[Input("start_acquisition", "n_clicks"), Input("start_acquisition_confirmed", "n_clicks")],
    state=[State("start_acquisition_modal", "is_open")],
)
def toggle_modal(start, confirm, is_open):
    if start or confirm:
        acq_is_open = False
        reboot_is_open = False
        print(start, confirm)

        if start > confirm:
            reboot_is_open = False
            acq_is_open = True

        if confirm >= start:
            reboot_is_open = True
            acq_is_open = False

        return acq_is_open, reboot_is_open
    else:
        return dash.no_update, dash.no_update

@app.callback(
    output=Output("rebooting_confirmed_callback", "children"),
    inputs=[Input("rebooting_modal", "is_open")],
)
def system_reboot(is_open):
    if is_open:
        rpi2c.set_watch_dog(rpi2c.start_datetime)
        rpi2c.set_power_off(20)
        time.sleep(1)
        os.system('sudo halt')
        time.sleep(10)
        return '' # empty return
    else:
        return dash.no_update

if __name__ == '__main__':
    app.run_server(host='0.0.0.0', debug=False)
