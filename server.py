import sys, socket, select, os

SHARED_DIR = os.environ.get("SERVER_SHARED_FILES")

if not SHARED_DIR:
    SHARED_DIR = os.path.join(os.path.dirname(__file__),"SharedFiles")
if not os.path.isdir(SHARED_DIR):
    print(f"Error: SharedFiles directory not found: {SHARED_DIR}")

host = "127.0.0.1"
port = int(sys.argv[1])

user_by_sock = {}
sock_by_user = {}
groups = {}
groups_by_sock = {}

def broadcast(payload_bytes,exclude=None):
    if exclude == None:
        exclude = []
    for client in list(sockets):
        if client not in exclude and client != s:
            try:
                client.sendall(payload_bytes)
            except OSError:
                disconnect(client, True)

def unicast(payload_bytes,user,sender):
    sock = sock_by_user[sender]
    msg = f"(to {user}) ".encode() + payload_bytes + b"\n"
    sock.sendall(msg)
    sock = sock_by_user[user]
    msg = b"(private) " + f"[{sender}] ".encode() + payload_bytes + b"\n"
    sock.sendall(msg)

def join_group(sock,group):
    msg = ""
    if group not in groups:
        groups[group] = []
        msg = f"(created group) {group}\n".encode()
    groups[group].append(sock)
    if sock not in groups_by_sock:
        groups_by_sock[sock] = [group]
    else:
        groups_by_sock[sock].append(group)
    if not msg:
        msg = f"(joined group) [{group}]\n".encode()
    sock.sendall(msg)
    username = user_by_sock.get(sock,"UNKNOWN")
    msg = f"[{username}] has joined group [{group}]\n".encode()
    multicast(group,msg,[sock])

def leave_group(sock,group,*,announce=True,ack=True):
    if group not in groups:
        sock.sendall(b"ERROR: Group does not exist.\n")
        return
    if sock not in groups[group]:
        sock.sendall(b"ERROR: You are not a member of this group.\n")
        return
    
    groups[group].remove(sock)

    if sock in groups_by_sock and group in groups_by_sock[sock]:
        groups_by_sock[sock].remove(group)
        if not groups_by_sock[sock]:
            del groups_by_sock[sock]

    username = user_by_sock.get(sock,"UNKNOWN")   

    if not groups[group]:
        del groups[group]
        sock.sendall(f"Left group [{group}] (group deleted)\n".encode())
        return
    if ack:
        sock.sendall(f"Left group [{group}]\n".encode())
    if announce:
        message = f"[{username}] left group [{group}]\n".encode()
        multicast(group,message,[sock])

def multicast(group, payload, exclude=None):
    if exclude == None:
        exclude = []
    for member in groups[group]:
        if member != s and member not in exclude:
            try:
                member.sendall(payload)
            except OSError:
                disconnect(member, True)


def disconnect(sock,unexpected=False):
    user = user_by_sock.get(sock)
    if sock in sockets:
        sockets.remove(sock)

    for group in list(groups_by_sock.get(sock, [])):
        leave_group(sock,group,announce=True,ack=False)

    groups_by_sock.pop(sock, None)
    user_by_sock.pop(sock,None)

    if user:
        sock_by_user.pop(user,None)

    try:
        sock.close()
    finally:
        if user: broadcast(f"[{user}] has left\n".encode())

def list_files(sock):
    dir_list = os.listdir(SHARED_DIR)
    message = f"(shared) Number of files: {len(dir_list)}".encode()
    sock.sendall(message)
    for f in dir_list:
        size = os.stat(os.path.join(SHARED_DIR,f)).st_size
        message = f"(shared) {f} : {size}Bytes\n".encode()
        sock.sendall(message)
    message = f"(shared) end\n".encode()
    sock.sendall(message)
    

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
                        sock.sendall(b"ERROR: /to command incorrectly formatted. Should be /to USERNAME MESSAGE.\n")
                        continue
                    username = parts[1].decode()
                    if username not in sock_by_user:
                        sock.sendall(b"ERROR: Username not found.\n")
                        continue

                    message = b" ".join(parts[2:])
                    sender = user_by_sock.get(sock,"UNKNOWN")
                    unicast(message,username,sender)
                elif parts[0] == b"/join":
                    if len(parts) != 2:
                        sock.sendall(b"ERROR: /join command incorrectly formatted. Should be /join GROUPNAME.\n")
                        continue
                    groupname = parts[1].decode()
                    join_group(sock,groupname)
                elif parts[0] == b"/group":
                    if len(parts) < 3:
                        sock.sendall(b"ERROR: /group command incorrectly formatted. Should be /group GROUPNAME MESSAGE.\n")
                        continue
                    groupname = parts[1].decode()
                    if groupname not in groups:
                        sock.sendall(b"ERROR: Group not found.\n")
                        continue
                    if sock not in groups[groupname]:
                        sock.sendall(b"ERROR: You are not a member of this group.\n")
                        continue
                    message = b" ".join(parts[2:])
                    sender = user_by_sock.get(sock,"UNKNOWN")
                    message = message.decode()
                    formattedmsg = f"[{groupname}] [{sender}] {message}\n".encode()
                    multicast(groupname,formattedmsg,[sock])
                elif parts[0] == b"/leave":
                    if len(parts) != 2:
                        sock.sendall(b"ERROR: /leave command incorrectly formatted. Should be /leave GROUPNAME.\n")
                        continue
                    groupname = parts[1].decode()
                    leave_group(sock,groupname)
                elif parts[0] == b"/share":
                    if len(parts) != 1:
                        sock.sendall(b"ERROR: /share command incorrectly formatted. Should be /share.\n")
                        continue
                    list_files(sock)
                else:
                    username = user_by_sock.get(sock,"UNKNOWN")
                    msg = f"[{username}] {data.decode(errors='replace')}"
                    data = msg.encode()
                    broadcast(data,[sock])
        for sock in exceptional:
            disconnect(sock,True)
