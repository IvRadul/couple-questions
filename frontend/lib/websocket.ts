import { API_BASE_URL, getToken } from "./auth";
import type { WsClientMessage, WsServerMessage } from "@/types";

/**
 * Открывает WebSocket-соединение с /ws/{couple_id}?token=...
 * и вызывает onMessage для каждого входящего JSON-сообщения.
 * Возвращает объект с методом send() и close().
 */
export function connectGameSocket(
  coupleId: string,
  onMessage: (msg: WsServerMessage) => void,
  onStatusChange?: (status: "connecting" | "open" | "closed") => void
) {
  const token = getToken();
  const wsBase = API_BASE_URL.replace(/^http/, "ws");
  const socket = new WebSocket(`${wsBase}/ws/${coupleId}?token=${encodeURIComponent(token || "")}`);

  onStatusChange?.("connecting");

  socket.onopen = () => onStatusChange?.("open");
  socket.onclose = () => onStatusChange?.("closed");
  socket.onerror = () => onStatusChange?.("closed");

  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data) as WsServerMessage;
      onMessage(data);
    } catch (e) {
      console.error("Не удалось разобрать сообщение WebSocket", e);
    }
  };

  return {
    send(message: WsClientMessage) {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(message));
      }
    },
    close() {
      socket.close();
    },
  };
}
