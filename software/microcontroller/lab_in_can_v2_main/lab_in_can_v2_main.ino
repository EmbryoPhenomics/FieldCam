#include <Arduino.h> 
#include "STM32LowPower.h"
#include <string>
#include <Wire.h>
#include <Adafruit_INA260.h>
#include <Adafruit_DS3502.h>
#include <SPI.h>
#include <SD.h>
#include <map>
#include <string>
#include <STM32RTC.h>
#include "SparkFun_VEML6030_Ambient_Light_Sensor.h"
#include <SparkFun_TMP117.h> // Used to send and recieve specific information from our sensor

// To do
// Dynamic lighting based on light sensor

// Blinky
#define LED_BUILTIN PA0

// Pin Definitions:
#define SDA1_MASTER PA10
#define SCL1_MASTER PA9

#define SDA2_SLAVE PB11 // Slave to RPi Master
#define SCL2_SLAVE PB10 // Slave to RPi Master

// SD chip select
#define SD_CS PA5

/* Power Control */
#define EN_5V PB13
#define EN_10V PB14
#define BATT_SW PA8
#define BATT_ST PB15

// Battery LEDs
#define BATT1_LED PB5
#define BATT2_LED PB6

// Mode Switches
#define TURN_ON_OFF PB2

#define RPI_GPIO22 PB12

// Definitions of global variables -----
float rpi_volts, rpi_current, rpi_power;
float uc_volts, uc_current, uc_power;
float batt1_volts, batt1_current, batt1_power;
float batt2_volts, batt2_current, batt2_power;
bool POWER_CHECK = false;

float temp_celsius;
long light_lux;

uint8_t led_brightness = 0;

// Wake and sleep parameters set by RPi
uint32_t watchdog_time_config;
volatile uint32_t watchdog_end_time;

uint16_t poweroff_time_config;
volatile uint32_t poweroff_end_time;

// Acquisition config
uint8_t duration = 0;
uint8_t interval = 0;
uint16_t frequency = 0;
uint8_t type = 0;
uint32_t start_datetime = 0;
uint32_t timestamp = 0;

bool SLEEP_ACTIVE = false;

int current_power_src = -1; // Can be -1 = No valid input, 1 = batt1, 2 = batt2
const char* power_log_filename = "syslog.txt"; // Filename for logging power inputs
File log_file;

bool log_file_start = false;
int log_file_counter = 0; 
int log_file_counter_interval = 20; // Only log data every 20 iterations of main loop (~10sec)

File transferFile;
volatile uint32_t fileSize;
bool sdReady    = false;
volatile bool eofReached = false;
volatile bool file_transfer_active = false;
volatile bool requestBusy = false;
volatile bool reopenPending = false;

// ---------------------------------------

// Sensors ---------------------------------------------------------------------------------

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

void init_light_sensor(void){
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
}

void init_temp_sensor(void){
  temp_sensor.begin(0x49);
}

long read_light_lux(void){
  light_lux = veml_6030.readLight(); 
  return light_lux;
}

float read_temp(void){
  if (temp_sensor.dataReady() == true) // Function to make sure that there is data ready to be printed, only prints temperature values when data is ready
  {
    temp_celsius = temp_sensor.readTempC();  
  }  
  return temp_celsius;
}
// ---------------------------------------------------------------------------------------

// GPIO ------------------------------------------------------------------------------------

void configureGPIO(void){
    /*  INPUTS
    --------------*/ 
    pinMode(TURN_ON_OFF, INPUT);
    pinMode(RPI_GPIO22, INPUT);
    pinMode(BATT_ST, INPUT);

    /*  OUTPUTS
    --------------*/ 
    pinMode(LED_BUILTIN, OUTPUT);digitalWrite(LED_BUILTIN, LOW);  // Led Pin
    pinMode(BATT1_LED, OUTPUT);digitalWrite(BATT1_LED, LOW);  // BATT1 Led Pin
    pinMode(BATT2_LED, OUTPUT);digitalWrite(BATT2_LED, LOW);  // BATT2 Led Pin

    pinMode(EN_5V, OUTPUT);digitalWrite(EN_5V, LOW);  // System Power off
    pinMode(EN_10V, OUTPUT);digitalWrite(EN_10V, LOW);  // LED 14V boost off
    pinMode(BATT_SW, OUTPUT);digitalWrite(BATT_SW, LOW); // BATT1 = low, BATT2 = high

}
// ---------------------------------------------------------------------------------------

