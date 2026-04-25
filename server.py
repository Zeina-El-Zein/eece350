import socket
import threading
import time
import sys
from protocol import send_message, receive_message
from game_engine import GameEngine, TICK_INTERVAL, GRID_W, GRID_H, GAME_DURATION
HOST = "0.0.0.0"
PORT = 5000

active_usernames = set()
connected_clients = {}
player_states = {}  #stores the current state of each player like lobby in_game or spectating
state_lock = threading.Lock()  #to protect shared data between threads
player_colors = {}   # username -> [r, g, b]

game_in_progress = False
pending_challenges = {}
players_in_game = []
game_engine = None
spectators = []

def build_lobby_message():
    return {
        "type": "LOBBY",
        "players": [
            {"username": uname, "status": player_states.get(uname, "lobby")}
            for uname in sorted(active_usernames)
        ]
    }

def broadcast_lobby():
    #send the lobby list to every connected client
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
    return None #if the user is not connected


def broadcast_game_state():
    state = game_engine.get_state()
    all_recipients = players_in_game + spectators
    for sock in all_recipients:
        try:
            send_message(sock, {"type": "GAME_STATE", **state})
        except Exception as e:
            print(f"[GAME BROADCAST ERROR] {e}")


def game_loop():
    
    global game_in_progress, players_in_game, game_engine, spectators

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
    #send the result to players and spectators
    all_recipients = players_in_game + spectators
    for sock in all_recipients:
        try:
            send_message(sock, end_msg)
        except Exception as e:
            print(f"[GAME OVER SEND ERROR] {e}")

    print(f"[GAME OVER] Winner: {state['winner']} — {state['end_reason']}")

    #reset the server state after the game ends
    with state_lock:
        for sock in players_in_game:
            uname = connected_clients.get(sock)
            if uname:
                player_states[uname] = "lobby"
        for sock in spectators:
            uname = connected_clients.get(sock)
            if uname:
                player_states[uname] = "lobby"
        game_in_progress = False
        players_in_game  = []
        spectators       = []
        game_engine      = None

    broadcast_lobby()
    print("[GAME LOOP] Finished and reset")
    
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
        "color1":  player_colors.get(username1, [60, 200, 120]),
        "color2":  player_colors.get(username2, [80, 140, 255]),
        "grid_w":  GRID_W,
        "grid_h":  GRID_H,
        "duration": GAME_DURATION,
    }
    send_message(socket1, game_start_msg)
    send_message(socket2, game_start_msg)

    print(f"[GAME START] {username1} vs {username2}")

     #update the lobby so other users see that these players are in game
    broadcast_lobby()

    #run the game loop in a separate thread so the server can still accept clients
    thread = threading.Thread(target=game_loop, daemon=True) 
    thread.start()


def handle_input(username, msg):
    global game_engine
    if not game_engine or game_engine.game_over:
        return

    direction = msg.get("direction", [0, 0])
    dx, dy = int(direction[0]), int(direction[1])

    with state_lock: #get the username
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
    #send the chat message to everyone except the sender
    for sock in recipients:
        uname = connected_clients.get(sock)
        if uname != sender_username:
            try:
                send_message(sock, chat_msg)
            except Exception as e:
                print(f"[CHAT ERROR] {e}")

def handle_spectate(client_socket, username):
    global spectators #allow a client to watch the current game
    #add the client to the spectators list
    with state_lock:
        if client_socket not in spectators:
            spectators.append(client_socket)
            player_states[username] = "spectating"

    if game_engine and not game_engine.game_over:  #if a game is running send the current game data to the spectator
        send_message(client_socket, {
            "type": "SPECTATE_OK",
            "game_in_progress": True
        })
        send_message(client_socket, {
            "type": "GAME_START",
            "player1": game_engine.snake1.username,
            "player2": game_engine.snake2.username,
            "color1":  player_colors.get(game_engine.snake1.username, [60, 200, 120]),
            "color2":  player_colors.get(game_engine.snake2.username, [80, 140, 255]),
            "grid_w":  40,
            "grid_h":  30,
            "duration": 120,
            "skip_countdown": True
        })        
        send_message(client_socket, {"type": "GAME_STATE", **game_engine.get_state()})
        print(f"[SPECTATE] {username} joined as spectator")
    else:
        send_message(client_socket, {
            "type": "SPECTATE_OK",
            "game_in_progress": False
        })
        print(f"[SPECTATE] {username} tried to spectate but no game in progress")

     #handle a challenge request from one player to another    
