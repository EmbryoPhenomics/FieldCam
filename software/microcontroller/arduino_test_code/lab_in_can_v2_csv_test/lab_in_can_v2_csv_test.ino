#include <Wire.h>
#include <SD.h>
#include <SPI.h>

#define I2C_ADDR 0x24
#define CHUNK_SIZE 32

#define LED_BUILTIN PA0
#define EN_5V PB13
#define SDA2_SLAVE PB11
#define SCL2_SLAVE PB10

#define SD_CS_PIN PA5  // Adjust for your board

TwoWire Wire2(SDA2_SLAVE, SCL2_SLAVE);

File csvFile;
bool sdReady = false;
bool eofReached = false;

void reopenFile() {
  if (csvFile) csvFile.close();
  csvFile = SD.open("log4.txt", FILE_READ);
  eofReached = false;
}

void onRequest() {
  uint8_t buffer[CHUNK_SIZE];
  memset(buffer, 0, CHUNK_SIZE);

  if (!sdReady) {
    buffer[0] = 0xFE; // error marker (no SD)
    Wire2.write(buffer, CHUNK_SIZE);
    return;
  }

  if (eofReached || !csvFile.available()) {
    buffer[0] = 0xFF; // EOF marker
    Wire2.write(buffer, CHUNK_SIZE);
    eofReached = true;
    return;
  }

  // Read next block from SD
  size_t bytesToSend = csvFile.read(&buffer[1], CHUNK_SIZE - 1);
  if (bytesToSend == 0) {
    buffer[0] = 0xFF;
    Wire2.write(buffer, CHUNK_SIZE);
    eofReached = true;
    return;
  }

  buffer[0] = bytesToSend;
  Wire2.write(buffer, CHUNK_SIZE);
}

void onReceive(int numBytes) {
  static bool first = true;
  while (Wire2.available()) {
    uint8_t cmd = Wire2.read();
    if (cmd == 0x00) {
      reopenFile();   // reset file pointer
      first = false;
    }
  }
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  pinMode(EN_5V, OUTPUT);
  digitalWrite(EN_5V, HIGH);

  Wire2.begin(I2C_ADDR);
  Wire2.onRequest(onRequest);
  Wire2.onReceive(onReceive);

  if (!SD.begin(SD_CS_PIN)) {
    sdReady = false;
  } else {
    sdReady = true;
    reopenFile();
  }
}

void loop() {
  digitalWrite(LED_BUILTIN, HIGH);
  delay(1000);
  digitalWrite(LED_BUILTIN, LOW);
  delay(1000);
}