// Lights ----------------------------------------------------------------------------------

Adafruit_DS3502 ds3502 = Adafruit_DS3502();

void init_lights(void){
  if (!ds3502.begin(0x28)){
    ds3502.begin(0x2B);
  }
}

void lights_on(uint8_t brightness) {
  digitalWrite(EN_10V, HIGH);
  delay(5);

  // Set wiper 
  uint8_t wiper_lvl = (brightness * 127) / 100; // Adjust brightness (0-100) to wiper range (0-127)
  ds3502.setWiper(wiper_lvl);
}

void lights_off(void) {
  // Turn off 14v boost
  digitalWrite(EN_10V, LOW);
  delay(5);
}

// ---------------------------------------------------------------------------------------


// RTC ------------------------------------------------------------------------------------

STM32RTC& rtc = STM32RTC::getInstance();

void init_rtc(){
  // Select RTC clock source: LSI_CLOCK, LSE_CLOCK or HSE_CLOCK.
  // By default the LSI is selected as source.
  rtc.setClockSource(STM32RTC::LSE_CLOCK);

  rtc.begin();   // the function to get the time from the RTC

  if (!rtc.isTimeSet()) {
    struct tm t;
    memset(&t, 0, sizeof(t));

    // Parse time: "hh:mm:ss"
    t.tm_hour = atoi(__TIME__);
    t.tm_min  = atoi(__TIME__ + 3);
    t.tm_sec  = atoi(__TIME__ + 6);

    // Parse date: "Mmm dd yyyy"
    char monthStr[4];
    int day, year;
    sscanf(__DATE__, "%s %d %d", monthStr, &day, &year);
    t.tm_mday = day;
    t.tm_year = year - 1900; // tm_year is years since 1900

    const char* months[] = {
      "Jan", "Feb", "Mar", "Apr", "May", "Jun",
      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
    };
    for (int i = 0; i < 12; ++i) {
      if (strncmp(monthStr, months[i], 3) == 0) {
      t.tm_mon = i; // tm_mon is 0-based
      break;
      }
    }

    rtc.setEpoch(mktime(&t));
  }

}

void read_rtc(){
  timestamp = rtc.getEpoch();
}
// ---------------------------------------------------------------------------------------

// RPi I2C ---------------------------------------------------------------------------------

#define I2C_ADDRESS 0x24

/*
# I2C register map:
# 
# Reg  | Type | Name                | Function                          | Number of Bytes
# ---- | ---- | ----                | ----                              | ----
# 0x01 | R    | RTC                 | RTC time data (Unix timestamp)    | 4 Bytes (32 bits) sent top byte to low byte in order 
# 0x02 | R    | RPi Volts           | --                                | 2 Byte (16 bits signed)  
# 0x03 | R    | RPi Current         | --                                | 2 Byte (16 bits signed)
# 0x04 | R    | RPi Power           | --                                | 2 Byte (16 bits signed)
# 0x05 | R    | uC Volts            | --                                | 2 Byte (16 bits signed)
# 0x06 | R    | uC Current          | --                                | 2 Byte (16 bits signed)
# 0x07 | R    | uC Power            | --                                | 2 Byte (16 bits signed)
# 0x08 | R    | Batt Volts          | --                                | 2 Byte (16 bits signed)
# 0x09 | R    | Batt Current        | --                                | 2 Byte (16 bits signed)
# 0x10 | R    | Batt Power          | --                                | 2 Byte (16 bits signed)
# 0x11 | W    | Acq config OUT      | Experimental configuration times  | 5 Bytes, duration (8 bits), interval (8 bits), frequency (16 bits), type (8 bits) 
# 0x12 | R    | Acq config IN       | Experimental configuration times  | 5 Bytes, duration (8 bits), interval (8 bits), frequency (16 bits), type (8 bits) 
# 0x13 | W    | Watchdog timer      | Time before power on RPi (mins)   | 2 Bytes (16 bits)
# 0x14 | R    | Poweroff timer      | Timer before power off RPi (secs) | 2 Bytes (16 bits)
*/

