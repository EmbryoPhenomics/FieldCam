import RPi.GPIO as GPIO

# Set pin reference tp physical pin number for ease of use
GPIO.setmode(GPIO.BCM)

# Mode pin
GPIO.setup(26, GPIO.IN)

while True:
	print(GPIO.input(26))
	time.sleep(0.5)