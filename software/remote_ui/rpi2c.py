import smbus
import RPi.GPIO as GPIO
from datetime import datetime
import time
import os

# Register definitions
REG_TIMESTAMP = 0x01

REG_RPI_VOLTS = 0x02
REG_RPI_CURRENT = 0x03
REG_RPI_POWER = 0x04

REG_UC_VOLTS = 0x05
REG_UC_CURRENT = 0x06
REG_UC_POWER = 0x07

REG_BATT1_VOLTS = 0x08
REG_BATT1_CURRENT = 0x09
REG_BATT1_POWER = 0x10

REG_BATT2_VOLTS = 0x11
REG_BATT2_CURRENT = 0x12
REG_BATT2_POWER = 0x13

REG_ACQ_CONFIG_R = 0x14
REG_ACQ_CONFIG_W = 0x15

REG_WATCHDOG = 0x16
REG_POWEROFF = 0x17

REG_WTEMP = 0x18
REG_WLIGHT = 0x19

REG_DT_ADJUST = 0x20

REG_LED_BRIGHTNESS = 0x21

REG_LOG_TRANSFER = 0x22
LOG_TRANSFER_CHUNK_SIZE = 32

class RPi2C:
    def __init__(self, i2c_addr=0x24, uc_log_file='./static/uc_system_log.csv'):
        self.bus = smbus.SMBus(1)
        self.i2c_addr = i2c_addr
        self.uc_log_file = uc_log_file

        self.batt1_volts = 0
        self.batt1_current = 0
        self.batt1_power = 0

        self.batt2_volts = 0
        self.batt2_current = 0
        self.batt2_power = 0

        self.rpi_current = 0
        self.rpi_voltage = 0
        self.rpi_power = 0
        self.uc_current = 0
        self.uc_voltage = 0
        self.uc_power = 0
        
        self.wtemp = 0
        self.wlight = 0

        self.duration = 0
        self.interval = 0
        self.frequency = 0
        self.type = 0
        self.start_datetime = 0
        self.led_brightness = 0

        self.timestamp = 0
 
    def i2c_read(self, addr, reg, length):
        # Two reads, first to clear buffer
        bytes_ = self.bus.read_i2c_block_data(addr, reg, length)
        bytes_ = self.bus.read_i2c_block_data(addr, reg, length)
        return bytes_

    def bts_2_float(self, bts):
        return (bts[0] << 8 | bts[1])/100

    def read_env_sensors(self):
        sensors = [self.i2c_read(self.i2c_addr, reg, length=2) for reg in [REG_WTEMP, REG_WLIGHT]]
        self.wtemp, self.wlight = [self.bts_2_float(bts) for bts in sensors]
        return self.wtemp, self.wlight

    @staticmethod
    def ts_2_dt(ts, for_filename=True):
        format_ = '%d-%m-%Y_%H-%M'
        if not for_filename:
            format_ = '%d/%m/%Y %H:%M'
        return datetime.fromtimestamp(ts).strftime(format_)

    def read_rtc(self):
        timestamp_bytes = self.i2c_read(self.i2c_addr, REG_TIMESTAMP, length=4)
        a,b,c,d = timestamp_bytes[:4]
        self.timestamp = (a << 24 | b << 16 | c << 8 | d)
        return self.timestamp

    def read_config(self):
        config_bytes = self.i2c_read(self.i2c_addr, REG_ACQ_CONFIG_R, length=10)
        self.duration = config_bytes[0]
        self.interval = (config_bytes[1] << 8 | config_bytes[2])
        self.frequency = (config_bytes[3] << 8 | config_bytes[4])
        self.type = config_bytes[5]
        self.start_datetime = (config_bytes[6] << 24 | config_bytes[7] << 16 | config_bytes[8] << 8 | config_bytes[9])
        return (self.duration, self.interval, self.frequency, self.type, self.start_datetime)

    def write_config(self):
        interval = (((self.interval >> 8) & 0xff), (self.interval & 0xff))
        frequency = (((self.frequency >> 8) & 0xff), (self.frequency & 0xff))
        start_datetime = (((self.start_datetime >> 24) & 0xff), ((self.start_datetime >> 16) & 0xff), ((self.start_datetime >> 8) & 0xff), (self.start_datetime & 0xff))
        args = [self.duration, *interval, *frequency, self.type, *start_datetime]
        self.bus.write_i2c_block_data(self.i2c_addr, REG_ACQ_CONFIG_W, args)

    def read_battery(self):
        readout = [self.i2c_read(self.i2c_addr, reg, length=2) for reg in [REG_BATT1_VOLTS, REG_BATT2_VOLTS]]
        self.batt1_volts, self.batt2_volts = [self.bts_2_float(dt) for dt in readout]
        return self.batt1_volts, self.batt2_volts

    def read_power(self):
        rpi_readouts = [self.i2c_read(self.i2c_addr, reg, length=2) for reg in [REG_RPI_VOLTS, REG_RPI_CURRENT, REG_RPI_POWER]]
        self.rpi_voltage, self.rpi_current, self.rpi_power = [self.bts_2_float(bts) for bts in rpi_readouts]

        uc_readouts = [self.i2c_read(self.i2c_addr, reg, length=2) for reg in [REG_UC_VOLTS, REG_UC_CURRENT, REG_UC_POWER]]
        self.uc_voltage, self.uc_current, self.uc_power = [self.bts_2_float(bts) for bts in uc_readouts]

        return (self.rpi_voltage, self.rpi_current, self.rpi_power, self.uc_voltage, self.uc_current, self.uc_power)

    def write_datetime_adjust(self, time):
        self.bus.write_i2c_block_data(self.i2c_addr, REG_DT_ADJUST, [*(((time >> 24) & 0xff), ((time >> 16) & 0xff), ((time >> 8) & 0xff), (time & 0xff))])

    def set_watch_dog(self, time): # Set watch dog timer in minutes
        args = (((time >> 24) & 0xff), ((time >> 16) & 0xff), ((time >> 8) & 0xff), (time & 0xff))
        self.bus.write_i2c_block_data(self.i2c_addr, REG_WATCHDOG, [*args]) 

    def set_power_off(self, time): # Set time to turn off power in seconds
        self.bus.write_i2c_block_data(self.i2c_addr, REG_POWEROFF, [*(((time >> 8) & 0xff), (time & 0xff))]) 

    def set_led_brightness(self, value):
        self.led_brightness = value
        self.bus.write_i2c_block_data(self.i2c_addr, REG_LED_BRIGHTNESS, [(value)])

    def read_log(self):        
        with open(self.uc_log_file, 'wb') as file:
            self.bus.write_i2c_block_data(self.i2c_addr, REG_LOG_TRANSFER, [(0x00)])  # reset file pointer
            time.sleep(2)

            while True:
                try:
                    data = self.bus.read_i2c_block_data(self.i2c_addr, REG_LOG_TRANSFER, LOG_TRANSFER_CHUNK_SIZE)
                except OSError:
                    print("I2C read error, retrying...")
                    time.sleep(0.1)
                    continue

                length = data[0]

                if length == 0xFF:
                    print('End of file, stopping...')
                    break

                if length == 0xFB:
                    print("SD card not ready, stopping...")
                    break

                if length == 0xFC:
                    print("Transfer file not ready, stopping...")
                    break

                if length == 0xFD:
                    print("No bytes to receive, stopping...")
                    break

                if 1 <= length < LOG_TRANSFER_CHUNK_SIZE:
                    chunk = bytes(data[1:1+length])
                    print(f"Received {length} bytes: {chunk}")
                    file.write(chunk)
                    prev_empty_file = True
                else:
                    print(f"Invalid length byte {length}, skipping.")
                    continue

                time.sleep(0.05)  # small pause (20 ms)            


