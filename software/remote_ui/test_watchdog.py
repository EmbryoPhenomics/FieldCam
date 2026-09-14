import datetime

watchdog_end_time = 0
timestamp = int(datetime.datetime.now().timestamp())

watchdog_time_config = 25

if ((watchdog_time_config > 0) & (watchdog_end_time == 0)):
  watchdog_end_time = timestamp + (watchdog_time_config * 60)
else:
	if ((watchdog_time_config == 0) & (watchdog_end_time != 0)):
  		watchdog_end_time = 0

watchdog_time_config = 0

if ((watchdog_time_config > 0) & (watchdog_end_time == 0)):
  watchdog_end_time = timestamp + (watchdog_time_config * 60)
else:
	if ((watchdog_time_config == 0) & (watchdog_end_time != 0)):
  		watchdog_end_time = 0

print(watchdog_time_config, watchdog_end_time)