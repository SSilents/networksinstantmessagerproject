import sys, socket, select, os

# Configure shared files directory (from environment or default to ./SharedFiles)
SHARED_DIR = os.environ.get("SERVER_SHARED_FILES")

if not SHARED_DIR:
    SHARED_DIR = os.path.join(os.path.dirname(__file__), "SharedFiles")
if not os.path.isdir(SHARED_DIR):
    print(f"Error: SharedFiles directory not found: {SHARED_DIR}")

# Server configuration
host = "127.0.0.1"
port = int(sys.argv[1])

# Data structures to track connected clients
user_by_sock = {}  # socket -> username mapping
sock_by_user = {}  # username -> socket mapping
groups = {}  # groupname -> [list of member sockets]
groups_by_sock = {}  # socket -> [list of groups they're in]

# Per-client protocol selection for file downloads
download_proto_by_sock = {}

# UDP socket for file transfers
udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_port_by_sock = {}  # socket -> UDP port (where client listens)
recv_buf_by_sock = (
    {}
)  # socket -> incomplete line buffer (TCP is a stream, not message-based)


def broadcast(payload_bytes, exclude=None):
    """Send message to all connected clients except those in exclude list"""
    if exclude == None:
        exclude = []
    for client in list(sockets):
        if client not in exclude and client != s:
            try:
                client.sendall(payload_bytes)
            except OSError:
                disconnect(client, True)


def unicast(payload_bytes, user, sender):
    """Send private message from sender to specific user"""
    # Notify sender
    sock = sock_by_user[sender]
    msg = f"(to {user}) ".encode() + payload_bytes + b"\n"
    sock.sendall(msg)

    # Send to recipient
    sock = sock_by_user[user]
    msg = b"(private) " + f"[{sender}] ".encode() + payload_bytes + b"\n"
    sock.sendall(msg)


def join_group(sock, group):
    """Add client to group (create group if it doesn't exist)"""
    msg = ""
    if group not in groups:
        groups[group] = []
        msg = f"(created group) {group}\n".encode()
    groups[group].append(sock)

    # Track groups per socket for cleanup on disconnect
    if sock not in groups_by_sock:
        groups_by_sock[sock] = [group]
    else:
        groups_by_sock[sock].append(group)

    if not msg:
        msg = f"(joined group) [{group}]\n".encode()
    sock.sendall(msg)

    # Notify other group members
    username = user_by_sock.get(sock, "UNKNOWN")
    msg = f"[{username}] has joined group [{group}]\n".encode()
    multicast(group, msg, [sock])


def leave_group(sock, group, *, announce=True, ack=True):
    """Remove client from group"""
    if group not in groups:
        sock.sendall(b"ERROR: Group does not exist.\n")
        return
    if sock not in groups[group]:
        sock.sendall(b"ERROR: You are not a member of this group.\n")
        return

    groups[group].remove(sock)

    # Update per-socket group tracking
    if sock in groups_by_sock and group in groups_by_sock[sock]:
        groups_by_sock[sock].remove(group)
        if not groups_by_sock[sock]:
            del groups_by_sock[sock]

    username = user_by_sock.get(sock, "UNKNOWN")

    # Delete group if empty
    if not groups[group]:
        del groups[group]
        sock.sendall(f"Left group [{group}] (group deleted)\n".encode())
        return

    if ack:
        sock.sendall(f"Left group [{group}]\n".encode())
    if announce:
        message = f"[{username}] left group [{group}]\n".encode()
        multicast(group, message, [sock])


def multicast(group, payload, exclude=None):
    """Send message to all members of a group except those in exclude list"""
    if exclude == None:
        exclude = []
    for member in groups[group]:
        if member != s and member not in exclude:
            try:
                member.sendall(payload)
            except OSError:
                disconnect(member, True)


def disconnect(sock, unexpected=False):
    """Clean up client connection: remove from groups, mappings, notify others"""
    user = user_by_sock.get(sock)
    if sock in sockets:
        sockets.remove(sock)

    # Remove from all groups
    for group in list(groups_by_sock.get(sock, [])):
        leave_group(sock, group, announce=True, ack=False)

    # Clean up all mappings
    groups_by_sock.pop(sock, None)
    user_by_sock.pop(sock, None)
    download_proto_by_sock.pop(sock, None)
    udp_port_by_sock.pop(sock, None)

    if user:
        sock_by_user.pop(user, None)

    try:
        sock.close()
    finally:
        if user:
            broadcast(f"[{user}] has left\n".encode())


