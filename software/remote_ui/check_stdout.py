import glob
from natsort import natsorted, ns

folder = './'

files = natsorted(glob.glob(f'{folder}/*_stdout.txt'), alg=ns.IGNORECASE)

for file in files:
	print(file)
	with open(file, 'r') as f:
		for line in f:
			if 'ERROR' in line.rstrip():
				print(line)
