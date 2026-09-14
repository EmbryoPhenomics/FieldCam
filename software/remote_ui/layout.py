#!/usr/bin/python3
import dash_bootstrap_components as dbc
import dash
from dash import Dash, html, dcc, Input, Output, State, clientside_callback, callback
import psutil
import json
from flask import Flask, Response

def disk_usage():
    space = psutil.disk_usage("/")
    free = space.free / float(1<<30) * 1.074
    total = space.total / float(1<<30) * 1.074

    return f'{round(free)} / {round(total)} GB'


color_mode_switch =  html.Span(
    [
        dbc.Label(className="fa fa-moon", html_for="switch"),
        dbc.Switch(id="switch", value=True, className="d-inline-block ms-1", persistence=False),
        dbc.Label(className="fa fa-sun", html_for="switch"),
    ]
)

storage_info = html.Span(
    [
        dbc.Label(disk_usage(), id='disk_space', style={"margin-right": "5px"}),
        dbc.Label(className="fa-solid fa-sim-card"),
    ]
)

layout = dbc.Container(
    [
        dbc.Row(
            [
                dbc.Col(color_mode_switch, width={'size': 7}),
                dbc.Col(storage_info, width={'size': 5}),
            ]
        ),
        dbc.Row(            
            dbc.Col(
                dbc.Card([
                    dbc.CardHeader(
                        dbc.Row([
                            dbc.Col(dbc.Label('System status'), width={'size': 5}),
                            dbc.Col(dbc.Label(id="rtc_mcu"), width={'size': 7}),
                            dcc.Interval(id='mcu_interval', interval=5000, n_intervals=0)
                        ])
                    ),
                    dbc.CardBody(
                        [
                            dbc.Row([
                                dbc.Col([
                                    dbc.Card([
                                        # dbc.CardHeader("Sensors"),
                                        # Temperature and Pressure

                                        dbc.CardBody([
                                            dbc.Label('Sensors'),
                                            html.Div(children=[
                                                html.Div(children=[
                                                    dbc.Label(className='fa-solid fa-temperature-quarter'),
                                                    dbc.Label('--°C', id='wtemp', style={"margin-left": "3px"}),
                                                ], style={'width': '50%', 'display': 'table-cell'}),
                                                html.Div(children=[
                                                    dbc.Label(className='fa-solid fa-lightbulb'),
                                                    dbc.Label('-- lux', id='wlight', style={"margin-left": "3px"}),
                                                ], style={'width': '50%', 'display': 'table-cell'}),
                                            ], style={'width': '100%', 'display': 'table'}),

                                            html.Br(),

                                            dbc.Label('Adjust system time'),
                                            dbc.Row([
                                                dbc.Col([dcc.DatePickerSingle(id='date_adjust', display_format='DD/MM/YYYY')], width={'size': 12}),
                                            ]),
                                            dbc.Row([
                                                dbc.Col([dbc.Input(placeholder='Hour', type="number", min=0, max=24, step=1, id='hour_adjust', style={"width": 80}, persistence=False)], width={'size': 6}),
                                                dbc.Col([dbc.Input(placeholder='Minute', type="number", min=0, max=60, step=1, id='minute_adjust', style={"width": 80}, persistence=False)], width={'size': 6}),
                                            ]),                                            
                                            dbc.Button('Update', id='adjust_datetime'),
                                            html.Div(id='adjust_datetime_callback'),
                                        ]),
                                    ]),
                                ], width={'size': 7}),
                                dbc.Col([
                                    dbc.Card([
                                        dbc.CardBody([
                                            dbc.Label("Battery charge"),
                                            html.Br(),

                                            dbc.Label(className="fa-solid fa-battery-three-quarters fa-rotate-270"), 
                                            dbc.Label('0.0V', id='batt1_volts', style={"margin-left": "10px"}),
                                            html.Br(),
                                            dbc.Label(className="fa-solid fa-battery-three-quarters fa-rotate-270"), 
                                            dbc.Label('0.0V', id='batt2_volts', style={"margin-left": "10px"}),

                                            html.Hr(),

                                            dbc.Label('Microcontroller'),
                                            dbc.Button("Download log",
                                                        id="uc_download",
                                                        color="primary",
                                                        size='sm'),

                                            dbc.Modal(
                                                [
                                                    dbc.ModalBody("Microcontroller log is ready for download."),
                                                    dbc.ModalFooter(
                                                        dbc.Button("Download",
                                                                    href="/static/uc_system_log.csv",
                                                                    download="uc_system_log.csv",
                                                                    external_link=True,
                                                                    color="primary",
                                                                    n_clicks=0),
                                                    ),
                                                ],
                                                id="uc_download_modal",
                                                is_open=False,
                                            ), 
                                        ]),
                                    ]),
                                ], width={'size': 5}),
                            ], className='g-1'),
                        ]
                    ),
                ]),
            ),
        ),
        html.Br(),
        dbc.Row(            
            dbc.Col(
                dbc.Card([
                    dbc.CardHeader("Camera control"),
                    dbc.CardBody([
                        dbc.Tabs([
                            dbc.Tab([
                                dbc.Row([
                                    dcc.Dropdown(
                                        id='resolution_mode',
                                        placeholder='Select resolution...',
                                        value=0,
                                        options=[
                                            dict(label='1536 x 864', value=0),
                                            dict(label='1920 x 1080', value=1),
                                        ],
                                        persistence=False),
                                    html.Div(id='resolution_callback'),                                    
                                ]),
                            ], label="Resolution"),
                            dbc.Tab([
                                dbc.Row([
                                    dbc.Col([dbc.Label('Shutter speed (ms)')], width={'size': 5}),
                                    dbc.Col([
                                        dbc.Label('ME', html_for='ae_switch'),
                                        dbc.Switch(id="ae_switch", value=True, className="d-inline-block ms-1", persistence=False),
                                        dbc.Label('AE', html_for='ae_switch'),
                                    ], width={'size': 5}),
                                    dbc.Col([
                                        dbc.Label(className="fa-solid fa-circle-info", id='ae_info'),
                                        dbc.Tooltip(
                                            "ME: Manual tuning of shutter speed.\n"
                                            "AE: Auto tuning of shutter speed.",
                                            target="ae_info",
                                        ),
                                    ], width={'size': 2})
                                ]),

                                dcc.Slider(
                                    id='exposure',
                                    min=0,
                                    max=100,
                                    value=10,
                                    disabled=False,
                                    tooltip={'always_visible': True, 'placement': 'bottom'},
                                    persistence=False),
                                html.Div(id='exposure_callback'),

                                html.Br(),

                                dbc.Label('Framerate'),
                                dcc.Slider(
                                    id='framerate',
                                    min=5,
                                    max=30,
                                    value=30,
                                    disabled=False,
                                    tooltip={'always_visible': True, 'placement': 'bottom'},
                                    persistence=False),
                                html.Div(id='framerate_callback'),                                

                            ], label="Shutter"),
                            dbc.Tab([
                                dbc.Label('Auto white balance modes'),
                                dcc.Dropdown(
                                    id='awb_mode',
                                    placeholder='Select AWB mode...',
                                    value=0,
                                    options=[
                                        dict(label='Auto', value=0),
                                        dict(label='Tungsten', value=2),
                                        dict(label='Fluorescent', value=3),
                                        dict(label='Indoor', value=4),
                                        dict(label='Daylight', value=5),
                                        dict(label='Cloudy', value=6),
                                    ],
                                    persistence=False),
                                html.Div(id='awb_callback'),
                            ], label="AWB"),
                            dbc.Tab([ # For now the LED tab will just enable on/off switching
                                dbc.Label('LED ring brightness'),
                                html.Br(),
                                dbc.Label('OFF', html_for='led_brightness_switch'),
                                dbc.Switch(id="led_brightness_switch", value=False, className="d-inline-block ms-1", persistence=False),
                                dbc.Label('ON', html_for='led_brightness_switch'),                                
                                dcc.Slider(
                                    id='led_brightness',
                                    min=0,
                                    max=100,
                                    value=0,
                                    tooltip={'always_visible': True, 'placement': 'bottom'},
                                    persistence=False),
                                html.Div(id='hardware_brightness_callback'),
                            ], label="LED", disabled=False),
                            dbc.Tab([
                                dbc.Row([
                                    dbc.Col([dbc.Label('Lens control')], width={'size': 5}),
                                    dbc.Col([
                                        dbc.Label('MF', html_for='focus_switch'),
                                        dbc.Switch(id="focus_switch", value=True, className="d-inline-block ms-1", persistence=False),
                                        dbc.Label('AF', html_for='focus_switch'),
                                    ], width={'size': 5}),
                                    dbc.Col([
                                        dbc.Label(className="fa-solid fa-circle-info", id='af_info'),
                                        dbc.Tooltip(
                                            "MF: Manual focus of Lens.\n"
                                            "AF: Auto focus of Lens.",
                                            target="af_info",
                                        ),
                                    ], width={'size': 2})
                                ]),
                         

                                # Lens distance vs position
                                # 0 = > 2m
                                # 1 = ~ 2m
                                # 2 = ~ 1.5m
                                # 4 = ~ 1m
                                # 8 = ~ 50cm
                                # 16 = ~ 20cm
                                # 20 = ~ 10cm

                                dcc.Slider(
                                    id='lens_position',
                                    min=0,
                                    max=20,
                                    value=0,
                                    tooltip={'always_visible': True, 'placement': 'bottom'},
                                    disabled=False,
                                    persistence=False),
                                html.Div(id='lens_position_callback'),
                            ], label="Lens"),                           
                        ]),
                        html.Div(id='hidden-camera-settings-callback'),

                        html.Br(),
                        html.Img(src="/video_feed"),
                        html.Br(),

                        dbc.Row([
                            dbc.Col([dbc.Button('Start/Stop Stream', id='camera-live-stream')], width={'size': 6}),
                            dbc.Col([html.Div(id='streaming-spinner')], width={'size': 2}),
                        ]),

                        html.Br(),

                        dbc.Row([
                            dbc.Col([dbc.Label('Record stream?')], width={'size': 6}),
                            dbc.Col([
                                dbc.Label("OFF", html_for="record_sw"),        
                                dbc.Switch(id="record_sw", value=False, className="d-inline-block ms-1", persistence=False, disabled=False),
                                dbc.Label("ON", html_for="record_sw"),
                            ], width={'size': 6})
                        ]),

                        html.Div(id='record_sw_callback'),
                    ]),
                ])
            )
        ),
        html.Br(),
        dbc.Row(            
            dbc.Col(
                dbc.Card([
                    dbc.CardHeader("Experiment design"),
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([dbc.Label('Duration (minutes)')], width={'size': 10}),
                            dbc.Col([
                                dbc.Label(className="fa-solid fa-circle-info", id='duration_info'),
                                dbc.Tooltip(
                                    "Duration to record video (minutes).",
                                    target="duration_info",
                                ),
                            ], width={'size': 2})
                        ]),
                 
                        dcc.Slider(
                            id='duration',
                            min=1,
                            max=60,
                            step=1,
                            value=1,
                            marks={i-1:i-1 for i in range(1,62,10) if i > 1},                            
                            tooltip={'always_visible': True, 'placement': 'bottom'},
                            persistence=False),
                        html.Div(id='duration_callback'),

                        html.Br(),

                        dbc.Row([
                            dbc.Col([dbc.Label('Interval')], width={'size': 4}),
                            dbc.Col([
                                dbc.Label(children="Minutes", html_for="interval_switch"),
                                dbc.Switch(id="interval_switch", value=False, className="d-inline-block ms-1", persistence=False),
                                dbc.Label(children="Hours", html_for="interval_switch"),
                            ], width={'size': 6}),
                            dbc.Col([
                                dbc.Label(className="fa-solid fa-circle-info", id='interval_info'),
                                dbc.Tooltip(
                                    "Standby interval (minutes), \n"
                                    "i.e. time between recordings.",
                                    target="interval_info",
                                ),
                            ], width={'size': 2})
                        ]),
                 
                        dcc.Slider(
                            id='interval',
                            min=1,
                            max=60,
                            value=1,
                            step=1,
                            marks={i-1:i-1 for i in range(1,62,10) if i > 1},
                            tooltip={'always_visible': True, 'placement': 'bottom'},
                            persistence=False),
                        html.Div(id='interval_callback'),
                        html.Br(),

                        dbc.Row([
                            dbc.Col([dbc.Label('Frequency')], width={'size': 10}),
                            dbc.Col([
                                dbc.Label(className="fa-solid fa-circle-info", id='frequency_info'),
                                dbc.Tooltip(
                                    "Number of times to record video.",
                                    target="frequency_info",
                                ),
                            ], width={'size': 2})
                        ]),
                 
                        dbc.Input(type="number", min=0, max=24*14, step=1, id='frequency', style={"width": 100}, persistence=False),
                        html.Div(id='frequency_callback'),
                        html.Br(),

                        dbc.Row([
                            dbc.Col([dbc.Label('Light schedule')], width={'size': 6}),
                            dbc.Col([
                                html.Div(children=[
                                    html.Div(children=[
                                        dbc.Label('ON: --', id='light_schedule_on_time', style={"margin-left": "1px", "color": "DeepSkyBlue"}),
                                    ], style={'width': '50%', 'display': 'table-cell'}),
                                    html.Div(children=[
                                        dbc.Label('OFF: --', id='light_schedule_off_time', style={"margin-left": "1px", "color": "Grey"}),
                                    ], style={'width': '50%', 'display': 'table-cell'}),
                                ], style={'width': '100%', 'display': 'table'}),
                            ], width={'size': 6})
                        ]),

                        dcc.RangeSlider(
                            min=0, 
                            max=24, 
                            step=1, 
                            value=[6, 18], 
                            marks={0: "12pm", 6: "6pm", 12: "12am", 18: "6am", 24: "11pm"}, 
                            tooltip={
                                "placement": "top", 
                                "always_visible": True, 
                                "transform": "timeIn12hrs",
                                "style": {"color": "White", "fontSize": "11px"}}, 
                            id='light_hour_input',
                            disabled=True),
                        html.Br(),

                        dbc.Row([
                            dbc.Col([dbc.Label('Start date and time')], width={'size': 10}),
                            dbc.Col([
                                dbc.Label(className="fa-solid fa-circle-info", id='start_date_time'),
                                dbc.Tooltip(
                                    "Date and time to start experiment.",
                                    target="start_date_time",
                                ),
                            ], width={'size': 2})
                        ]),

                        dbc.Row([
                            dbc.Col([dcc.DatePickerSingle(id='start_date', display_format='DD/MM/YYYY')], width={'size': 5}),
                            dbc.Col([], width={'size': 1}),
                            dbc.Col([dbc.Input(placeholder='Hour...', type="number", min=0, max=24, step=1, id='start_hour', persistence=False)], width={'size': 3}),
                            dbc.Col([dbc.Input(placeholder='Minute...', type="number", min=0, max=60, step=1, id='start_minute', persistence=False)], width={'size': 3}),
                        ]),

                        dbc.Modal(
                            [
                                dbc.ModalBody("Start date is before the current date and time. Please select a start date/time in the future."),
                            ],
                            id="start_date_modal",
                            is_open=False,
                        ),

                        html.Div(id='date_time_callback'),
                        html.Br(),

                        dbc.Row([
                            dbc.Col([dbc.Label('Acquisition type')], width={'size': 10}),
                            dbc.Col([
                                dbc.Label(className="fa-solid fa-circle-info", id='type_info'),
                                dbc.Tooltip(
                                    "Whether to perform experiment 'continuously', \n."
                                    "i.e no power off, or to perform a 'wake/sleep cycle' \n"
                                    "where system powers down between video recordings.",
                                    target="type_info",
                                ),
                            ], width={'size': 2})
                        ]),

                        dbc.Label("Wake/Sleep", html_for="acq_type_switch"),        
                        dbc.Switch(id="acq_type_switch", value=False, className="d-inline-block ms-1", persistence=False),
                        dbc.Label("Continuous", html_for="acq_type_switch"),

                        html.Div(id='type_callback'),

                        html.Br(),
                        dbc.Row([
                            dbc.Col([dbc.Button('Export config', id='export_config', disabled=False),], width={'size': 8}),
                            dbc.Col([html.Br()], width={'size': 2}),
                            dbc.Col([dbc.Label(className="fa-solid fa-circle-question", id='config_check')], width={'size': 2}),
                        ]),
                        html.Br(),
                        dbc.Button('Start acquisition', id='start_acquisition', disabled=True),
                        dbc.Modal(
                            [
                                dbc.ModalBody("By clicking start the system will begin the deployment, are you sure you want to proceed? If so, make sure that you move the magnet for setting the mode back to it's home position."),
                                dbc.ModalFooter(
                                    dbc.Button(
                                        "Yes", id="start_acquisition_confirmed", className="ms-auto", n_clicks=0
                                    )
                                ),
                            ],
                            id="start_acquisition_modal",
                            is_open=False,
                        ),                                     
                        dbc.Modal(
                            [
                                dbc.ModalBody("Deployment has started..."),
                            ],
                            id="rebooting_modal",
                            is_open=False,
                        ),
                        html.Div(id="rebooting_confirmed_callback"),  
                    ])

                ])
            )
        ),

    ], fluid=True, 
    # style={'backgroundColor':'grey'}
)

if __name__ == '__main__':
    # Initialise app
    server = Flask(__name__)
    app = dash.Dash(__name__, server=server, external_stylesheets=['./static/bootstrap.min.css', './static/fontawesome-free-6.3.0-web/css/all.css'])
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

    app.run_server(host='0.0.0.0', debug=False)
