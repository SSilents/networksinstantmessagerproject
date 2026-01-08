import sys, socket, threading, os

# Parse command-line arguments
username = sys.argv[1]
hostname = sys.argv[2]
port = int(sys.argv[3])

## Flags:
prompt_ready = False  # Tracks if initial connection handshake is complete
quitting = False  # Indicates client is shutting down

# Threading event to control when user input is allowed (prevents prompt during multi-line responses)
input_allowed = threading.Event()
input_allowed.set()

# Threading event to control when user disconnects (stops client code continuing looping through main)
disconnected = threading.Event()
disconnected.clear()

# Create user-specific download directory
DOWNLOAD_DIR = os.path.join(os.getcwd(), username)

# Default file transfer protocol
download_proto = "TCP"

if not os.path.isdir(DOWNLOAD_DIR):
    os.mkdir(DOWNLOAD_DIR)


def recv_loop(sock: socket.socket, udp_sock: socket.socket):
    """Background thread that receives all messages from the server via TCP and files via TCP/UDP"""
    global prompt_ready

    buf = b""  # TCP receive buffer (accumulates partial messages)

    while True:
        # Receive data from TCP socket
        try:
            data = sock.recv(4096)
        except (ConnectionResetError, OSError):
            if not quitting:
                print("\nDisconnected from server. Press Enter to exit.\n")
                disconnected.set()
                input_allowed.set()
            break

        if not data:
            if not quitting:
                print("Server closed the connection. Press Enter to exit.\n")
                disconnected.set()
                input_allowed.set()
            break

        buf += data

        # Process complete text lines (delimited by \n) from TCP buffer
        while b"\n" in buf:
            line_bytes, buf = buf.split(b"\n", 1)
            line = line_bytes.decode(errors="replace").strip()

            # Print server messages (chat, control messages, errors)
            print(line, flush=True)

            # Signal that /share listing is complete
            if line == "(shared) end":
                input_allowed.set()

            # File download header detected
            if line.startswith("(file) ok"):
                # Parse header: "(file) ok |filename| size Bytes"
                parts = line.split("|")
                if len(parts) < 3:
                    print("ERROR: bad file header", flush=True)
                    input_allowed.set()
                    continue

                filename = os.path.basename(parts[1].strip())
                size_str = parts[2].strip().split()[0]  # Extract size number
                size = int(size_str)

                filepath = os.path.join(DOWNLOAD_DIR, filename)

                # Download file using selected protocol
                if download_proto == "TCP":
                    # TCP: reliable stream, read exactly 'size' bytes
                    remaining = size
                    with open(filepath, "wb") as fp:
                        # First, consume any file data already in TCP buffer
                        if buf:
                            take = min(len(buf), remaining)
                            fp.write(buf[:take])
                            buf = buf[take:]
                            remaining -= take

                        # Continue reading until all bytes received
                        while remaining > 0:
                            chunk = sock.recv(min(4096, remaining))
                            if not chunk:
                                break
                            fp.write(chunk)
                            remaining -= len(chunk)

                elif download_proto == "UDP":
                    # UDP: unreliable, packets may arrive out-of-order or be lost
                    # Server sends 1000-byte data chunks with 4-byte sequence numbers
                    expected = (size + 1000 - 1) // 1000  # Total packets expected
                    chunks = {}  # seq_num -> payload dictionary
                    end_seen = False

                    while True:
                        try:
                            pkt, _ = udp_sock.recvfrom(4096)
                        except socket.timeout:
                            print(
                                f"ERROR: UDP timeout receiving {filename} ({len(chunks)}/{expected} packets)"
                            )
                            break

                        if len(pkt) < 4:
                            continue

                        # First 4 bytes = sequence number, rest = data payload
                        seq = int.from_bytes(pkt[:4], "big")
                        payload = pkt[4:]

                        # 0xFFFFFFFF marks end-of-transfer
                        if seq == 0xFFFFFFFF:
                            end_seen = True
                            # Don't break immediately - some packets may still arrive out-of-order
                            if len(chunks) >= expected:
                                break
                            continue

                        # Store packet if in valid range and not a duplicate
                        if 0 <= seq < expected and seq not in chunks:
                            chunks[seq] = payload

                        # Exit once all expected packets received
                        if len(chunks) >= expected:
                            break

                        # If end marker seen and all packets collected, finish
                        if end_seen and len(chunks) >= expected:
                            break

                    # Write packets in sequence order to file
                    with open(filepath, "wb") as fp:
                        for i in range(expected):
                            if i in chunks:
                                fp.write(chunks[i])
                            else:
                                # Missing packet = incomplete file
                                break

                # Report actual downloaded size
                actual = os.path.getsize(filepath) if os.path.exists(filepath) else 0
                print(f"(file) downloaded {filename} ({actual} bytes)", flush=True)
                input_allowed.set()

            # Mark that initial connection is ready
            if not prompt_ready:
                prompt_ready = True

        if not prompt_ready:
            prompt_ready = True


def main():
    """Main client loop: connect, handshake, handle user input"""
    global download_proto

    # Establish TCP control connection
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((hostname, port))

    # Send username to server
    s.sendall(f"HELLO {username}\n".encode())

    # Create UDP socket for file transfers and register port with server
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.bind(("", 0))  # Bind to ephemeral port
    udp_port = udp_sock.getsockname()[1]
    udp_sock.settimeout(10.0)

    s.sendall(f"UDPPORT {udp_port}\n".encode())

    # Start background thread to receive messages and files
    t = threading.Thread(target=recv_loop, args=(s, udp_sock), daemon=True)
    t.start()

    # Wait for connection to be established
    while not prompt_ready:
        pass

    # Main input loop
    while True:
        try:
            input_allowed.wait()  # Block if waiting for multi-line response
            msg = input(">>")
        except EOFError:
            msg = "/quit"
        
        if disconnected.is_set():
            break

        # Handle quit command
        if msg.strip() == "/quit":
            global quitting
            quitting = True
            s.sendall(b"QUIT\n")
            s.close()
            break

        # Commands that expect multi-line responses - block input until complete
        if msg.strip() == "/share":
            input_allowed.clear()
        if "/get" in msg.strip():
            input_allowed.clear()

        # Update local protocol setting when user changes it
        if "/proto tcp" in msg.strip():
            download_proto = "TCP"
        if "/proto udp" in msg.strip():
            download_proto = "UDP"

        # Don't send empty messages
        if not msg.strip():
            continue

        # Send command/message to server
        s.sendall(f"{msg}\n".encode())


if __name__ == "__main__":
    main()