class LED:
    def __init__(self, led_pin=22):
        self.led_pin = led_pin
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.led_pin, GPIO.OUT)

    def on(self):
        GPIO.output(self.led_pin, 1)

    def off(self):
        GPIO.output(self.led_pin, 0)


if __name__ == '__main__':
    import os 

    # led = LED()
    rpi2c = RPi2C()

    rpi2c.read_log()


    # rpi2c.set_led_brightness(20)
    # time.sleep(0.1)

    # led.on()
    # time.sleep(1)

    # try:
    #     print(f'Timestamp RTC: {rpi2c.ts_2_dt(rpi2c.read_rtc(), for_filename=False)}')
    #     # print(f'Experimental config: {rpi2c.read_config()}')
    #     print(f'Input voltages: {rpi2c.read_battery()}')
    #     print(f'Power (RPi, UC): {rpi2c.read_power()}')

    #     # Change config
    #     rpi2c.duration = 15
    #     rpi2c.interval = 45
    #     rpi2c.frequency = 24
    #     rpi2c.type = 1
    #     rpi2c.start_datetime = rpi2c.timestamp + 1000
    #     rpi2c.write_config()

    #     # Confirm config change
    #     print(f'Experimental config: {rpi2c.read_config()}')
        

    #     # rpi2c.set_watch_dog(1)
    #     # print(rpi2c.i2c_read(0x24, 0x19))

    #     # rpi2c.set_power_off(20)
    #     # print(rpi2c.i2c_read(0x24, 0x20))
    # except Exception as e:
    #     print(e)
    
    # led.off()

    # # # Shut down ---
    # # time.sleep(1)
    # # os.system('sudo halt')
    # # time.sleep(5)