// Register definitions
#define REG_TIMESTAMP 0x01

#define REG_RPI_VOLTS 0x02
#define REG_RPI_CURRENT 0x03
#define REG_RPI_POWER 0x04

#define REG_UC_VOLTS 0x05
#define REG_UC_CURRENT 0x06
#define REG_UC_POWER 0x07

#define REG_BATT1_VOLTS 0x08
#define REG_BATT1_CURRENT 0x09
#define REG_BATT1_POWER 0x10

#define REG_BATT2_VOLTS 0x11
#define REG_BATT2_CURRENT 0x12
#define REG_BATT2_POWER 0x13

#define REG_ACQ_CONFIG_R 0x14
#define REG_ACQ_CONFIG_W 0x15

#define REG_WATCHDOG 0x16
#define REG_POWEROFF 0x17

#define REG_WTEMP 0x18
#define REG_WLIGHT 0x19

#define REG_DT_ADJUST 0x20

#define REG_LED_BRIGHTNESS 0x21

#define REG_LOG_TRANSFER 0x22
#define CHUNK_SIZE 32

volatile uint8_t register_address;
volatile bool is_register_address_received = false;

TwoWire Wire2(SDA2_SLAVE, SCL2_SLAVE);

// Functions for handling receive events ---------------------------

void reopenFile() {
  if (transferFile) transferFile.close();
  transferFile = SD.open(power_log_filename, FILE_READ);
  eofReached = false;

  fileSize = transferFile ? transferFile.size() : 0;

  if (transferFile) {
    file_transfer_active = true;
    printf("Successfully opened log file for transfer.");
  } else {
    printf("Unable to open log file for transfer.");
  }
}

void get_acq_config() {
  // Retrieve acquisition config from RPi
  // These variables are currently unused by the teensy but may be at a future date
  int bts = Wire2.available();
  if (bts < 5) return; // Incomplete config

  duration = Wire2.read();
  interval = (Wire2.read() << 8) | (Wire2.read() & 0xff);
  frequency = (Wire2.read() << 8) | (Wire2.read() & 0xff);
  type = Wire2.read();
  start_datetime = (Wire2.read() << 24) | (Wire2.read() << 16) | (Wire2.read() << 8) | (Wire2.read() & 0xff);    
}

void receive_event(int howMany) {
  if (howMany < 1) return; // Ignore empty transmissions

  while (Wire2.available()) {
    register_address = Wire2.read(); // Read the register address
    is_register_address_received = true;

    // Trigger different ISRs depending on the received address
    if (howMany > 1) {
      if (register_address == REG_ACQ_CONFIG_W) { 
        get_acq_config();
      } else if (register_address == REG_WATCHDOG){
        watchdog_time_config = (Wire2.read() << 24) | (Wire2.read() << 16) | (Wire2.read() << 8) | (Wire2.read() & 0xff);
      } else if (register_address == REG_POWEROFF){
        poweroff_time_config = (Wire2.read() << 8) | (Wire2.read() & 0xff);
      } else if (register_address == REG_DT_ADJUST) {
        uint32_t dt_adjust = (Wire2.read() << 24) | (Wire2.read() << 16) | (Wire2.read() << 8) | (Wire2.read() & 0xff);
        rtc.setEpoch(dt_adjust);
      } else if (register_address == REG_LED_BRIGHTNESS) {
        led_brightness = Wire2.read();
        printf("Received wiper brightness: %lu \n", led_brightness);
      } else if (register_address == REG_LOG_TRANSFER){
        uint8_t cmd = Wire2.read();
        if (cmd == 0x00) {
          reopenPending = true;
        }
      }
    }
  }
}

void send_uint_32bit(uint32_t data){
  Wire2.write((uint8_t)(data >> 24));
  Wire2.write((uint8_t)(data >> 16));
  Wire2.write((uint8_t)(data >> 8));
  Wire2.write((uint8_t)data);
}

