import sys, socket, threading
username = sys.argv[1]
hostname = sys.argv[2]
port = int(sys.argv[3])

prompt_ready = False

def recv_loop(sock:socket.socket):
    global prompt_ready
    while True:
        try:
            data = sock.recv(1024)
        except (ConnectionResetError,OSError):
            print("Disconnected (Connection reset).")
            break
        
        if not data:
            print("Server closed the connection.")
            break
        msg = data.decode(errors="replace")
        print("\n" + msg, end="", flush=True)

        if not prompt_ready:
            prompt_ready = True

        print(">>", end="", flush=True)



def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((hostname, port))

    s.sendall(f"HELLO {username}\n".encode())

    #Starts the recv thread
    t = threading.Thread(target=recv_loop, args=(s,),daemon=True)
    t.start()

    while True:
        if prompt_ready:
            print(">>",end="",flush=True)
        try:
            msg = input()
        except EOFError:
            msg = "/quit"
        
        if msg.strip() == "/quit":
            s.close() #also causes recv loop to exit
            break
        if not msg.strip():
            break
        s.sendall(f"{msg}\n".encode())

if __name__ == "__main__":
    main()

# with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
#     s.connect((hostname, port))
#     sts = "HELLO " + username + "\n"
#     s.sendall(sts.encode())
#     while True:
#         data = s.recv(1024)
#         if not data:
#             break
#         print(f"Server: {data.decode()}")
