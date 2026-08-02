from typing import Dict, Optional
from fastapi import WebSocket


class ConnectionManager:
    """Держит до двух активных WebSocket-соединений на комнату (couple_id),
    а также не более одного "ожидающего ответа" приглашения сыграть раунд
    с конкретным паком (pending round request) на комнату.

    room[couple_id] = { user_id: WebSocket }
    pending_requests[couple_id] = {"pack_id": int, "requested_by_id": str}
    """

    def __init__(self):
        self.rooms: Dict[str, Dict[str, WebSocket]] = {}
        self.pending_requests: Dict[str, dict] = {}

    async def connect(self, couple_id: str, user_id: str, websocket: WebSocket) -> None:
        # Приём (accept) уже сделан вызывающим кодом (websocket_endpoint) —
        # это нужно, чтобы клиент/nginx всегда видели корректный HTTP 101
        # хендшейк, даже если соединение потом сразу же закрывается из-за
        # невалидного токена/пары (иначе некоторые связки nginx+ASGI отдают
        # такой обрыв как 502, а не как понятную ошибку).
        self.rooms.setdefault(couple_id, {})
        self.rooms[couple_id][user_id] = websocket

    def disconnect(self, couple_id: str, user_id: str) -> None:
        room = self.rooms.get(couple_id)
        if room and user_id in room:
            del room[user_id]
        if room is not None and not room:
            del self.rooms[couple_id]

    async def send_to_user(self, couple_id: str, user_id: str, message: dict) -> None:
        room = self.rooms.get(couple_id, {})
        ws = room.get(user_id)
        if ws is not None:
            await ws.send_json(message)

    async def broadcast_to_couple(self, couple_id: str, message: dict) -> None:
        room = self.rooms.get(couple_id, {})
        for ws in list(room.values()):
            await ws.send_json(message)

    # ---------- Ожидающие приглашения на раунд с выбранным паком ----------

    def set_pending_request(self, couple_id: str, pack_id: int, requested_by_id: str) -> None:
        self.pending_requests[couple_id] = {"pack_id": pack_id, "requested_by_id": requested_by_id}

    def get_pending_request(self, couple_id: str) -> Optional[dict]:
        return self.pending_requests.get(couple_id)

    def clear_pending_request(self, couple_id: str) -> None:
        self.pending_requests.pop(couple_id, None)


manager = ConnectionManager()
