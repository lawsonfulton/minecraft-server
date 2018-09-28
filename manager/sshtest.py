import paramiko
import sys, threading

class Shell_SSH(object):
    def __init__(self, hostname, username, password, keyfile):
        self.connection = paramiko.SSHClient()
        self.connection.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        self.connection.connect(hostname, username=username, password=password, key_filename=keyfile)
    
    def run_command(self, command):
        print "$ %s" %(command)
        stdin, stdout, stderr = self.connection.exec_command(command)
        stdin.close()
        
        for line in stdout.read().splitlines():
            print '> %s' %(  line)

    def close(self):
        self.connection.close()

    def windows_shell(self, channnel, ):
        

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
            
        writer = threading.Thread(target=writeall, args=(chan,))
        writer.start()
            
        try:
            while True:
                d = sys.stdin.read(1)
                if not d:
                    break
                chan.send(d)
        except EOFError:
            # user hit ^Z or F6
            pass
        
if __name__ == '__main__':
    sshcmd = Shell_SSH('54.235.158.237', 'ec2-user', '', "./minecraftkeypair.pem")
    #sshcmd.run_command("ls")
    #sshcmd.run_command("cd ./server")
    #sshcmd.run_command("ls")
    chan = sshcmd.connection.invoke_shell()
    sshcmd.windows_shell(chan)
    
    sshcmd.close()