from typing import Dict
from fastapi import WebSocket


class ConnectionManager:
    """Держит до двух активных WebSocket-соединений на комнату (couple_id).

    room[couple_id] = { user_id: WebSocket }
    """

    def __init__(self):
        self.rooms: Dict[str, Dict[str, WebSocket]] = {}

    async def connect(self, couple_id: str, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
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


manager = ConnectionManager()
