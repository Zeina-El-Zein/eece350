import socket
from protocol import send_message, receive_message

SERVER_IP = "127.0.0.1"
SERVER_PORT = 5000


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
            print("Disconnected from server before receiving a response.")
            return

        message_type = response.get("type")
        message_text = response.get("message", "")

        if message_type == "USERNAME_OK":
            print(f"Welcome, {username}! {message_text}")
            print("Waiting for lobby updates...\n")

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
                        print(f"- {player}")
                    print("----------------------")

                else:
                    print("Received unknown message:", msg)

        elif message_type == "USERNAME_TAKEN":
            print(f"Username '{username}' is already taken. Please try another one.")

        elif message_type == "ERROR":
            print(f"Server error: {message_text}")

        else:
            print("Unknown server response:", response)

    except ConnectionRefusedError:
        print(f"Could not connect to the server at {SERVER_IP}:{SERVER_PORT}.")
        print("Make sure the server is running first.")

    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    finally:
        client_socket.close()
        print("Connection closed.")


if __name__ == "__main__":
    start_client()
    