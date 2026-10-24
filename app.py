import json
import math
import os
import secrets
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

app = FastAPI(title="Treasure Hunt Multiplayer")
ROOMS = {}
ROOM_CAPACITIES = {"solo": 1, "duo": 2, "squad": 4}
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
COIN_REWARDS = {0: 34, 4: 48, 6: 27}
KEY_CHEST_INDEX = 5
DRAWER_COUNT = 5
ALLOWED_ORIGINS = {
    origin.strip()
    for origin in os.environ.get(
        "ALLOWED_ORIGINS",
        "https://cassyy1212.github.io,http://localhost:8000,http://127.0.0.1:8000",
    ).split(",")
    if origin.strip()
}


def create_code():
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
        if code not in ROOMS:
            return code


def public_player(player):
    return {
        "id": player["id"],
        "name": player["name"],
        "x": player["x"],
        "y": player["y"],
        "angle": player["angle"],
        "hidden": player["hidden"],
    }


async def send_error(socket, message):
    await socket.send_json({"type": "error", "message": message})


async def broadcast(room, message):
    disconnected = []
    for player_id, socket in list(room["sockets"].items()):
        try:
            await socket.send_json(message)
        except (RuntimeError, WebSocketDisconnect):
            disconnected.append(player_id)
    for player_id in disconnected:
        room["sockets"].pop(player_id, None)
        room["players"].pop(player_id, None)


def remove_player(code, player_id):
    room = ROOMS.get(code)
    if room is None:
        return None
    room["players"].pop(player_id, None)
    room["sockets"].pop(player_id, None)
    if not room["players"]:
        ROOMS.pop(code, None)
        return None
    return room


async def apply_world_event(room, player_id, event_type, index):
    if event_type == "chest":
        opened = room["world"]["openedChests"]
        if index < 0 or index >= 7 or index in opened:
            return
        opened.add(index)
        event = {
            "type": "world_event",
            "eventType": "chest",
            "index": index,
            "actorId": player_id,
            "reward": COIN_REWARDS.get(index, 0),
            "hasKey": index == KEY_CHEST_INDEX,
        }
        room["world"]["hasKey"] = room["world"]["hasKey"] or event["hasKey"]
    elif event_type == "drawer":
        searched = room["world"]["searchedDrawers"]
        if index < 0 or index >= DRAWER_COUNT or index in searched:
            return
        searched.add(index)
        event = {
            "type": "world_event",
            "eventType": "drawer",
            "index": index,
            "actorId": player_id,
        }
    else:
        return
    await broadcast(room, event)


@app.get("/")
async def root():
    return JSONResponse({"service": "Treasure Hunt Multiplayer", "websocket": "/ws"})


@app.get("/health")
async def health():
    return {"status": "ok", "activeRooms": len(ROOMS)}


