The server uses a SharedFiles directory located next to server.py.
Optionally, an environment variable SERVER_SHARED_FILES may be set
to override this location.

To broadcast messages to all connected users:
    Enter text with no preceding /command.
To send a private message to another single user (unicast):
    Enter "/to <username> <message>".
    <username> : username of another user connected to the server.
    <message> : the message you would like to send.
To join a group (or create a group if the group doesn't exist yet):
    Enter "/join <groupname>".
    <groupname>: the name of the group.
To leave a group you are a member of:
    Enter "/leave <groupname".
    <groupname>: the name of the group.
To send a message to a group you are a member of:
    Enter: "/group <groupname> <message>".
    <groupname>: the name of the group.
    <message> : the message you would like to send.
To see a list of all files in the shared folder:
    Enter: "/share".
To download a file from the shared folder:
    Enter: "/get <filename>".
    <filename> : The name of the file in the shared folder.
To change file downloading protocols:
    Enter: "/proto <protocol>".
    <protocol>: Either "tcp" or "udp".
    INFO: For UDP downloads, the client collects all packets using sequence numbers and completes the download once all sequence numbers are received or timeout occurs.
To disconnect client from the server:
    Enter: "/quit"