def list_files(sock):
    """Send list of available shared files to client"""
    dir_list = os.listdir(SHARED_DIR)
    message = f"(shared) Number of files: {len(dir_list)}\n".encode()
    sock.sendall(message)
    for f in dir_list:
        size = os.stat(os.path.join(SHARED_DIR, f)).st_size
        message = f"(shared) {f} : {size}Bytes\n".encode()
        sock.sendall(message)
    message = f"(shared) end\n".encode()  # Signals end of listing
    sock.sendall(message)


def tcp_download(filename, sock):
    """Send file to client using reliable TCP connection"""
    path = os.path.join(SHARED_DIR, filename)
    size = os.path.getsize(path)

    # Send header with filename and size
    sock.sendall(f"(file) ok |{filename}| {size} Bytes\n".encode())

    # Stream file data
    with open(path, "rb") as fp:
        while True:
            chunk = fp.read(4096)
            if not chunk:
                break
            sock.sendall(chunk)


def udp_download(filename, client_sock):
    """Send file to client using unreliable UDP with sequence numbers"""
    # Get client's UDP listening port (registered earlier via UDPPORT command)
    client_ip = client_sock.getpeername()[0]
    client_port = udp_port_by_sock.get(client_sock)
    if not client_port:
        client_sock.sendall(b"ERROR: UDP port not registered.")
        return
    client_addr = (client_ip, client_port)

    path = os.path.join(SHARED_DIR, filename)
    size = os.path.getsize(path)

    # Send header via reliable TCP
    client_sock.sendall(f"(file) ok |{filename}| {size} Bytes\n".encode())

    # Send file data via UDP with sequence numbers
    with open(path, "rb") as fp:
        seq = 0
        while True:
            data = fp.read(1000)  # 1000-byte chunks
            if not data:
                break
            # Packet format: [4-byte seq][data]
            pkt = seq.to_bytes(4, "big") + data
            udp_sock.sendto(pkt, client_addr)
            seq += 1

    # Send end-of-file marker (seq = 0xFFFFFFFF)
    udp_sock.sendto((0xFFFFFFFF).to_bytes(4, "big"), client_addr)


