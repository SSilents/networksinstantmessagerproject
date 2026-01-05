import sys, socket, select
host = "127.0.0.1"
port = int(sys.argv[1])

user_by_sock = {}


def broadcast(payload_bytes,exclude=None):
    for client in sockets:
        if client not in exclude and client != s:
            try:
                client.sendall(payload_bytes)
            except:
                sockets.remove(client)
                user_by_sock.pop(client,None)
                client.close()
def disconnect(sock,unexpected=False):
    user = user_by_sock(sock)
    if sock in sockets:
        sockets.remove(sock)
    user_by_sock.pop(sock,None)
    sock.close()
    broadcast(f"[{user}] has left\n".encode())


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
                    sockets.remove(sock)
                    sock.close()
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
                    broadcast(f"[{username}] has joined\n".encode(),[sock])
                elif parts[0] == "QUIT":
                    disconnect(sock)
                else:
                    username = user_by_sock.get(sock,b"UNKNOWN")
                    msg = f"[{username}] {data.decode(errors='replace')}"
                    data = msg.encode()
                    broadcast(data,[sock])
        for sock in exceptional:
            disconnect(sock,True)
