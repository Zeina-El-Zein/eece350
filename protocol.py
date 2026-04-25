import json
import struct

# It defines the communication protocol used to send and receive messages
# Each message is converted to JSON, then sent with a 4-byte length prefix

def send_message(sock, data):
    """
    Send one JSON message over TCP using:
    [4-byte big-endian length][JSON bytes]
    """
    #convert the Python dictionary into a JSON string
    #then encode it into bytes so it can be sent through the socket

    json_bytes = json.dumps(data).encode("utf-8")

    #create a 4-byte big-endian integer containing the size of the JSON message
    #this allows the receiver to know exactly how many bytes to read
    length_prefix = struct.pack("!I", len(json_bytes))

    #send the length first, then the actual JSON message
    #sendall() makes sure that all bytes are sent
    sock.sendall(length_prefix + json_bytes)


def recv_exact(sock, num_bytes):
    """
    Receive exactly num_bytes from the socket.
    Return None if connection closes before enough bytes arrive.
    """
    #store the received bytes here until we reach the expected size
    buffer = b""
    while len(buffer) < num_bytes:
        chunk = sock.recv(num_bytes - len(buffer))   #receive only the number of bytes still missing
        if not chunk:
            return None
        buffer += chunk   #we add the received part to the buffer
    return buffer


def receive_message(sock):
    """
    Receive one framed JSON message.
    First read 4-byte length, then read the JSON body.
    Return the parsed Python dictionary, or None if disconnected.
    """

    #first,read the 4-byte length prefix
    raw_length = recv_exact(sock, 4)
    if raw_length is None:
        return None

    #convert the 4-byte prefix back into an integer message length
    message_length = struct.unpack("!I", raw_length)[0]

    #read exactly message_length bytes, which represent the JSON message body
    raw_message = recv_exact(sock, message_length)
    if raw_message is None:
        return None

    #decode the JSON bytes into a string then convert it back to a Python dictionary
    return json.loads(raw_message.decode("utf-8"))
