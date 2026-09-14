
extern "C" int _write(int file, char *ptr, int len) {
  // Send characters over SWO (ITM Port 0)
  for (int i = 0; i < len; i++) {
    ITM_SendChar(*ptr++);
  }
  return len;
}

#include "STM32LowPower.h"
#include <string>
#include <Wire.h>
#include <Adafruit_INA260.h>
#include <Adafruit_DS3502.h>
#include <SPI.h>
#include <SD.h>
#include "STM32LowPower.h"
#include "SparkFun_VEML6030_Ambient_Light_Sensor.h"
#include <SparkFun_TMP117.h> // Used to send and recieve specific information from our sensor

#define SD_CS    PA5  // example CS pin

File myFile;

TMP117 temp_sensor; // Initalize sensor

#define AL_ADDR 0x10

SparkFun_Ambient_Light veml_6030 = SparkFun_Ambient_Light(AL_ADDR);
// Possible values: .125, .25, 1, 2
// Both .125 and .25 should be used in most cases except darker rooms.
// A gain of 2 should only be used if the sensor will be covered by a dark
// glass.
float gain = .125;
// Possible integration times in milliseconds: 800, 400, 200, 100, 50, 25
// Higher times give higher resolutions and should be used in darker light. 
int integtime = 100;
long luxVal = 0; 

Adafruit_INA260 ina260_5v = Adafruit_INA260();
Adafruit_INA260 ina260_3v3 = Adafruit_INA260();
Adafruit_INA260 ina260_batt1 = Adafruit_INA260();
Adafruit_INA260 ina260_batt2 = Adafruit_INA260();
Adafruit_DS3502 ds3502 = Adafruit_DS3502();

#define SDA2_SLAVE PB11 // Slave to RPi Master
#define SCL2_SLAVE PB10 // Slave to RPi Master
#define I2C_ADDRESS 0x24

TwoWire Wire2(SDA2_SLAVE, SCL2_SLAVE);

#define BATT_SW PA8

// the setup function runs once when you press reset or power the board
void setup() {
  // Set up slave i2c for testing
  Wire2.begin(I2C_ADDRESS);

  // Enable tracing on Cortex-M4 (ITM needs TRCENA set)
  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;

  // Optional: turn on ITM Stimulus Port 0
  ITM->TCR = ITM_TCR_ITMENA_Msk      // Enable ITM
           | ITM_TCR_SYNCENA_Msk     // Enable sync packets
           | ITM_TCR_TSENA_Msk       // Enable timestamp packets
           | ITM_TCR_SWOENA_Msk;     // Enable SWO output

  ITM->TER |= (1UL << 0); // Enable Stimulus Port 0

  bool sdInitialized = SD.begin(SD_CS);

  if (!sdInitialized) {
    printf("initialization failed.\n");
    return;
  } else {
    printf("Wiring is correct and a card is present.\n");
  }

  LowPower.begin();
  ina260_3v3.begin(0x41);
  ina260_5v.begin(0x40);
  ina260_batt1.begin(0x45);
  ina260_batt2.begin(0x44);
  if (!ds3502.begin(0x28)){
    ds3502.begin(0x2B);
  }

  temp_sensor.begin(0x49);

  veml_6030.begin();
  // Again the gain and integration times determine the resolution of the lux
  // value, and give different ranges of possible light readings. Check out
  // hoookup guide for more info. 
  veml_6030.setGain(gain);
  veml_6030.setIntegTime(integtime);

  printf("Reading settings...\n"); 
  float gainVal = veml_6030.readGain();
  printf("Gain: %ld", (long)(gainVal));
  int timeVal = veml_6030.readIntegTime();
  printf(" Integration Time: %ld\n", (long)(timeVal));

  ds3502.setWiper(25);

  // Blinky
  pinMode(PA0, OUTPUT);

  // 5v and 10v boost enable
  pinMode(PB13, OUTPUT);digitalWrite(PB13, HIGH); // 5V
  pinMode(PB14, OUTPUT);digitalWrite(PB14, HIGH); // 10V
}

// the loop function runs over and over again forever
void loop() {
  ina260_batt1.setMode(INA260_MODE_CONTINUOUS);
  ina260_batt2.setMode(INA260_MODE_CONTINUOUS);
  ina260_3v3.setMode(INA260_MODE_CONTINUOUS);
  ina260_5v.setMode(INA260_MODE_CONTINUOUS);

  luxVal = veml_6030.readLight();
  printf("Ambient Light Reading: %ld lux\n", (long)(luxVal));

  if (temp_sensor.dataReady() == true) // Function to make sure that there is data ready to be printed, only prints temperature values when data is ready
  {
    float tempC = temp_sensor.readTempC();  
    printf("Temperature (Celsius): %ld\n", (long)(tempC));
  }

  // Turn on power paths
  digitalWrite(PA0, HIGH);  // turn the LED on (HIGH is the voltage level)
  delay(100);
  digitalWrite(PB13, HIGH);
  delay(100);
  digitalWrite(PB14, HIGH);

  // open the file. note that only one file can be open at a time,
  // so you have to close this one before opening another.
  myFile = SD.open("test.txt", FILE_WRITE);

  // if the file opened okay, write to it:
  if (myFile) {
    printf("Writing to test.txt...");
    myFile.println("testing 1, 2, 3.");
    // close the file:
    myFile.close();
    printf("done.\n");
  } else {
    // if the file didn't open, print an error:
    printf("error opening test.txt.\n");
  }

  printf("Batt1 power readout: %ldmA, %ldmV, %ldmW ",
    (long)(ina260_batt1.readCurrent()),
    (long)(ina260_batt1.readBusVoltage()),
    (long)(ina260_batt1.readPower()));
  printf("Batt2 power readout: %ldmA, %ldmV, %ldmW\n ",
    (long)(ina260_batt2.readCurrent()),
    (long)(ina260_batt2.readBusVoltage()),
    (long)(ina260_batt2.readPower()));
  printf("3v3 power readout: %ldmA, %ldmV, %ldmW ",
    (long)(ina260_3v3.readCurrent()),
    (long)(ina260_3v3.readBusVoltage()),
    (long)(ina260_3v3.readPower()));
  printf("5v power readout: %ldmA, %ldmV, %ldmW\n",
    (long)(ina260_5v.readCurrent()),
    (long)(ina260_5v.readBusVoltage()),
    (long)(ina260_5v.readPower()));

  luxVal = veml_6030.readLight();
  printf("Ambient Light Reading: %ld lux\n", (long)(luxVal));

  delay(2000);                      // wait for a second
  digitalWrite(PB14, LOW);
  delay(50);
  digitalWrite(PB13, LOW);
  delay(50);
  digitalWrite(PA0, LOW);   // turn the LED off by making the voltage LOW
  ina260_batt1.setMode(INA260_MODE_SHUTDOWN);
  ina260_batt2.setMode(INA260_MODE_SHUTDOWN);
  ina260_3v3.setMode(INA260_MODE_SHUTDOWN);
  ina260_5v.setMode(INA260_MODE_SHUTDOWN);
  delay(5000);
  // LowPower.deepSleep(5000);
}
