import sys, socket, threading, os
username = sys.argv[1]
hostname = sys.argv[2]
port = int(sys.argv[3])

## Flags:
prompt_ready = False
quitting = False

input_allowed = threading.Event()
input_allowed.set()

DOWNLOAD_DIR = os.path.join(os.getcwd(),username)

download_proto = "TCP"

if not os.path.isdir(DOWNLOAD_DIR):
    os.mkdir(DOWNLOAD_DIR)

def recv_loop(sock: socket.socket, udp_sock: socket.socket):
    global prompt_ready

    buf = b""  # raw TCP buffer (bytes)

    while True:
        try:
            data = sock.recv(4096)
        except (ConnectionResetError, OSError):
            if not quitting:
                print("\nDisconnected from server.")
            break

        if not data:
            if not quitting:
                print("\nServer closed the connection.")
            break

        buf += data

        # Process complete text lines from TCP buffer
        while b"\n" in buf:
            line_bytes, buf = buf.split(b"\n", 1)
            line = line_bytes.decode(errors="replace").strip()

            # Print the line (control / chat messages)
            print(line, flush=True)

            if line == "(shared) end":
                input_allowed.set()

            # File header line
            if line.startswith("(file) ok"):
                # Your server sends: "(file) ok |{filename}| {size} Bytes"
                parts = line.split("|")
                if len(parts) < 3:
                    print("ERROR: bad file header", flush=True)
                    input_allowed.set()
                    continue

                filename = os.path.basename(parts[1].strip())
                # parts[2] starts with "<size> Bytes"
                size_str = parts[2].strip().split()[0]
                size = int(size_str)

                filepath = os.path.join(DOWNLOAD_DIR, filename)

                # Now receive file bytes based on selected protocol
                if download_proto == "TCP":
                    remaining = size
                    with open(filepath, "wb") as fp:
                        # consume any leftover bytes already in TCP buffer
                        if buf:
                            take = min(len(buf), remaining)
                            fp.write(buf[:take])
                            buf = buf[take:]
                            remaining -= take

                        while remaining > 0:
                            chunk = sock.recv(min(4096, remaining))
                            if not chunk:
                                break
                            fp.write(chunk)
                            remaining -= len(chunk)

                elif download_proto == "UDP":
                    expected = (size + 1000 - 1) // 1000  # server uses 1000-byte UDP payloads
                    chunks = {}
                    end_seen = False

                    while True:
                        try:
                            pkt, _ = udp_sock.recvfrom(4096)
                        except socket.timeout:
                            print(f"ERROR: UDP timeout receiving {filename} ({len(chunks)}/{expected} packets)")
                            break

                        if len(pkt) < 4:
                            continue

                        seq = int.from_bytes(pkt[:4], "big")
                        payload = pkt[4:]

                        if seq == 0xFFFFFFFF:
                            end_seen = True
                            # don't break immediately; some data may still be in flight/out-of-order
                            if len(chunks) >= expected:
                                break
                            continue

                        if 0 <= seq < expected and seq not in chunks:
                            chunks[seq] = payload

                        if len(chunks) >= expected:
                            break

                        # If END arrived and we already have everything, we can finish
                        if end_seen and len(chunks) >= expected:
                            break

                    with open(filepath, "wb") as fp:
                        for i in range(expected):
                            if i in chunks:
                                fp.write(chunks[i])
                            else:
                                # missing packet => incomplete file
                                break

                actual = os.path.getsize(filepath) if os.path.exists(filepath) else 0
                print(f"(file) downloaded {filename} ({actual} bytes)", flush=True)
                input_allowed.set()

            if not prompt_ready:
                prompt_ready = True



        



        # if not (msg.startswith("ERROR: ") or msg.startswith("(to ") or msg.startswith("(created group)") or msg.startswith("(joined group)") or msg.startswith("(shared)") or msg.startswith("(file)") or prompt_ready == False):
        #     print(">>",end="",flush=True)


        if not prompt_ready:
            prompt_ready = True
    



def main():
    global download_proto
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((hostname, port))

    s.sendall(f"HELLO {username}\n".encode())

    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.bind(("",0))
    udp_port = udp_sock.getsockname()[1]
    udp_sock.settimeout(10.0)

    s.sendall(f"UDPPORT {udp_port}\n".encode())

    #Starts the recv thread
    t = threading.Thread(target=recv_loop, args=(s,udp_sock),daemon=True)
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
        if "/get" in msg.strip():
            input_allowed.clear()
        if "/proto tcp" in msg.strip():
            download_proto = "TCP"
        if "/proto udp" in msg.strip():
            download_proto = "UDP"
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