// Functions for handling request events
void send_acq_config() {
  Wire2.write((uint8_t)duration); 
  Wire2.write((uint8_t)(interval >> 8)); 
  Wire2.write((uint8_t)(interval)); 
  Wire2.write((uint8_t)(frequency >> 8)); 
  Wire2.write((uint8_t)(frequency)); 
  Wire2.write((uint8_t)type);   
  send_uint_32bit(start_datetime);
}

void send_rtc() {
  send_uint_32bit(timestamp);
}

// Converts float to int, only works for 2 decimal places.
void send_float(float value) {
  int value_int = value * 100;
  Wire2.write((uint8_t)(value_int >> 8)); 
  Wire2.write((uint8_t)(value_int)); 
}

void transfer_request() {
  if (requestBusy) {
    uint8_t busy[CHUNK_SIZE];
    memset(busy, 0, CHUNK_SIZE);
    busy[0] = 0xFD; // busy marker
    Wire2.write(busy, CHUNK_SIZE);
    return;
  }
  requestBusy = true;

  uint8_t buffer[CHUNK_SIZE];
  memset(buffer, 0, CHUNK_SIZE);

  if (!sdReady) {
    buffer[0] = 0xFB;
    Wire2.write(buffer, CHUNK_SIZE);
    requestBusy = false;
    return;
  }

  if (!transferFile) {
    buffer[0] = 0xFC; // error marker (bad file handle)
    Wire2.write(buffer, CHUNK_SIZE);
    requestBusy = false;
    return;
  }

  if (eofReached) {
    buffer[0] = 0xFF;
    Wire2.write(buffer, CHUNK_SIZE);
    requestBusy = false;
    file_transfer_active = false;
    return;
  }

  uint32_t filePos  = transferFile.position();

  if (fileSize == 0 || filePos >= fileSize) {
    buffer[0] = 0xFF; // genuine EOF marker
    Wire2.write(buffer, CHUNK_SIZE);
    eofReached  = true;
    requestBusy = false;
    file_transfer_active = false;
    return;
  }

  size_t bytesToSend = transferFile.read(&buffer[1], CHUNK_SIZE - 1);

  if (bytesToSend == 0) {
    buffer[0] = 0xFD; // error marker (read failed)
    Wire2.write(buffer, CHUNK_SIZE);
    requestBusy = false;
    return;
  }

  buffer[0] = (uint8_t)bytesToSend;
  Wire2.write(buffer, CHUNK_SIZE);

  requestBusy = false;
}

// Function to handle outgoing data (to master)
void request_event() {
  if (!is_register_address_received) return; // No register address received

  switch (register_address) {
    case REG_LOG_TRANSFER:
      transfer_request();
      break;
    case REG_RPI_VOLTS:
      send_float(rpi_volts);
      break;
    case REG_RPI_CURRENT:
      send_float(rpi_current);
      break;
    case REG_RPI_POWER:
      send_float(rpi_power);
      break;
    case REG_UC_VOLTS:
      send_float(uc_volts);
      break;
    case REG_UC_CURRENT:
      send_float(uc_current);
      break;
    case REG_UC_POWER:
      send_float(uc_power);
      break;
    case REG_BATT1_VOLTS:
      send_float(batt1_volts);
      break;
    case REG_BATT1_CURRENT:
      send_float(batt1_current);
      break;
    case REG_BATT1_POWER:
      send_float(batt1_power);
      break;
    case REG_BATT2_VOLTS:
      send_float(batt2_volts);
      break;
    case REG_BATT2_CURRENT:
      send_float(batt2_current);
      break;
    case REG_BATT2_POWER:
      send_float(batt2_power);
      break;
    case REG_TIMESTAMP:
      send_rtc();
      break;    
    case REG_ACQ_CONFIG_R:
      send_acq_config();
      break;    
    case REG_WATCHDOG:      
      send_uint_32bit(watchdog_time_config);
        break;
    case REG_POWEROFF:      
        Wire2.write((uint8_t)(poweroff_time_config >> 8)); 
        Wire2.write((uint8_t)(poweroff_time_config));
        break;
    case REG_WTEMP:
      send_float(temp_celsius);
      break;
    case REG_WLIGHT:
      send_float(light_lux);
      break;    
  }
  is_register_address_received = false; // Reset for the next transaction
}

