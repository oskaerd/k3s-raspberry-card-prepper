from .ssh_controller import NodeSshController
import time
from abc import ABC, abstractmethod




class K3sNode:
    def __init__(self, username, node_name, ip):
        self.node_name = node_name
        self.ip = ip
        self.username = username
        self.connection_failed = False

        # SSH connection
        print(f"\tConnecting to target node {ip}")
        self.ssh = NodeSshController(ip, username)
        if self.ssh is None:
            self.connection_failed = True

    def overwrite_firmware_config_files(self, config_files_dir = '/boot/firmware'):
        print("\tAppending required flags to config files.")

        # filename, check for, modify command:
        file_tuples = [
            # /boot/firmware/config.txt
            ("config.txt", 'add arm_64bit=1', "echo \'add arm_64bit=1\' | tee -a config.txt"),
            # /boot/firmware/cmdline.txt
            ("cmdline.txt", "cgroup_enable=memory", "echo $(cat cmdline.txt) cgroup_memory=1 cgroup_enable=memory > cmdline.txt")
        ]

        for file_tuple in file_tuples:
            print(f"\tModifying {config_files_dir}/{file_tuple[0]}", end='')
            # check if flags have not been already set in the file:
            streams = self.ssh.command(f"grep \'{file_tuple[1]}\' {config_files_dir}/{file_tuple[0]}")
            if streams[1].read().decode('utf-8') == '':
                self.ssh.command(f"cp {config_files_dir}/{file_tuple[0]} .")
                self.ssh.command(f"{file_tuple[2]}")
                streams = self.ssh.sudo_command(f"mv {file_tuple[0]} {config_files_dir}")
                # This read is needed for file to be moved.
                streams[1].read().decode('utf-8')
                print('. Done')
            else:
                print(f" - flags already present. Skipping.")

    def prepare_k3s_config_file(self):
        # Not applicable for the worker node.
        pass

    def set_ip_tables(self):
        print("\tConfiguring legacy IP tables.", end='')
        self.ssh.sudo_command("iptables -F")
        self.ssh.sudo_command("update-alternatives --set iptables /usr/sbin/iptables-legacy")
        self.ssh.sudo_command("update-alternatives --set ip6tables /usr/sbin/ip6tables-legacy")
        print(" Done.\n\tInstalling missing Ubuntu kernel packages for raspberry (takes up to 10 minutes).")

    def install_required_modules(self, verbose = False):
        # Don't really need to check if these are already installed.
        # If so, the package will just get skipped so we're fine.
        # -y to skip prompt if one wants to install the package
        # curl usually is installed on RPis but make sure for other platforms:
        streams = self.ssh.sudo_command("apt install -y curl")
        streams[1].readlines()

        # Below takes some noticable time (~6 minutes) to complete.
        # DEBIAN_FRONTEND=noninteractive - disables interactive prompt for the reset. Since the prompt is visual
        # it causes the tool to hang for stdout flush despite module getting installed.
        streams = self.ssh.sudo_command("DEBIAN_FRONTEND=noninteractive apt install -y linux-modules-extra-raspi")

        # Blocking until the command is completed
        for line in streams[1].readlines():
            # Not recommended to go verbose here, once the lines got flushed
            # python shell hang and became non-responsive.
            # TODO: remove, leave just readlines
            if verbose:
                print(line, end='')

        if not verbose:
            print('\tDone. \n\tRebooting.')
        self.reboot_and_reconnect()

    def reboot_and_reconnect(self):
        reconnected = False
        streams = self.ssh.sudo_command("reboot")
        # TODO method for that
        try:
            streams[1].readlines()
            reconnected = True
        except:
            print(f"Lost connection to the device {self.rpi}")
            self.ssh.ssh.close()

        # some delay for RPi to reboot
        time.sleep(60)
        if reconnected:
            print('\tReconnected')
        # TODO method for that
        self.ssh.ssh.connect(self.ip, username="rpi", password="rpi")

    def install_k3s(self):
        pass

    def write_final_k3s_config_file(self):
        print('TODO')

    def get_controller_key(self):
        # TODO: This needs to reach out to K3sRpiConfigurator to get the controller key
        pass

    def __str__(self):
        return f"IP: {self.ip}, name: {self.node_name} - node"



class K3sControllerNode(K3sNode):
    def __init__(self, username, node_name, ip):
        super().__init__(username, node_name, ip)

    def prepare_k3s_config_file(self):
        print("\tPreparing K3s config directory and files.")
        self.ssh.command("mkdir .kube")
        # Append export of K3s config path to the .bashrc file.
        self.ssh.command(f"echo \"export KUBECONFIG=/home/{self.username}/.kube/config\" >> ~/.bashrc")
        # Source to have the variable available in current session
        self.ssh.command("source ~/.bashrc")

    def install_k3s(self):
        print('\tInstalling K3s on the controller node.')
        # TODO: 1.2.4 Version is hardcoded, parametrize it later on:
        streams = self.ssh.sudo_command("curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=\"v1.24.9+k3s1\" K3S_KUBECONFIG_MODE=\"644\" sh -s -")
        print(streams[1].readlines())

    def write_final_k3s_config_file(self):
        print("\tCopying k3s.yaml to config directory and setting node's IP address.")
        self.ssh.command(f"cp /etc/rancher/k3s/k3s.yaml /home/{self.username}/.kube/config")
        self.ssh.command(f"sed -i -r \'s/(\\b[0-9]{{1,3}}\\.){{3}}[0-9]{{1,3}}\\b\'/{self.ip}/ /home/{self.username}/.kube/config")

    def helm_install_with_repositories(self):
        repo_commands = [
            "add rancher-latest https://releases.rancher.com/server-charts/latest",
            "add jetstack https://charts.jetstack.io",
            "update"
        ]
        print("\tInstalling helm and required repositories:", end='')
        streams = self.ssh.sudo_command("curl https://raw.githubusercontent.com/helm/helm/master/scripts/get-helm-3 | bash")
        streams[1].readlines()

        for cmd in repo_commands:
            streams = self.ssh.command(f"helm repo {cmd}")
            streams[1].readlines()

        print(' Done.')

    def create_rancher_namespaces(self):
        rancher_namespaces = [
            "cattle-system",
            "cert-manager"
        ]

        print("\tCreating rancher namespaces.", end='')

        for ns in rancher_namespaces:
            streams = self.ssh.command(f"kubectl create namespace {ns}")
            streams[1].readlines()

        print(' Done')

    def install_cert_manager(self):
        commands = [
            "kubectl apply --validate=false -f https://github.com/jetstack/cert-manager/releases/download/v1.2.0-alpha.2/cert-manager.crds.yaml",
            "helm install cert-manager jetstack/cert-manager --namespace cert-manager",
            "kubectl get pods --namespace cert-manager"
        ]
        print("\tInstalling cert manager:", end='')
        for cmd in commands:
            streams = self.ssh.command(cmd)
            result = streams[1].readlines()
        print(" Done.")

    def __str__(self):
        return f"IP: {self.ip}, name: {self.node_name} - controller"

    def get_controller_key(self):
        pass