def handle_challenge(challenger_socket, challenger_name, msg):
    global game_in_progress, pending_challenges 
    target_name = msg.get("target", "").strip()
    color = msg.get("color", [60, 200, 120])
    with state_lock:
        player_colors[challenger_name] = color
        
        if game_in_progress: #do not allow challenges while a game is already running
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
    #handle accept or decline from the challenged player
    global pending_challenges

    #read if the challenge was accepted
    accepted = msg.get("accepted", False)
    color = msg.get("color", [80, 140, 255])

    with state_lock:
        #store the responder's selected color
        player_colors[responder_name] = color
        
        #find who challenged this responder
        challenger_name = None
        for c, t in pending_challenges.items():
            if t == responder_name:
                challenger_name = c
                break

        #if no challenge exists send an error
        if not challenger_name:
            send_message(responder_socket, {
                "type": "ERROR",
                "message": "No pending challenge found."
            })
            return

        #remove the pending challenge after response
        del pending_challenges[challenger_name]

    #get the challenger socket
    challenger_socket = get_socket_by_username(challenger_name)

    #if declined notify the challenger
    if not accepted:
        if challenger_socket:
            send_message(challenger_socket, {
                "type": "ERROR",
                "message": f"{responder_name} declined your challenge."
            })
        return

    #if accepted start the match
    if challenger_socket:
        start_game(challenger_socket, responder_socket,
                   challenger_name, responder_name)

def handle_disconnect_during_game(username):
    global game_engine, game_in_progress, players_in_game #end the game if one player disconnects during a match

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
    #this function runs in a separate thread for each connected client
    print(f"[NEW CONNECTION] {client_address} connected.")

    try:
        #first message must be join
        join_msg = receive_message(client_socket)

        #close connection if there is no message that was received
        if join_msg is None:
            client_socket.close()
            return

        #reject the client if the first message is not join
        if join_msg.get("type") != "JOIN":
            send_message(client_socket, {
                "type": "ERROR",
                "message": "First message must be JOIN"
            })
            client_socket.close()
            return

        #read the username from the join message
        username = join_msg.get("username", "").strip()

        #reject empty usernames
        if not username:
            send_message(client_socket, {
                "type": "ERROR",
                "message": "Username cannot be empty"
            })
            client_socket.close()
            return

        #check if username is unique and register the client
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

        #we tell the client that the username is accepted
        send_message(client_socket, {
            "type": "USERNAME_OK",
            "message": "Username accepted"
        })

        print(f"[USERNAME ACCEPTED] {username} joined from {client_address}")

        #update lobby for everyone
        broadcast_lobby()

        #keep receiving messages from this client
        while True:
            msg = receive_message(client_socket)

            #stop loop if client disconnected
            if msg is None:
                break

            msg_type = msg.get("type")

            #send the message to the correct handler
            if msg_type == "CHALLENGE":
                handle_challenge(client_socket, username, msg)

            elif msg_type == "CHALLENGE_RESP":
                handle_challenge_resp(client_socket, username, msg)

            elif msg_type == "INPUT":
                handle_input(username, msg)

            elif msg_type == "CHAT":
                handle_chat(username, msg)

            elif msg_type == "SPECTATE":
                handle_spectate(client_socket, username)

            elif msg_type == "PLAYER_COLOR":
                with state_lock:
                    player_colors[username] = msg.get("color", [60, 200, 120])

            else:
                print(f"[RECEIVED FROM {username}] {msg}")

    #print errors without stopping the whole server
    except Exception as e:
        print(f"[ERROR] {client_address}: {e}")

    finally:
        #if the player disconnects during a game the opponent wins
        current_state = player_states.get(username)
        if current_state == "in_game":
            handle_disconnect_during_game(username)

        #remove the client from all server structures
        with state_lock:
            connected_clients.pop(client_socket, None)
            active_usernames.discard(username)
            player_states.pop(username, None)

            if client_socket in spectators:
                spectators.remove(client_socket)

        print(f"[DISCONNECTED] {username}")

        #update lobby after disconnect
        broadcast_lobby()

        #close the socket
        client_socket.close()


def start_server():
    #create the TCP server socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    #allow reusing the port quickly after restarting the server
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    #bind the server to the host and port
    server_socket.bind((HOST, PORT))

    #start listening for clients
    server_socket.listen()

    print(f"[SERVER STARTED] Listening on {HOST}:{PORT}")

    #accept clients forever
    while True:
        client_socket, client_address = server_socket.accept()

        #create one thread for each client
        thread = threading.Thread(
            target=handle_client,
            args=(client_socket, client_address),
            daemon=True
        )

        #start the client thread
        thread.start()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            PORT = int(sys.argv[1])
        except ValueError:
            print("Invalid port number. Using default port 5000.")
    start_server()