# Main server loop using select() for multiplexed I/O
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind((host, port))
    sockets = [s]  # List of all sockets to monitor
    s.listen()

    while True:
        # Wait for any socket to become readable or exceptional
        readable, _, exceptional = select.select(sockets, [], sockets)

        for sock in readable:
            # New connection on listening socket
            if sock == s:
                conn, addr = s.accept()
                sockets.append(conn)
                recv_buf_by_sock[conn] = ""  # Initialize line buffer
                conn.sendall(b"Welcome ... \n")
                print(f"Connected by {addr}")
            else:
                # Data from existing client
                try:
                    data = sock.recv(4096)
                except ConnectionResetError:
                    disconnect(sock, True)
                    continue
                if not data:
                    disconnect(sock, True)
                    continue

                # TCP is a stream - buffer partial lines and process complete ones
                buf = recv_buf_by_sock.get(sock, "") + data.decode(errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split()
                    if not parts:
                        continue

                    cmd = parts[0]

                    # Initial handshake: client sends username
                    if cmd == "HELLO" and sock not in user_by_sock:
                        if len(parts) != 2:
                            sock.sendall(b"Username not provided by client.")
                            disconnect(sock, True)
                            continue
                        username = parts[1]
                        user_by_sock[sock] = username
                        sock_by_user[username] = sock
                        broadcast(f"[{username}] has joined\n".encode(), [sock])

                    # Client disconnecting
                    elif cmd == "QUIT":
                        disconnect(sock)

                    # Private message: /to USERNAME MESSAGE
                    elif cmd == "/to":
                        if len(parts) < 3:
                            sock.sendall(
                                b"ERROR: /to command incorrectly formatted. Should be /to USERNAME MESSAGE.\n"
                            )
                            continue
                        username = parts[1]
                        if username not in sock_by_user:
                            sock.sendall(b"ERROR: Username not found.\n")
                            continue
                        message = " ".join(parts[2:]).encode()
                        sender = user_by_sock.get(sock, "UNKNOWN")
                        if username == sender:
                            sock.sendall(b"ERROR: Cannot send message to self.\n")
                            continue
                        unicast(message, username, sender)

                    # Join group: /join GROUPNAME
                    elif cmd == "/join":
                        if len(parts) != 2:
                            sock.sendall(
                                b"ERROR: /join command incorrectly formatted. Should be /join GROUPNAME.\n"
                            )
                            continue
                        groupname = parts[1]
                        join_group(sock, groupname)

                    # Group message: /group GROUPNAME MESSAGE
                    elif cmd == "/group":
                        if len(parts) < 3:
                            sock.sendall(
                                b"ERROR: /group command incorrectly formatted. Should be /group GROUPNAME MESSAGE.\n"
                            )
                            continue
                        groupname = parts[1]
                        if groupname not in groups:
                            sock.sendall(b"ERROR: Group not found.\n")
                            continue
                        if sock not in groups[groupname]:
                            sock.sendall(
                                b"ERROR: You are not a member of this group.\n"
                            )
                            continue
                        message = " ".join(parts[2:])
                        sender = user_by_sock.get(sock, "UNKNOWN")
                        formattedmsg = f"[{groupname}] [{sender}] {message}\n".encode()
                        multicast(groupname, formattedmsg, [sock])

                    # Leave group: /leave GROUPNAME
                    elif cmd == "/leave":
                        if len(parts) != 2:
                            sock.sendall(
                                b"ERROR: /leave command incorrectly formatted. Should be /leave GROUPNAME.\n"
                            )
                            continue
                        groupname = parts[1]
                        leave_group(sock, groupname)

                    # List shared files: /share
                    elif cmd == "/share":
                        if len(parts) != 1:
                            sock.sendall(
                                b"ERROR: /share command incorrectly formatted. Should be /share.\n"
                            )
                            continue
                        list_files(sock)

                    # Download file: /get FILENAME
                    elif cmd == "/get":
                        if len(parts) < 2:
                            sock.sendall(
                                b"ERROR: /get command incorrectly formatted. Should be /get FILENAME.\n"
                            )
                            continue
                        dir_list = os.listdir(SHARED_DIR)
                        filename = " ".join(parts[1:])  # Support filenames with spaces
                        if filename not in dir_list:
                            sock.sendall(b"ERROR: file not found.\n")
                            continue
                        # Use client's selected protocol (default TCP)
                        proto = download_proto_by_sock.get(sock, "TCP")
                        if proto == "TCP":
                            tcp_download(filename, sock)
                        elif proto == "UDP":
                            udp_download(filename, sock)

                    # Change download protocol: /proto tcp|udp
                    elif cmd == "/proto":
                        if len(parts) != 2:
                            sock.sendall(
                                b"ERROR: /proto command incorrectly formatted. Should be /proto tcp|udp.\n"
                            )
                            continue
                        if parts[1].lower() == "tcp":
                            download_proto_by_sock[sock] = "TCP"
                            sock.sendall(b"(proto) ok tcp\n")
                        elif parts[1].lower() == "udp":
                            download_proto_by_sock[sock] = "UDP"
                            sock.sendall(b"(proto) ok udp\n")
                        else:
                            sock.sendall(
                                b"ERROR: /proto command incorrectly formatted. Should be /proto tcp|udp.\n"
                            )

                    # Client registering UDP port: UDPPORT <port>
                    elif cmd == "UDPPORT":
                        if len(parts) != 2:
                            sock.sendall(b"ERROR: UDP port not provided by client.\n")
                            continue
                        try:
                            udp_port_by_sock[sock] = int(parts[1])
                        except ValueError:
                            sock.sendall(b"ERROR: invalid UDP port.\n")

                    # Default: treat as broadcast message
                    else:
                        username = user_by_sock.get(sock, "UNKNOWN")
                        msg = f"[{username}] {line}\n".encode()
                        broadcast(msg, [sock])

                recv_buf_by_sock[sock] = buf  # Save remaining incomplete line

        # Handle exceptional conditions (errors on sockets)
        for sock in exceptional:
            disconnect(sock, True)