void configure_i2c(void) {
  // Initialize Wire2 (SDA2, SCL2)
  Wire2.begin(I2C_ADDRESS);
  Wire2.onReceive(receive_event);
  Wire2.onRequest(request_event);
}
// ---------------------------------------------------------------------------------------

// Power monitoring ----------------------------------------------------------------------

Adafruit_INA260 ina260_5v = Adafruit_INA260();
Adafruit_INA260 ina260_3v3 = Adafruit_INA260();
Adafruit_INA260 ina260_batt1 = Adafruit_INA260();
Adafruit_INA260 ina260_batt2 = Adafruit_INA260(); // Current unused

void init_power_mon(){
  ina260_3v3.begin(0x41);
  ina260_5v.begin(0x40);
  ina260_batt1.begin(0x45);
  ina260_batt2.begin(0x44);
}

void read_batt_volts(){
    ina260_batt1.setMode(INA260_MODE_CONTINUOUS);
    ina260_batt2.setMode(INA260_MODE_CONTINUOUS);
    delay(5);
    
    batt1_volts = ina260_batt1.readBusVoltage()/1000;
    batt2_volts = ina260_batt2.readBusVoltage()/1000;

    ina260_batt1.setMode(INA260_MODE_SHUTDOWN);
    ina260_batt2.setMode(INA260_MODE_SHUTDOWN);
    delay(5);
}

void read_power(){
    // Initiate before read
    ina260_batt1.setMode(INA260_MODE_CONTINUOUS);
    ina260_batt2.setMode(INA260_MODE_CONTINUOUS);
    ina260_3v3.setMode(INA260_MODE_CONTINUOUS);
    ina260_5v.setMode(INA260_MODE_CONTINUOUS);
    delay(5);

    rpi_current = ina260_5v.readCurrent()/1000;
    rpi_volts = ina260_5v.readBusVoltage()/1000;
    rpi_power = ina260_5v.readPower()/1000;

    uc_current = ina260_3v3.readCurrent()/1000;
    uc_volts = ina260_3v3.readBusVoltage()/1000;
    uc_power = ina260_3v3.readPower()/1000;

    batt1_current = ina260_batt1.readCurrent()/1000;
    batt1_volts = ina260_batt1.readBusVoltage()/1000;
    batt1_power = ina260_batt1.readPower()/1000;

    batt2_current = ina260_batt2.readCurrent()/1000;
    batt2_volts = ina260_batt2.readBusVoltage()/1000;
    batt2_power = ina260_batt2.readPower()/1000;

    // Shutdown when not in use
    ina260_batt1.setMode(INA260_MODE_SHUTDOWN);
    ina260_batt2.setMode(INA260_MODE_SHUTDOWN);
    ina260_3v3.setMode(INA260_MODE_SHUTDOWN);
    ina260_5v.setMode(INA260_MODE_SHUTDOWN);    
    delay(5);
}

// ---------------------------------------------------------------------------------------

// Main code -----------------------------------------------------------------------------

bool POWER_ON = false; // true if NTURN_ON received, false if NTURN_OFF received
bool RPI_POWER_ON = false;
int SWITCH_COUNT = 0;

extern "C" int _write(int file, char *ptr, int len) {
  // Send characters over SWO (ITM Port 0)
  for (int i = 0; i < len; i++) {
    ITM_SendChar(*ptr++);
  }
  return len;
}

void flash_led_builtin(int duration){
  digitalWrite(LED_BUILTIN, HIGH);
  delay(duration);
  digitalWrite(LED_BUILTIN, LOW);
}

void log_power() {
  log_file = SD.open(power_log_filename, FILE_WRITE);
  if (log_file) {
    log_file.print(timestamp);log_file.print(",");
    log_file.print(temp_celsius);log_file.print(",");
    log_file.print(light_lux);log_file.print(",");
    log_file.print(batt1_volts);log_file.print(",");
    log_file.print(batt1_current);log_file.print(",");
    log_file.print(batt1_power);log_file.print(",");
    log_file.print(batt2_volts);log_file.print(",");
    log_file.print(batt2_current);log_file.print(",");
    log_file.print(batt2_power);log_file.print(",");
    log_file.print(rpi_volts);log_file.print(",");
    log_file.print(rpi_current);log_file.print(",");
    log_file.print(rpi_power);log_file.print(",");
    log_file.print(uc_volts);log_file.print(",");
    log_file.print(uc_current);log_file.print(",");
    log_file.print(uc_power);log_file.println();
    log_file.close();
    printf("Logged data to file.");
  } else {
    printf("Error opening log file.");
  }
  log_file.close();
}

