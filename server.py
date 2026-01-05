import sys, socket, select
host = "127.0.0.1"
port = int(sys.argv[1])

user_by_sock = {}


def broadcast(sender_sock, payload_bytes):
    for client in sockets:
        if client != sender_sock and client != s:
            try:
                client.sendall(payload_bytes)
            except:
                sockets.remove(client)
                user_by_sock.pop(client,None)
                client.close()

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
                    sockets.remove(sock)
                    user_by_sock.pop(sock,None)
                    sock.close()
                    continue
                parts = data.split()
                if not parts:
                    continue
                if parts[0] == b"HELLO":
                    if len(parts) != 2:
                        sock.sendall(b"Username not provided by client.")
                        sockets.remove(sock)
                        user_by_sock.pop(sock,None)
                        sock.close()
                        continue
                    sts = parts[1] + b" connected \n"
                    user_by_sock[sock] = parts[1]
                    broadcast(sock,sts)
                else:
                    username = user_by_sock.get(sock,b"UNKNOWN")
                    data = b"%s: %s" % (username, data)
                    broadcast(sock,data)
        for sock in exceptional:
            if sock in sockets:
                sockets.remove(sock)
            user_by_sock.pop(sock,None)
            sock.close()
