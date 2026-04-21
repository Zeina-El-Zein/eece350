import socket
import threading
import time
from protocol import send_message, receive_message
from game_engine import GameEngine, TICK_INTERVAL

HOST = "0.0.0.0"
PORT = 5000

active_usernames = set()
connected_clients = {}
player_states = {}
state_lock = threading.Lock()

game_in_progress = False
pending_challenges = {}
players_in_game = []
game_engine = None


def build_lobby_message():
    return {
        "type": "LOBBY",
        "players": sorted(list(active_usernames))
    }


def broadcast_lobby():
    lobby = build_lobby_message()
    for client in list(connected_clients.keys()):
        try:
            send_message(client, lobby)
        except Exception as e:
            print(f"[BROADCAST ERROR] {e}")


def get_socket_by_username(username):
    for sock, uname in connected_clients.items():
        if uname == username:
            return sock
    return None


def broadcast_game_state():
    state = game_engine.get_state()
    for sock in players_in_game:
        try:
            send_message(sock, {"type": "GAME_STATE", **state})
        except Exception as e:
            print(f"[GAME BROADCAST ERROR] {e}")


def game_loop():
    global game_in_progress, players_in_game, game_engine

    print("[GAME LOOP] Started")

    # wait for client countdown to finish
    time.sleep(10)

    while not game_engine.game_over:
        t0 = time.time()
        game_engine.tick()
        broadcast_game_state()
        elapsed = time.time() - t0
        sleep_time = TICK_INTERVAL - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)
    # game is over — send GAME_OVER to both players
    state = game_engine.get_state()
    end_msg = {
        "type": "GAME_OVER",
        "winner": state["winner"],
        "end_reason": state["end_reason"],
        "scores": {
            state["snake1"]["username"]: state["snake1"]["health"],
            state["snake2"]["username"]: state["snake2"]["health"],
        }
    }

    for sock in players_in_game:
        try:
            send_message(sock, end_msg)
        except Exception as e:
            print(f"[GAME OVER SEND ERROR] {e}")

    print(f"[GAME OVER] Winner: {state['winner']} — {state['end_reason']}")

    # reset all game state
    with state_lock:
        for sock in players_in_game:
            uname = connected_clients.get(sock)
            if uname:
                player_states[uname] = "lobby"
        game_in_progress = False
        players_in_game  = []
        game_engine      = None

    broadcast_lobby()

def start_game(socket1, socket2, username1, username2):
    global game_in_progress, players_in_game, game_engine

    with state_lock:
        game_in_progress = True
        players_in_game = [socket1, socket2]
        player_states[username1] = "in_game"
        player_states[username2] = "in_game"
        game_engine = GameEngine(username1, username2)

    game_start_msg = {
        "type": "GAME_START",
        "player1": username1,
        "player2": username2,
        "grid_w": 40,
        "grid_h": 30,
        "duration": 120
    }
    send_message(socket1, game_start_msg)
    send_message(socket2, game_start_msg)

    print(f"[GAME START] {username1} vs {username2}")

    thread = threading.Thread(target=game_loop, daemon=True)
    thread.start()


def handle_input(username, msg):
    global game_engine
    if not game_engine or game_engine.game_over:
        return

    direction = msg.get("direction", [0, 0])
    dx, dy = int(direction[0]), int(direction[1])

    with state_lock:
        uname1 = game_engine.snake1.username
        uname2 = game_engine.snake2.username

    if username == uname1:
        game_engine.handle_input(1, dx, dy)
    elif username == uname2:
        game_engine.handle_input(2, dx, dy)

def handle_chat(sender_username, msg):
    message = msg.get("message", "").strip()
    if not message:
        return

    chat_msg = {
        "type": "CHAT_MSG",
        "from": sender_username,
        "message": message
    }

    with state_lock:
        recipients = list(connected_clients.keys())

    for sock in recipients:
        uname = connected_clients.get(sock)
        if uname != sender_username:
            try:
                send_message(sock, chat_msg)
            except Exception as e:
                print(f"[CHAT ERROR] {e}")
