/**
 * WebSocket service for connecting to Elora backend
 */

import { WS_URL, wsUrl } from "../config";

const DEFAULT_URL = WS_URL;

type MessageHandler = (message: any) => void;
type StatusHandler = (status: "connected" | "disconnected" | "error") => void;

class EloraWebSocket {
  private ws: WebSocket | null = null;
  private url: string;
  private userId: string;
  private token: string | null;
  private onMessage: MessageHandler | null = null;
  private onStatusChange: StatusHandler | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    baseUrl: string = DEFAULT_URL,
    userId: string = "user-1",
    token: string | null = null,
  ) {
    this.url = wsUrl(baseUrl, userId, token);
    this.userId = userId;
    this.token = token;
  }

  connect(onMessage: MessageHandler, onStatusChange: StatusHandler) {
    this.onMessage = onMessage;
    this.onStatusChange = onStatusChange;

    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        console.log("[WS] Connected to Elora backend");
        this.onStatusChange?.("connected");
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.onMessage?.(data);
        } catch (e) {
          console.error("[WS] Parse error:", e);
        }
      };

      this.ws.onerror = (error) => {
        console.error("[WS] Error:", error);
        this.onStatusChange?.("error");
      };

      this.ws.onclose = () => {
        console.log("[WS] Disconnected");
        this.onStatusChange?.("disconnected");
        // Auto-reconnect after 3 seconds
        this.reconnectTimer = setTimeout(() => this.connect(onMessage, onStatusChange), 3000);
      };
    } catch (e) {
      console.error("[WS] Connection failed:", e);
      this.onStatusChange?.("error");
    }
  }

  sendText(text: string) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "text", content: text }));
    }
  }

  sendAudio(base64Audio: string) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "audio", content: base64Audio }));
    }
  }

  sendImage(base64Image: string) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "image", content: base64Image }));
    }
  }

  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }
    this.ws?.close();
    this.ws = null;
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

export default EloraWebSocket;
