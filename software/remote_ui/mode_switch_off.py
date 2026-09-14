#!/usr/bin/python3
import json

switch = dict(stream_mode=False)
with open('./mode_switch.json', 'w') as file:
	json.dump(switch, file, indent=4)

	print('Turn mode switch off.')