def handle_challenge(challenger_socket, challenger_name, msg):
    global game_in_progress, pending_challenges

    target_name = msg.get("target", "").strip()

    with state_lock:
        if game_in_progress:
            send_message(challenger_socket, {
                "type": "ERROR",
                "message": "A game is already in progress."
            })
            return

        if target_name not in active_usernames:
            send_message(challenger_socket, {
                "type": "ERROR",
                "message": f"Player '{target_name}' not found."
            })
            return

        if target_name == challenger_name:
            send_message(challenger_socket, {
                "type": "ERROR",
                "message": "You cannot challenge yourself."
            })
            return

        pending_challenges[challenger_name] = target_name

    target_socket = get_socket_by_username(target_name)
    if target_socket:
        send_message(target_socket, {
            "type": "CHALLENGE_IN",
            "from": challenger_name
        })
        print(f"[CHALLENGE] {challenger_name} challenged {target_name}")


def handle_challenge_resp(responder_socket, responder_name, msg):
    global pending_challenges

    accepted = msg.get("accepted", False)

    with state_lock:
        challenger_name = None
        for c, t in pending_challenges.items():
            if t == responder_name:
                challenger_name = c
                break

        if not challenger_name:
            send_message(responder_socket, {
                "type": "ERROR",
                "message": "No pending challenge found."
            })
            return

        del pending_challenges[challenger_name]

    challenger_socket = get_socket_by_username(challenger_name)

    if not accepted:
        if challenger_socket:
            send_message(challenger_socket, {
                "type": "ERROR",
                "message": f"{responder_name} declined your challenge."
            })
        return

    if challenger_socket:
        start_game(challenger_socket, responder_socket,
                   challenger_name, responder_name)


def handle_disconnect_during_game(username):
    global game_engine, game_in_progress, players_in_game

    if not game_engine or game_engine.game_over:
        return

    with state_lock:
        game_engine.game_over = True
        if game_engine.snake1.username == username:
            game_engine.winner = game_engine.snake2.username
        else:
            game_engine.winner = game_engine.snake1.username
        game_engine.end_reason = f"{username} disconnected"

    print(f"[FORFEIT] {username} disconnected during game")

def handle_client(client_socket, client_address):
    print(f"[NEW CONNECTION] {client_address} connected.")

    try:
        join_msg = receive_message(client_socket)

        if join_msg is None:
            client_socket.close()
            return

        if join_msg.get("type") != "JOIN":
            send_message(client_socket, {
                "type": "ERROR",
                "message": "First message must be JOIN"
            })
            client_socket.close()
            return

        username = join_msg.get("username", "").strip()

        if not username:
            send_message(client_socket, {
                "type": "ERROR",
                "message": "Username cannot be empty"
            })
            client_socket.close()
            return

        with state_lock:
            if username in active_usernames:
                send_message(client_socket, {
                    "type": "USERNAME_TAKEN",
                    "message": "Username already in use"
                })
                client_socket.close()
                return

            active_usernames.add(username)
            connected_clients[client_socket] = username
            player_states[username] = "lobby"

        send_message(client_socket, {
            "type": "USERNAME_OK",
            "message": "Username accepted"
        })

        print(f"[USERNAME ACCEPTED] {username} joined from {client_address}")
        broadcast_lobby()

        while True:
            msg = receive_message(client_socket)
            if msg is None:
                break

            msg_type = msg.get("type")

            if msg_type == "CHALLENGE":
                handle_challenge(client_socket, username, msg)

            elif msg_type == "CHALLENGE_RESP":
                handle_challenge_resp(client_socket, username, msg)

            elif msg_type == "INPUT":
                handle_input(username, msg)

            elif msg_type == "CHAT":
                handle_chat(username, msg)

            else:
                print(f"[RECEIVED FROM {username}] {msg}")

    except Exception as e:
        print(f"[ERROR] {client_address}: {e}")

    finally:
        current_state = player_states.get(username)
        if current_state == "in_game":
            handle_disconnect_during_game(username)

        with state_lock:
            connected_clients.pop(client_socket, None)
            active_usernames.discard(username)
            player_states.pop(username, None)

        print(f"[DISCONNECTED] {username}")
        broadcast_lobby()
        client_socket.close()


def start_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen()

    print(f"[SERVER STARTED] Listening on {HOST}:{PORT}")

    while True:
        client_socket, client_address = server_socket.accept()
        thread = threading.Thread(
            target=handle_client,
            args=(client_socket, client_address),
            daemon=True
        )
        thread.start()


if __name__ == "__main__":
    start_server()
