from boto import ec2
import time
import sys
import paramiko
import threading

from PySide import QtGui, QtCore
from PySide.QtGui import QMainWindow, QPushButton, QApplication
 
from ui_manager import Ui_MainWindow


class ServerInstance:
    def __init__(self):
        self.conn = ec2.connect_to_region("us-east-1",
                                        aws_access_key_id="",
                                        aws_secret_access_key="")
                                        
        self.instance = None
        self.public_ip = None
        
    def get_running_instance(self):
        reservations = self.conn.get_all_instances()
        instances = [i for r in reservations for i in r.instances]

        for instance in instances:
                if "MinecraftServer" in instance.__dict__['tags']:
                    status = instance.update()
                    if status == "running":
                        return instance
        
        return None
        
    def start_instance(self,instance_type):
        print "Checking for running instances..."
        #Check if there is one up already
        instance = self.get_running_instance()
        if instance is not None:
            self.instance = instance
            addresses = self.conn.get_all_addresses()
            self.public_ip = addresses[0].public_ip
            print "Attached to running instance"
            return True
            
        print "No instances found. Starting a new instance..."
        
        #Start the instance
        reservations = self.conn.run_instances('ami-05355a6c',
                                    key_name='minecraftkeypair',
                                    instance_type=instance_type,
                                    security_groups=['Minecraft'],
                                    placement="us-east-1a")
                                    
        instance = reservations.instances[0]

        print('Waiting for instance to start (This may take up to five minutes)')
        # Check up on its status every so often
        status = instance.update()
        while status == 'pending':
            time.sleep(10)
            status = instance.update()
        if status == 'running':
            print('New instance "' + instance.id + '" accessible at ' + instance.public_dns_name)
        else:
            print('Instance status: ' + status)
            return False
        
        instance.add_tag("MinecraftServer","True") #Tag it so we can recognize it later
        
        addresses = self.conn.get_all_addresses()
        eip = ec2.address.Address(connection=self.conn, public_ip = addresses[0].public_ip)
        success = eip.associate(instance.id)
        self.public_ip = addresses[0].public_ip

        if success:
            print "Associated elastic ip " + addresses[0].public_ip
        else:
            print "Failed to associate elastic ip"
            return False

        success = self.conn.attach_volume("vol-90a8b0ca",instance.id,"/dev/sdh")
        if success:
            print "Attached ebs volume"
        else:
            print "Failed to attach ebs volume"
            return False
        
        self.instance = instance
        return True
        
    def stop_instance(self):
        self.conn.stop_instances([self.instance])
        
class Shell_SSH(object):
    def __init__(self, hostname, username, password, keyfile):
        self.connection = paramiko.SSHClient()
        self.connection.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        self.connection.connect(hostname, username=username, password=password, key_filename=keyfile)
        #transport = self.connection.get_transport()
        #transport.set_keepalive(30)
        
    def run_command(self, command):
        print "$ %s" %(command)
        stdin, stdout, stderr = self.connection.exec_command(command)
        stdin.close()
        
        for line in stdout.read().splitlines():
            print '> %s' %(  line)

    def close(self):
        self.connection.close()

    def start_shell(self):
        self.chan = self.connection.invoke_shell()

        sys.stdout.write("Line-buffered terminal emulation. Press F6 or ^Z to send EOF.\r\n\r\n")
            
        def writeall(sock):
            while True:
                data = sock.recv(256)
                if not data:
                    sys.stdout.write('\r\n*** EOF ***\r\n\r\n')
                    sys.stdout.flush()
                    break
                sys.stdout.write(data)
                sys.stdout.flush()
            
        writer = threading.Thread(target=writeall, args=(self.chan,))
        writer.start()
       
        #try:
        #    while True:
        #        d = sys.stdin.read(1)
        #        if not d:
        #            break
        #        chan.send(d)
        #except EOFError:
        #    # user hit ^Z or F6
        #    pass
            
    def write(self, text):
        for c in text:
            self.chan.send(c)
        self.chan.send('\n')
        
class MyStream(QtCore.QObject):
    message = QtCore.Signal(str)
    def __init__(self, parent=None):
        super(MyStream, self).__init__(parent)

    def write(self, message):
        self.message.emit(str(message))
        
    def flush(self):
        pass
        
 
class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)
        self.setupUi(self)

        self.launchButton.clicked.connect(self.launch_instance)
        self.shutdownButton.clicked.connect(self.shutdown_instance)
        self.typeComboBox.currentIndexChanged.connect(self.update_type)
        self.sendCommandLine.returnPressed.connect(self.enter_command)
        
        self.server = None
        self.sshcmd = None
        self.instance_type = self.typeComboBox.currentText().split()[0] # 

    def __del__(self):
        # Restore sys.stdout
        sys.stdout = sys.__stdout__
    
    @QtCore.Slot(str)
    def on_myStream_message(self, message):
        self.serverOutputTextEdit.moveCursor(QtGui.QTextCursor.End)
        self.serverOutputTextEdit.insertPlainText(message)
        QApplication.processEvents()
    
    def launch_instance(self):
        self.server = ServerInstance()
        self.server.start_instance(self.instance_type)
        
        print "Connecting to %s (This could take a while)" %(self.server.public_ip)
        count = 0
        while True:
            try:
                self.sshcmd = Shell_SSH(self.server.public_ip, 'ec2-user', '', "./minecraftkeypair.pem")
                break
            except:
                if count > 3:
                    raise
                count += 1
                pass
        self.sshcmd.start_shell()
        self.run_minecraft_server()
        
        
    def run_minecraft_server(self):
        
        self.sshcmd.write("mkdir /home/ec2-user/volume")
        self.sshcmd.write("sudo mount /dev/sdh /home/ec2-user/volume")
        self.sshcmd.write("sudo chmod -R 777 /home/ec2-user/volume")

        self.sshcmd.write("sudo ln -s /home/ec2-user/volume/msm/conf_files/m1.medium-msm.conf /etc/msm.conf")
        self.sshcmd.write("sudo mkdir /dev/shm/msm")
        self.sshcmd.write("sudo chmod -R 775 /dev/shm/msm")
        self.sshcmd.write("sudo /home/ec2-user/volume/msm/msm update")
        
    
    def shutdown_instance(self):
        self.server = ServerInstance()
        self.server.stop_instance()
    
    def update_type(self):
        self.instance_type = self.typeComboBox.currentText().split()[0]
        
    def enter_command(self):
        text = self.sendCommandLine.text()
        self.sendCommandLine.clear()
        self.sshcmd.write(text)
    
if __name__ == '__main__':
    app = QApplication(sys.argv)
    frame = MainWindow()
    frame.show()    
    
    myStream = MyStream()
    myStream.message.connect(frame.on_myStream_message)
    sys.stdout = myStream        
    
    app.exec_()
            
    