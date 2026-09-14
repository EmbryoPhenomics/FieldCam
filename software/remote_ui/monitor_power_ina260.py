import busio
import board
import adafruit_ina260
import time

i2c = busio.I2C(board.SCL, board.SDA)
ina260 = adafruit_ina260.INA260(i2c)

while True:
	print("Current:", ina260.current, "Voltage:", ina260.voltage, "Power:", ina260.power, "Power/Voltage:", ina260.power / ina260.voltage)
	time.sleep(0.5)