@app.websocket("/ws")
async def multiplayer_socket(socket: WebSocket):
    origin = socket.headers.get("origin", "")
    if origin and origin not in ALLOWED_ORIGINS:
        await socket.close(code=1008, reason="Origin not allowed")
        return

    await socket.accept()
    room_code = None
    player_id = None
    try:
        while True:
            raw = await socket.receive_text()
            if len(raw) > 4096:
                await send_error(socket, "Message is too large.")
                continue
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await send_error(socket, "Invalid message.")
                continue
            if not isinstance(message, dict):
                await send_error(socket, "Invalid message.")
                continue

            message_type = message.get("type")
            if player_id is None:
                if message_type == "create":
                    mode = message.get("mode")
                    if not isinstance(mode, str) or mode not in ROOM_CAPACITIES:
                        await send_error(socket, "Choose Solo, Duo, or Squad.")
                        continue
                    room_code = create_code()
                    player_id = uuid.uuid4().hex
                    player = {
                        "id": player_id,
                        "name": f"Explorer-{secrets.randbelow(900) + 100}",
                        "x": 3.3,
                        "y": 5.5,
                        "angle": 0.0,
                        "hidden": False,
                    }
                    room = {
                        "mode": mode,
                        "capacity": ROOM_CAPACITIES[mode],
                        "hostId": player_id,
                        "started": False,
                        "players": {player_id: player},
                        "sockets": {player_id: socket},
                        "world": {
                            "openedChests": set(),
                            "searchedDrawers": set(),
                            "hasKey": False,
                            "completed": False,
                        },
                    }
                    ROOMS[room_code] = room
                    await socket.send_json({
                        "type": "lobby_created",
                        "id": player_id,
                        "name": player["name"],
                        "code": room_code,
                        "mode": mode,
                        "started": False,
                        "players": [],
                        "world": {
                            "openedChests": [],
                            "searchedDrawers": [],
                            "hasKey": False,
                        },
                    })
                    continue
                if message_type == "join":
                    room_code = str(message.get("code", "")).strip().upper()
                    room = ROOMS.get(room_code)
                    if room is None:
                        await send_error(socket, "No active lobby was found for that code.")
                        room_code = None
                        continue
                    if len(room["players"]) >= room["capacity"]:
                        await send_error(socket, "That lobby is full.")
                        room_code = None
                        continue
                    player_id = uuid.uuid4().hex
                    player = {
                        "id": player_id,
                        "name": f"Explorer-{secrets.randbelow(900) + 100}",
                        "x": 3.3,
                        "y": 5.5,
                        "angle": 0.0,
                        "hidden": False,
                    }
                    existing_players = [
                        public_player(existing)
                        for existing in room["players"].values()
                    ]
                    room["players"][player_id] = player
                    room["sockets"][player_id] = socket
                    await socket.send_json({
                        "type": "joined",
                        "id": player_id,
                        "name": player["name"],
                        "code": room_code,
                        "mode": room["mode"],
                        "started": room["started"],
                        "players": existing_players,
                        "world": {
                            "openedChests": sorted(room["world"]["openedChests"]),
                            "searchedDrawers": sorted(room["world"]["searchedDrawers"]),
                            "hasKey": room["world"]["hasKey"],
                        },
                    })
                    await broadcast(room, {
                        "type": "player_joined",
                        "player": public_player(player),
                    })
                    continue
                await send_error(socket, "Create a lobby or join with a code first.")
                continue

            room = ROOMS.get(room_code)
            if room is None or player_id not in room["players"]:
                await send_error(socket, "This lobby is no longer active.")
                break

            if message_type == "move":
                x = message.get("x")
                y = message.get("y")
                angle = message.get("angle")
                if not all(
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and math.isfinite(value)
                    for value in (x, y, angle)
                ):
                    continue
                player = room["players"][player_id]
                player.update({
                    "x": max(0.0, min(26.0, float(x))),
                    "y": max(0.0, min(26.0, float(y))),
                    "angle": float(angle) % (2 * math.pi),
                    "hidden": bool(message.get("hidden", False)),
                })
                await broadcast(room, {
                    "type": "player_state",
                    "player": public_player(player),
                })
            elif message_type == "configure":
                mode = message.get("mode")
                if player_id != room["hostId"] or room["started"]:
                    await send_error(socket, "Only the host can change an unstarted lobby.")
                    continue
                if not isinstance(mode, str) or mode not in ROOM_CAPACITIES:
                    await send_error(socket, "Choose Solo, Duo, or Squad.")
                    continue
                if len(room["players"]) > 1:
                    await send_error(socket, "Team size cannot change after another player joins.")
                    continue
                room["mode"] = mode
                room["capacity"] = ROOM_CAPACITIES[mode]
                await socket.send_json({"type": "lobby_configured", "mode": mode})
            elif message_type == "start":
                if player_id != room["hostId"]:
                    await send_error(socket, "Only the host can start this lobby.")
                    continue
                room["started"] = True
                await broadcast(room, {
                    "type": "game_started",
                    "mode": room["mode"],
                    "players": [public_player(player) for player in room["players"].values()],
                    "world": {
                        "openedChests": sorted(room["world"]["openedChests"]),
                        "searchedDrawers": sorted(room["world"]["searchedDrawers"]),
                        "hasKey": room["world"]["hasKey"],
                    },
                })
            elif message_type == "finish":
                if not room["world"]["hasKey"] or room["world"]["completed"]:
                    continue
                room["world"]["completed"] = True
                await broadcast(room, {"type": "game_finished"})
            elif message_type == "chat":
                text = message.get("text")
                if not isinstance(text, str):
                    continue
                text = text.strip()[:160]
                if text:
                    await broadcast(room, {
                        "type": "chat",
                        "id": player_id,
                        "name": room["players"][player_id]["name"],
                        "text": text,
                    })
            elif message_type == "interact":
                event_type = message.get("target")
                index = message.get("index")
                if event_type not in ("chest", "drawer") or not isinstance(index, int) or isinstance(index, bool):
                    continue
                await apply_world_event(room, player_id, event_type, index)
            elif message_type == "leave":
                break
    except WebSocketDisconnect:
        pass
    finally:
        if room_code and player_id:
            room = remove_player(room_code, player_id)
            if room is not None:
                await broadcast(room, {"type": "player_left", "id": player_id})
