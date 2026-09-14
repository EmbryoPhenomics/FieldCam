import glob
from natsort import natsorted, ns

folder = '/run/user/1000/gvfs/sftp:host=10.42.0.1,user=pi/home/pi/remote_ui'

files = natsorted(glob.glob(f'{folder}/*_stdout.txt'), alg=ns.IGNORECASE)

for file in files:
	print(file)
	with open(file, 'r') as f:
		for line in f:
			if 'ERROR' in line.rstrip():
				print(line)
