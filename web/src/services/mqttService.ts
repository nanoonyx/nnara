import mqtt from "mqtt";

export interface MqttConfig {
    host: string;
    port: number;
    protocol: "ws" | "wss";
    clientId: string;
}

export class MqttService {
    private client: mqtt.MqttClient | null = null;
    private onMessageCallback: ((topic: string, message: string) => void) | null = null;

    connect(config: MqttConfig, onConnect?: () => void) {
        if (this.client) this.client.end();

        const { host, port, protocol, clientId } = config;
        const url = `${protocol}://${host}:${port}/mqtt`;

        this.client = mqtt.connect(url, {
            clientId,
            clean: true,
            connectTimeout: 4000,
            reconnectPeriod: 1000,
        });

        this.client.on("connect", () => {
            console.log("MQTT Connected");
            if (onConnect) onConnect();
        });

        this.client.on("message", (topic, payload) => {
            if (this.onMessageCallback) {
                this.onMessageCallback(topic, payload.toString());
            }
        });

        this.client.on("error", (err) => {
            console.error("MQTT Error:", err);
        });
    }

    subscribe(topic: string) {
        if (this.client) {
            this.client.subscribe(topic);
        }
    }

    publish(topic: string, message: string) {
        if (this.client) {
            this.client.publish(topic, message);
        }
    }

    onMessage(callback: (topic: string, message: string) => void) {
        this.onMessageCallback = callback;
    }

    disconnect() {
        if (this.client) {
            this.client.end();
            this.client = null;
        }
    }
}

export const mqttService = new MqttService();
