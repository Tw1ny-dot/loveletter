import socket
import threading
import json
import random

HOST = '0.0.0.0'
PORT = 12345

game_state = {
    "players": {},
    "turn": 0,
    "started": False,
    "deck": [],
    "eliminated": set(),
    "history": []
}

CARD_COUNTS = {
    "Garde": 5, "Pretre": 2, "Baron": 2, "Servante": 2,
    "Prince": 2, "Roi": 1, "Comtesse": 1, "Princesse": 1
}
CARD_VALUES = {
    "Garde": 1, "Pretre": 2, "Baron": 3, "Servante": 4,
    "Prince": 5, "Roi": 6, "Comtesse": 7, "Princesse": 8
}

MIN_PLAYERS = 2
MAX_PLAYERS = 4

def create_deck():
    deck = []
    for name, count in CARD_COUNTS.items():
        deck.extend([name] * count)
    random.shuffle(deck)
    return deck

def handle_client(conn, addr):
    print(f"[Connexion] depuis {addr}")
    buffer = ""
    name = None

    while True:
        data = conn.recv(4096)
        if not data:
            return
        buffer += data.decode()
        if '\n' in buffer:
            line, buffer = buffer.split('\n', 1)
            msg = json.loads(line.strip())
            if msg.get("type") == "name":
                name = msg["name"]
                break

    player_id = len(game_state["players"])
    game_state["players"][player_id] = {
        "name": name,
        "conn": conn,
        "hand": [],
        "protected": False,
        "ready": False
    }
    broadcast({"type": "info", "content": f"{name} a rejoint la partie."})

    try:
        while True:
            while '\n' not in buffer:
                data = conn.recv(4096)
                if not data:
                    return
                buffer += data.decode()

            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                if not line.strip():
                    continue
                msg = json.loads(line.strip())
                if msg["type"] == "ready":
                    game_state["players"][player_id]["ready"] = True
                    broadcast({"type": "info", "content": f"{name} est prêt."})
                    if should_start_game():
                        threading.Thread(target=start_game).start()
                elif msg["type"] == "play":
                    process_turn(player_id, msg)

    except Exception as e:
        print(f"[Erreur] {e}")
    finally:
        conn.close()

def should_start_game():
    players = list(game_state["players"].values())
    ready = [p for p in players if p["ready"]]
    return MIN_PLAYERS <= len(ready) == len(players) <= MAX_PLAYERS

def broadcast(msg):
    for p in game_state["players"].values():
        try:
            p["conn"].send((json.dumps(msg) + '\n').encode())
        except:
            pass

def send_to_player(pid, msg):
    try:
        conn = game_state["players"][pid]["conn"]
        conn.send((json.dumps(msg) + '\n').encode())
    except:
        pass

def draw_card():
    return game_state["deck"].pop() if game_state["deck"] else None

def start_game():
    game_state["started"] = True
    game_state["deck"] = create_deck()
    players = list(game_state["players"].values())
    for pid, p in game_state["players"].items():
        p["hand"].append(draw_card())
        send_to_player(pid, {"type": "start", "players": [pl["name"] for pl in players]})
        send_to_player(pid, {"type": "hand", "hand": p["hand"]})
    next_turn()

def next_turn():
    while game_state["turn"] in game_state["eliminated"]:
        game_state["turn"] = (game_state["turn"] + 1) % len(game_state["players"])
    pid = game_state["turn"]
    player = game_state["players"][pid]
    if pid in game_state["eliminated"]:
        return
    new_card = draw_card()
    if new_card:
        player["hand"].append(new_card)
    send_to_player(pid, {
        "type": "your_turn",
        "hand": player["hand"],
        "history": game_state["history"]
    })

def process_turn(pid, msg):
    card = msg["card"]
    target_id = msg.get("target")
    guess = msg.get("guess")
    player = game_state["players"][pid]

    if card not in player["hand"]:
        return
    player["hand"].remove(card)
    result = f"{player['name']} joue {card}"

    # 🔴 Ajout à l'historique
    game_state["history"].append({"player": player["name"], "card": card})

    if card == "Garde" and target_id is not None and guess:
        target = game_state["players"][target_id]
        if guess != "Garde" and guess in target["hand"] and not target["protected"]:
            game_state["eliminated"].add(target_id)
            result += f" et élimine {target['name']} (deviné {guess})"
        else:
            result += " mais ça ne marche pas"

    elif card == "Pretre" and target_id is not None:
        target = game_state["players"][target_id]
        if not target["protected"]:
            send_to_player(pid, {"type": "reveal", "target": target["name"], "card": target["hand"]})

    elif card == "Baron" and target_id is not None:
        target = game_state["players"][target_id]
        if not target["protected"]:
            if CARD_VALUES[player["hand"][0]] > CARD_VALUES[target["hand"][0]]:
                game_state["eliminated"].add(target_id)
                result += f" et {target['name']} est éliminé"
            else:
                game_state["eliminated"].add(pid)
                result += f" et {player['name']} est éliminé"

    elif card == "Servante":
        player["protected"] = True

    elif card == "Prince" and target_id is not None:
        target = game_state["players"][target_id]
        if not target["protected"]:
            discarded = target["hand"].pop()
            target["hand"].append(draw_card())
            send_to_player(target_id, {"type": "hand", "hand": target["hand"]})
            if discarded == "Princesse":
                game_state["eliminated"].add(target_id)
                result += f" et {target['name']} est éliminé (Princesse défaussée)"

    elif card == "Roi" and target_id is not None:
        target = game_state["players"][target_id]
        player["hand"], target["hand"] = target["hand"], player["hand"]
        send_to_player(pid, {"type": "hand", "hand": player["hand"]})
        send_to_player(target_id, {"type": "hand", "hand": target["hand"]})

    elif card == "Princesse":
        game_state["eliminated"].add(pid)
        result += " et se fait éliminer (joué la Princesse)"

    broadcast({"type": "log", "content": result})
    player["protected"] = False

    alive = [p for p in game_state["players"] if p not in game_state["eliminated"]]
    if len(alive) == 1:
        winner = game_state["players"][alive[0]]["name"]
        broadcast({"type": "end", "winner": winner})
        return

    game_state["turn"] = (game_state["turn"] + 1) % len(game_state["players"])
    next_turn()

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen()
    print(f"[Serveur] En écoute sur {HOST}:{PORT}")
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

if __name__ == '__main__':
    start_server()