bool check_and_switch_power(void){
  bool switch_on = false; // Assume unable to power up, and only power up if valid power inputs
  
  read_batt_volts(); // Update global batt volt measures

  bool batt1_ok = batt1_volts > 2.00f;
  bool batt2_ok = batt2_volts > 2.00f;
  
  printf("Batt1: %d, Batt2: %d, Power_src: %d\n", 
         batt1_ok, batt2_ok, current_power_src);

  if ((!batt1_ok) && (!batt2_ok)){
    switch_on = false;
    current_power_src = -1;
  } else {
    if ((batt1_volts < 0.50f) && (batt2_ok)){ // Do not toggle BATT_SW if no batt1 but there is batt2
      switch_on = true;
      current_power_src = 2;
    } else {
      if (current_power_src == -1){ // Initialise logic
        if (batt1_ok){
          digitalWrite(BATT_SW, LOW);
          switch_on = true;
          current_power_src = 1;
        } else if (batt2_ok) {
          digitalWrite(BATT_SW, HIGH);
          switch_on = true;
          current_power_src = 2;
        }
      }

      if (current_power_src == 1){
        if (!batt1_ok){
          if (batt2_ok){ // Switch to batt2 if batt1 too low
            digitalWrite(BATT_SW, HIGH);
            switch_on = true;
            current_power_src = 2;
          }
        } else {
          switch_on = true; // Stay on batt1 if ok
        }
      } else if (current_power_src == 2){
        if (!batt2_ok){
          if (batt1_ok){ // Only switch back if batt2 drops too low
            digitalWrite(BATT_SW, LOW);
            switch_on = true;
            current_power_src = 1;
          }
        } else {
          switch_on = true; // Stay on batt2 if ok
        }
      }
    }
  }

  return switch_on;
}

// These ISRs do not have any logic to behave differently if the system is already on
// or off. This is intentional to enable an end-user to power on/off a system
// in the unlikely event that there is a fault in the RPi operation. 
void turn_on(void){
  if (POWER_CHECK) {
    printf("Received turn on request...");

    digitalWrite(EN_5V, HIGH);

    POWER_ON = true;
    RPI_POWER_ON = true;
  }
}

void turn_off(void){
  printf("Received turn off request...");

  digitalWrite(EN_5V, LOW);

  RPI_POWER_ON = false;
  POWER_ON = false;  
}

void setup() {
  // Enable tracing on Cortex-M4 (ITM needs TRCENA set)
  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;

  // Optional: turn on ITM Stimulus Port 0
  ITM->TCR = ITM_TCR_ITMENA_Msk      // Enable ITM
           | ITM_TCR_SYNCENA_Msk     // Enable sync packets
           | ITM_TCR_TSENA_Msk       // Enable timestamp packets
           | ITM_TCR_SWOENA_Msk;     // Enable SWO output

  ITM->TER |= (1UL << 0); // Enable Stimulus Port 0

  Wire.begin();

  LowPower.begin();

  configureGPIO();

  // Begin various devices
  init_power_mon();
  init_rtc();
  init_lights();
  init_light_sensor();
  init_temp_sensor();

  // Attach external switch interrupts
  attachInterrupt(digitalPinToInterrupt(TURN_ON_OFF),*turn_on, RISING); 

  // I2C for RPi communication
  configure_i2c();

  bool sdInitialized = SD.begin(SD_CS);

  if (!sdInitialized) {
    printf("initialization failed.\n");
    return;
  } else {
    printf("Wiring is correct and a card is present.\n");
    sdReady = true;
  }

  // // Check if file exists, and create it
  if (!SD.exists(power_log_filename)) {
    log_file = SD.open(power_log_filename, FILE_WRITE);
    if (log_file) {
        log_file.println("unix_timestamp,temp_celsius,light_lux,batt1_volts,batt1_current,batt1_power,batt2_volts,batt2_current,batt2_power,rpi_volts,rpi_current,rpi_power,uc_volts,uc_current,uc_power");
        log_file.close();
    }
    log_file.close();
  }
}

