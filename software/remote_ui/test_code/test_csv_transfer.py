from smbus2 import SMBus
import time

I2C_ADDR = 0x24
CHUNK_SIZE = 32

# Arduino/STM32 register values (match the sketch)
REG_DATA_READ = 0x22   # tell device to (re)open/reset file pointer

with SMBus(1) as bus, open("received.csv", "wb") as f:
    bus.write_i2c_block_data(I2C_ADDR, REG_DATA_READ, [(0x00)])  # reset STM32 pointer
    time.sleep(0.05)

    while True:
        try:
            data = bus.read_i2c_block_data(I2C_ADDR, REG_DATA_READ, CHUNK_SIZE)
        except OSError:
            print("I2C read error, retrying...")
            time.sleep(0.1)
            continue

        print(data)

        length = data[0]

        if length == 0xFF:
            print("End of file received.")
            break

        if 1 <= length < CHUNK_SIZE:
            chunk = bytes(data[1:1+length])
            print(f"Received {length} bytes: {chunk}")
            f.write(chunk)
        else:
            print(f"Invalid length byte {length}, skipping.")
            break

        time.sleep(0.02)  # small pause (20 ms)

print("CSV file received successfully.")

