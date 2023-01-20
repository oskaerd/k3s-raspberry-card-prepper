import paramiko
import datetime as dt
import time


class NodeSshController:
    def __init__(self, ip, username = "rpi", password = "rpi"):
        print("Initializing SSH controller...")
        self.ip = ip
        self.password = password
        self.username = username

        # SSH connection
        try:
            self._ssh = paramiko.SSHClient()
            self._ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self._ssh.connect(ip, username=username, password=password)
        except paramiko.ssh_exception.NoValidConnectionsError:
            print(f"\tWARNING: Could not connect to the host {self.ip} - will be skipped")
            self._ssh = None
            return

    def sudo_command(self, command):
        streams = self._ssh.exec_command(f"sudo {command}", get_pty=True)
        # Small delay for password prompt to appear:
        time.sleep(1)
        streams[0].write(f"rpi\n")
        streams[0].flush()

        return streams

    def command(self, command):
        return self._ssh.exec_command(command)

    def __del__(self):
        if self._ssh is None:
            return
        print(f"Closing connection to remote {self.ip}")
        self._ssh.close()
