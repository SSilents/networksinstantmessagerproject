import sys, socket, threading
username = sys.argv[1]
hostname = sys.argv[2]
port = int(sys.argv[3])

## Flags:
prompt_ready = False
quitting = False

input_allowed = threading.Event()
input_allowed.set()

def recv_loop(sock:socket.socket):
    global prompt_ready
    while True:
        try:
            data = sock.recv(1024)
        except (ConnectionResetError,OSError):
            if not quitting:
                print("\nDisconnected from server.")
            break
        
        if not data:
            if not quitting:
                print("\nServer closed the connection.")
            break
        msg = data.decode(errors="replace")
        print("\n" + msg, end="", flush=True)

        if "(shared) end" in msg:
            input_allowed.set()

        if not (msg.startswith("ERROR: ") or msg.startswith("(to ") or msg.startswith("(created group)") or msg.startswith("(joined group)") or msg.startswith("(shared)") or prompt_ready == False):
            print(">>",end="",flush=True)
        

        


        if not prompt_ready:
            prompt_ready = True
    



def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((hostname, port))

    s.sendall(f"HELLO {username}\n".encode())

    #Starts the recv thread
    t = threading.Thread(target=recv_loop, args=(s,),daemon=True)
    t.start()
    while not prompt_ready: pass
    while True:
        try:
            input_allowed.wait()
            msg = input(">>")
        except EOFError:
            msg = "/quit"
        
        if msg.strip() == "/quit":
            global quitting
            quitting = True
            s.sendall(b"QUIT\n")
            s.close() #also causes recv loop to exit
            break
        if msg.strip() == "/share":
            input_allowed.clear()
        if not msg.strip():
            continue
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