void loop() {
  // Update readouts
  read_power();
  read_rtc();
  read_light_lux();
  read_temp();

  POWER_CHECK = check_and_switch_power();

  printf("Timestamp: %lu, Watchdog time: %lu, Poweroff time: %lu\n", 
         timestamp, watchdog_end_time, poweroff_end_time);

  printf("ON/OFF switch state: %d, RPI POWER ON: %d, Charge check: %d\n", 
         digitalRead(TURN_ON_OFF), RPI_POWER_ON, POWER_CHECK);

  printf("Batt1: %ld mV, Batt2: %ld mV\n",
        (long)(batt1_volts * 1000.0f),
        (long)(batt2_volts * 1000.0f));

  if (reopenPending && !requestBusy) {
      reopenPending = false;
      reopenFile();
  }

  if (eofReached && transferFile) {
      transferFile.close();
      file_transfer_active = false;
  }

  // If a watchdog timer has been received from RPi
  if ((watchdog_time_config > 0) && (watchdog_end_time == 0)) {
      watchdog_end_time = watchdog_time_config;
  } else if ((watchdog_time_config == 0) && (watchdog_end_time != 0)) {
      watchdog_end_time = 0;
  }

  // If a power-off timer has been received from RPi
  if ((poweroff_time_config > 0) && (poweroff_end_time == 0)) {
      poweroff_end_time = timestamp + poweroff_time_config;
  } else if ((poweroff_time_config == 0) && (poweroff_end_time != 0)) {
      poweroff_end_time = 0;
  }

  // Somewhat janky periodic check to turn on/off external LEDs
  // Would be better as an interrupt
  if (digitalRead(RPI_GPIO22) == HIGH) {
    lights_on(led_brightness);  
  } else {
    lights_off();
  }

  // If watchdog timer has finished, power on RPi
  if ((timestamp >= watchdog_end_time) && (watchdog_end_time > 0)) {
    if (POWER_CHECK) {
      printf("Turning RPI on...");        
      digitalWrite(EN_5V, HIGH);
      RPI_POWER_ON = true;
    }
    watchdog_time_config = 0;
    watchdog_end_time = 0;
  }

  // If power-off timer has passed, power off RPi
  if ((timestamp >= poweroff_end_time) && (poweroff_end_time > 0)) {
      printf("Turning RPI off...");        
      digitalWrite(EN_5V, LOW);
      RPI_POWER_ON = false;
      poweroff_time_config = 0;
      poweroff_end_time = 0;
  }

  if (file_transfer_active == false) {
    if (log_file_start == false) {
      log_power();
      log_file_start = true;
    }

    if (log_file_counter == log_file_counter_interval) {
      log_power();
      log_file_counter = 0;
    }

    log_file_counter += 1;
  }

  if (POWER_ON == true) {
    int on_off_switch_state = digitalRead(TURN_ON_OFF);

    if (on_off_switch_state == HIGH) {
      SWITCH_COUNT = SWITCH_COUNT + 1;
    } else {
      SWITCH_COUNT = 0; // If switch not active, reset counter
    }
  }

  if (SWITCH_COUNT > 5) {
    turn_off();
    SWITCH_COUNT = 0;
  }

  // Power down to prevent over discharge
  if (POWER_CHECK == false){
    turn_off();
  }
  
  // flash_led_builtin(50);
  // delay(1000);

  // Check which batt is being used and flash corresponding led
  int batt_stat = digitalRead(BATT_ST);
  if (batt_stat == HIGH){
    digitalWrite(BATT2_LED, HIGH);
    delay(50);
    digitalWrite(BATT2_LED, LOW);
  } else {
    digitalWrite(BATT1_LED, HIGH);
    delay(50);
    digitalWrite(BATT1_LED, LOW);
  }


  if (RPI_POWER_ON == false) {
    SLEEP_ACTIVE = true;
    flash_led_builtin(50);
    // delay(1000);
    LowPower.deepSleep(10000);
  } else {
    flash_led_builtin(50);
    delay(1000);
  }
}

