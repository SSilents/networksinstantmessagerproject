import sys, socket
username = sys.argv[1]
hostname = sys.argv[2]
port = int(sys.argv[3])

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect((hostname, port))
    sts = "HELLO " + username + "\n"
    s.sendall(sts.encode())
    while True:
        data = s.recv(1024)
        if not data:
            break
        print(f"Server: {data.decode()}")
