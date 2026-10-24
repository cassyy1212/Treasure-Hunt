# Treasure Hunt

A browser-based cave-horror exploration game. Play it at
https://cassyy1212.github.io/Treasure-Hunt/ or download the standalone HTML at
https://cassyy1212.github.io/Treasure-Hunt/treasure-hunt.html.

## Online private lobbies

The static game is playable without a server. Private lobby codes, shared
players, chat, and shared loot require the multiplayer service in `app.py` to
be deployed. The Render Blueprint in `render.yaml` uses the repository root
and expects a service named `treasure-hunt-multiplayer`; the game connects to
that service's `/ws` endpoint. Its default allowed origin is the GitHub Pages
site.

Select Solo, Duo, Trio, or Squad when creating a private lobby, share the
generated code, and have players join before the host confirms the game.
Random public matchmaking is not connected yet.

Lobby and game state is held in memory, so service restarts or sleep can clear
rooms. The server is not authoritative for movement or monster behavior.
