import socket
import threading
from protocol import send_message, receive_message

SERVER_IP = "127.0.0.1"
SERVER_PORT = 5000

in_game = False


def receive_thread(client_socket):
    global in_game
    while True:
        msg = receive_message(client_socket)
        if msg is None:
            print("Server disconnected.")
            break

        msg_type = msg.get("type")

        if msg_type == "LOBBY":
            players = msg.get("players", [])
            print("\n--- Online Players ---")
            for player in players:
                print(f"  - {player}")
            print("----------------------")
            print("Type 'challenge <username>' to challenge a player.")

        elif msg_type == "CHALLENGE_IN":
            from_user = msg.get("from", "?")
            print(f"\n*** {from_user} is challenging you! ***")
            print("Type 'accept' or 'decline'.")

        elif msg_type == "GAME_START":
            p1 = msg.get("player1")
            p2 = msg.get("player2")
            print(f"\n*** GAME STARTING: {p1} vs {p2} ***")
            in_game = True

        elif msg_type == "ERROR":
            print(f"[ERROR] {msg.get('message')}")

        else:
            print(f"[SERVER] {msg}")


def input_thread(client_socket):
    global in_game
    while True:
        try:
            cmd = input().strip()
        except EOFError:
            break

        if not cmd:
            continue

        if in_game:
            print("Game input not yet implemented.")
            continue

        if cmd.startswith("challenge "):
            target = cmd.split(" ", 1)[1].strip()
            send_message(client_socket, {
                "type": "CHALLENGE",
                "target": target
            })

        elif cmd == "accept":
            send_message(client_socket, {
                "type": "CHALLENGE_RESP",
                "accepted": True
            })

        elif cmd == "decline":
            send_message(client_socket, {
                "type": "CHALLENGE_RESP",
                "accepted": False
            })

        else:
            print("Unknown command. Try: challenge <username>, accept, decline")
        


def start_client():
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        client_socket.connect((SERVER_IP, SERVER_PORT))
        print(f"Connected to server at {SERVER_IP}:{SERVER_PORT}")

        username = input("Enter your username: ").strip()
        if not username:
            print("Username cannot be empty.")
            return

        send_message(client_socket, {
            "type": "JOIN",
            "username": username
        })

        response = receive_message(client_socket)
        if response is None:
            print("Disconnected before receiving response.")
            return

        msg_type = response.get("type")

        if msg_type == "USERNAME_TAKEN":
            print("Username already taken.")
            return

        elif msg_type == "ERROR":
            print(f"Error: {response.get('message')}")
            return

        elif msg_type == "USERNAME_OK":
            print(f"Welcome, {username}!")

        t_recv = threading.Thread(target=receive_thread, args=(client_socket,), daemon=True)
        t_input = threading.Thread(target=input_thread, args=(client_socket,), daemon=True)

        t_recv.start()
        t_input.start()

        t_recv.join()

    except ConnectionRefusedError:
        print("Could not connect. Is the server running?")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        client_socket.close()
        print("Connection closed.")


if __name__ == "__main__":
    start_client()
