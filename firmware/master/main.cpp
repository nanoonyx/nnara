#include <WiFi.h>
#include <PubSubClient.h>
#include <esp_now.h>
#include <ArduinoJson.h>

// --- Configuration ---
const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";
const char* mqtt_server = "192.168.1.10"; // Default RPi IP

WiFiClient espClient;
PubSubClient client(espClient);

// --- ESP-NOW Configuration ---
uint8_t slaveAddress[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF}; // Broadcast for simplicity, or specific

typedef struct struct_message {
    char type[10];
    char id[20];
    char cmd[50];
} struct_message;

struct_message myData;

// --- MQTT Callbacks ---
void callback(char* topic, byte* payload, unsigned int length) {
    StaticJsonDocument<256> doc;
    deserializeJson(doc, payload, length);

    const char* target = doc["target"];
    const char* id = doc["id"];
    const char* cmd = doc["cmd"];

    Serial.print("Received MQTT [");
    Serial.print(topic);
    Serial.print("] Target: ");
    Serial.println(target);

    // Prepare ESP-NOW message
    strncpy(myData.type, target, sizeof(myData.type));
    strncpy(myData.id, id, sizeof(myData.id));
    strncpy(myData.cmd, cmd, sizeof(myData.cmd));

    // Send via ESP-NOW
    esp_err_t result = esp_now_send(slaveAddress, (uint8_t *) &myData, sizeof(myData));
    
    if (result == ESP_OK) {
        Serial.println("Sent with success");
    } else {
        Serial.println("Error sending the data");
    }
}

void reconnect() {
    while (!client.connected()) {
        Serial.print("Attempting MQTT connection...");
        String clientId = "NaraMaster-";
        clientId += String(random(0xffff), HEX);
        if (client.connect(clientId.c_str())) {
            Serial.println("connected");
            client.subscribe("nara/cmd");
            client.subscribe("nara/master/global");
            client.subscribe("nara/group/#");
            client.subscribe("nara/slave/+/in");
        } else {
            Serial.print("failed, rc=");
            Serial.print(client.state());
            Serial.println(" try again in 5 seconds");
            delay(5000);
        }
    }
}

void setup() {
    Serial.begin(115200);

    // WiFi
    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println("\nWiFi connected");

    // MQTT
    client.setServer(mqtt_server, 1883);
    client.setCallback(callback);

    // ESP-NOW
    WiFi.mode(WIFI_STA);
    if (esp_now_init() != ESP_OK) {
        Serial.println("Error initializing ESP-NOW");
        return;
    }

    esp_now_peer_info_t peerInfo;
    memcpy(peerInfo.peer_addr, slaveAddress, 6);
    peerInfo.channel = 0;  
    peerInfo.encrypt = false;
    
    if (esp_now_add_peer(&peerInfo) != ESP_OK) {
        Serial.println("Failed to add peer");
        return;
    }
}

void loop() {
    if (!client.connected()) {
        reconnect();
    }
    client.loop();

    // Periodic status report
    static unsigned long lastReport = 0;
    if (millis() - lastReport > 30000) {
        lastReport = millis();
        StaticJsonDocument<128> status;
        status["msg"] = "Master Online";
        status["rssi"] = WiFi.RSSI();
        char buffer[128];
        serializeJson(status, buffer);
        client.publish("nara/master/status", buffer);
    }
}
