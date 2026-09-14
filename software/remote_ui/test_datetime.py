import datetime
from zoneinfo import ZoneInfo  # Python 3.9+

ts_now = int(datetime.datetime.now().timestamp())

date_str = '2025-04-10'
hour = 10
minute = 50

date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()

ts1 = datetime.datetime(
    year=date.year, 
    month=date.month, 
    day=date.day, 
    hour=hour,
    minute=minute,
    second=0
)

format_ = '%d-%m-%Y_%H-%M'
ts_start = int(ts1.timestamp())

print(ts_start, ts_now)
print(datetime.datetime.fromtimestamp(ts_now).strftime(format_))
print(datetime.datetime.fromtimestamp(int(ts1.timestamp())).strftime(format_))
