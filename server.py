import sys, socket, select
host = "127.0.0.1"
port = int(sys.argv[1])

user_by_sock = {}
sock_by_user = {}


def broadcast(payload_bytes,exclude=None):
    if exclude == None:
        exclude = []
    for client in list(sockets):
        if client not in exclude and client != s:
            try:
                client.sendall(payload_bytes)
            except OSError:
                sockets.remove(client)
                username = user_by_sock.pop(client,None)
                sock_by_user.pop(username,None)
                client.close()

def unicast(payload_bytes,user,sender):
    sock = sock_by_user[user]
    msg = b"(private) " + f"[{sender}] ".encode() + payload_bytes + b"\n"
    sock.sendall(msg)

def disconnect(sock,unexpected=False):
    user = user_by_sock.get(sock)
    if sock in sockets:
        sockets.remove(sock)
    user_by_sock.pop(sock,None)
    sock_by_user.pop(user,None)
    sock.close()
    if user: broadcast(f"[{user}] has left\n".encode())


with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind((host, port))
    sockets = [s]
    s.listen()

    while True:
        readable, _, exceptional = select.select(sockets,[],sockets)
        for sock in readable:
            if sock == s:
                conn, addr = s.accept()
                sockets.append(conn)
                conn.sendall(b"Welcome ... \n")
                print(f"Connected by {addr}")
            else:
                try:
                    data = sock.recv(1024)
                except ConnectionResetError:
                    disconnect(sock,True)
                    continue
                if not data:
                    disconnect(sock,True)
                    continue
                parts = data.split()
                if not parts:
                    continue
                if parts[0] == b"HELLO" and sock not in user_by_sock:
                    if len(parts) != 2:
                        sock.sendall(b"Username not provided by client.")
                        disconnect(sock,True)
                        continue
                    username = parts[1].decode()
                    user_by_sock[sock] = username
                    sock_by_user[username] = sock
                    broadcast(f"[{username}] has joined\n".encode(),[sock])
                elif parts[0] == b"QUIT":
                    disconnect(sock)
                elif parts[0] == b"/to":
                    if len(parts) < 3:
                        sock.sendall(b"/to command incorrectly formatted. Should be /to USERNAME MESSAGE.\n")
                        continue
                    username = parts[1].decode()
                    if username not in sock_by_user:
                        sock.sendall(b"Username not found.\n")
                        continue

                    message = b" ".join(parts[2:])
                    sender = user_by_sock.get(sock,"UNKNOWN")
                    unicast(message,username,sender)
                else:
                    username = user_by_sock.get(sock,"UNKNOWN")
                    msg = f"[{username}] {data.decode(errors='replace')}"
                    data = msg.encode()
                    broadcast(data,[sock])
        for sock in exceptional:
            disconnect(sock,True)
