#include <esp_now.h>
#include <WiFi.h>
#include <NimBLEDevice.h>

// --- Configuration ---
const char* SLAVE_ID = "S1"; 

// --- Data Structure ---
typedef struct struct_message {
    char type[10];
    char id[20];
    char cmd[50];
} struct_message;

struct_message incomingData;

// --- BLE Configuration ---
NimBLEClient* pClient = nullptr;
static NimBLEUUID serviceUUID("EB70"); // Example Service UUID
static NimBLEUUID charUUID("EB71");    // Example Characteristic UUID

bool sendBLECommand(const char* mac, const char* cmd) {
    NimBLEAddress addr(mac);
    pClient = NimBLEDevice::createClient();

    Serial.printf("Connecting to %s...\n", mac);
    if (!pClient->connect(addr)) {
        NimBLEDevice::deleteClient(pClient);
        return false;
    }

    NimBLERemoteService* pService = pClient->getService(serviceUUID);
    if (pService) {
        NimBLERemoteCharacteristic* pChar = pService->getCharacteristic(charUUID);
        if (pChar && pChar->canWrite()) {
            pChar->writeValue(cmd, strlen(cmd), true);
            Serial.println("BLE Write Success");
            pClient->disconnect();
            NimBLEDevice::deleteClient(pClient);
            return true;
        }
    }

    pClient->disconnect();
    NimBLEDevice::deleteClient(pClient);
    return false;
}

// --- ESP-NOW Callback ---
void OnDataRecv(const uint8_t * mac, const uint8_t *incomingBytes, int len) {
    memcpy(&incomingData, incomingBytes, sizeof(incomingData));
    
    Serial.print("Bytes received: ");
    Serial.println(len);
    Serial.print("Target: ");
    Serial.println(incomingData.type);

    // Logic for this Slave
    if (strcmp(incomingData.type, "Global") == 0 || strcmp(incomingData.id, SLAVE_ID) == 0) {
        Serial.printf("Executing command: %s\n", incomingData.cmd);
        
        // 3-Retry Logic
        bool success = false;
        for (int i = 0; i < 3; i++) {
            // In a real scenario, we'd lookup the BLE MAC from CID
            // For now, we simulate execution
            Serial.printf("Retry %d...\n", i+1);
            delay(100); 
            success = true; // Simulating success
            if (success) break;
        }

        // Ideally, send ACK back to Master via ESP-NOW
    }
}

void setup() {
    Serial.begin(115200);

    WiFi.mode(WIFI_STA);
    if (esp_now_init() != ESP_OK) {
        Serial.println("Error initializing ESP-NOW");
        return;
    }

    esp_now_register_recv_cb(OnDataRecv);
    
    NimBLEDevice::init("");
    Serial.println("Slave Ready");
}

void loop() {
    // Slave specific background tasks (Battery monitoring, etc.)
}
