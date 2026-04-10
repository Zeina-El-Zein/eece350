import socket
import threading
from protocol import send_message, receive_message

HOST = "0.0.0.0"
PORT = 5000

active_usernames = set()
connected_clients = {}
state_lock = threading.Lock()

game_in_progress = False
pending_challenges = {}
players_in_game = []


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


def start_game(socket1, socket2, username1, username2):
    global game_in_progress, players_in_game
    with state_lock:
        game_in_progress = True
        players_in_game = [socket1, socket2]

    send_message(socket1, {
        "type": "GAME_START",
        "player1": username1,
        "player2": username2
    })
    send_message(socket2, {
        "type": "GAME_START",
        "player1": username1,
        "player2": username2
    })
    print(f"[GAME START] {username1} vs {username2}")


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
        print(f"[CHALLENGE DECLINED] {responder_name} declined {challenger_name}")
        return

    if challenger_socket:
        start_game(challenger_socket, responder_socket, challenger_name, responder_name)


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

            else:
                print(f"[RECEIVED FROM {username}] {msg}")

    except Exception as e:
        print(f"[ERROR] {client_address}: {e}")

    finally:
        with state_lock:
            username = connected_clients.pop(client_socket, None)
            if username and username in active_usernames:
                active_usernames.remove(username)

        if username:
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
