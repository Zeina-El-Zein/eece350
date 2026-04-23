
import json
import struct

#code 1
def send_message(sock, data):
    """
    Send one JSON message over TCP using:
    [4-byte big-endian length][JSON bytes]
    """
    json_bytes = json.dumps(data).encode("utf-8")
    length_prefix = struct.pack("!I", len(json_bytes))
    sock.sendall(length_prefix + json_bytes)


def recv_exact(sock, num_bytes):
    """
    Receive exactly num_bytes from the socket.
    Return None if connection closes before enough bytes arrive.
    """
    buffer = b""
    while len(buffer) < num_bytes:
        chunk = sock.recv(num_bytes - len(buffer))
        if not chunk:
            return None
        buffer += chunk
    return buffer


def receive_message(sock):
    """
    Receive one framed JSON message.
    First read 4-byte length, then read the JSON body.
    Return the parsed Python dictionary, or None if disconnected.
    """
    raw_length = recv_exact(sock, 4)
    if raw_length is None:
        return None

    message_length = struct.unpack("!I", raw_length)[0]
    raw_message = recv_exact(sock, message_length)
    if raw_message is None:
        return None

    return json.loads(raw_message.decode("utf-8"))

