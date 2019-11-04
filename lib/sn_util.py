#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import logging
import shutil
import subprocess
import pwd
import socket
import re
from gi.repository import GLib
from gi.repository import GObject


class SnUtil:

    @staticmethod
    def getGatewayInterface():
        ret = FcsUtil.shell("/bin/route -n4", "stdout")
        # syntax: DestIp GatewayIp DestMask ... OutIntf
        m = re.search("^(0\\.0\\.0\\.0)\\s+([0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+)\\s+(0\\.0\\.0\\.0)\\s+.*\\s+(\\S+)$", ret, re.M)
        if m is None:
            return None
        return m.group(4)

    @staticmethod
    def getGatewayIpAddress():
        ret = FcsUtil.shell("/bin/route -n4", "stdout")
        # syntax: DestIp GatewayIp DestMask ... OutIntf
        m = re.search("^(0\\.0\\.0\\.0)\\s+([0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+)\\s+(0\\.0\\.0\\.0)\\s+.*\\s+(\\S+)$", ret, re.M)
        if m is None:
            return None
        return m.group(2)

    @staticmethod
    def getUidGidMinMaxInfo():
        uidMin = -1
        uidMax = -1
        gidMin = -1
        gidMax = -1

        buf = ""
        with open("/etc/login.defs", "r") as f:
            buf = f.read()

        for line in buf.split("\n"):
            m = re.search("^UID_MIN\s+([0-9]+)", line)
            if m is not None:
                uidMin = int(m.group(1))
            m = re.search("^UID_MAX\s+([0-9]+)", line)
            if m is not None:
                uidMax = int(m.group(1))
            m = re.search("^GID_MIN\s+([0-9]+)", line)
            if m is not None:
                gidMin = int(m.group(1))
            m = re.search("^GID_MAX\s+([0-9]+)", line)
            if m is not None:
                gidMax = int(m.group(1))

        assert uidMin != -1 and uidMax != -1 and gidMin != -1 and gidMax != -1
        return (uidMin, uidMax, gidMin, gidMax)

    @staticmethod
    def getNormalUserList():
        uidMin, uidMax, gidMin, gidMax = SnUtil.getUidGidMinMaxInfo()

        ret = []
        for pw in pwd.getpwall():
            if uidMin <= pw.pw_uid <= uidMax:
                ret.append(pw.pw_name)
        return ret

    @staticmethod
    def addLinePrefix(tstr, prefix):
        return prefix + ("\n" + prefix).join(tstr.split("\n"))

    @staticmethod
    def getSysctl(name):
        msg = SnUtil.shell("/sbin/sysctl -n %s" % (name), "stdout")
        return msg.rstrip('\n')

    @staticmethod
    def setSysctl(name, value):
        return

    @staticmethod
    def copyToDir(srcFilename, dstdir, mode=None):
        """Copy file to specified directory, and set file mode if required"""

        if not os.path.isdir(dstdir):
            os.makedirs(dstdir)
        fdst = os.path.join(dstdir, os.path.basename(srcFilename))
        shutil.copy(srcFilename, fdst)
        if mode is not None:
            SnUtil.shell("/bin/chmod " + mode + " \"" + fdst + "\"")

    @staticmethod
    def copyToFile(srcFilename, dstFilename, mode=None):
        """Copy file to specified filename, and set file mode if required"""

        if not os.path.isdir(os.path.dirname(dstFilename)):
            os.makedirs(os.path.dirname(dstFilename))
        shutil.copy(srcFilename, dstFilename)
        if mode is not None:
            SnUtil.shell("/bin/chmod " + mode + " \"" + dstFilename + "\"")

    @staticmethod
    def readFile(filename):
        """Read file, returns the whold content"""

        f = open(filename, 'r')
        buf = f.read()
        f.close()
        return buf

    @staticmethod
    def writeFile(filename, buf, mode=None):
        """Write buffer to file"""

        f = open(filename, 'w')
        f.write(buf)
        f.close()
        if mode is not None:
            SnUtil.shell("/bin/chmod " + mode + " \"" + filename + "\"")

    @staticmethod
    def mkDir(dirname):
        if not os.path.isdir(dirname):
            SnUtil.forceDelete(dirname)
            os.mkdir(dirname)

    @staticmethod
    def mkDirAndClear(dirname):
        SnUtil.forceDelete(dirname)
        os.mkdir(dirname)

    @staticmethod
    def touchFile(filename):
        assert not os.path.exists(filename)
        f = open(filename, 'w')
        f.close()

    @staticmethod
    def forceDelete(filename):
        if os.path.islink(filename):
            os.remove(filename)
        elif os.path.isfile(filename):
            os.remove(filename)
        elif os.path.isdir(filename):
            shutil.rmtree(filename)

    @staticmethod
    def forceSymlink(source, link_name):
        if os.path.exists(link_name):
            os.remove(link_name)
        os.symlink(source, link_name)

    @staticmethod
    def getFreeSocketPort(portType, portStart, portEnd):
        if portType == "tcp":
            sType = socket.SOCK_STREAM
        elif portType == "udp":
            assert False
        else:
            assert False

        for port in range(portStart, portEnd + 1):
            s = socket.socket(socket.AF_INET, sType)
            try:
                s.bind((('', port)))
                return port
            except socket.error:
                continue
            finally:
                s.close()
        raise Exception("No valid %s port in [%d,%d]." % (portType, portStart, portEnd))

    @staticmethod
    def shell(cmd, flags=""):
        """Execute shell command"""

        assert cmd.startswith("/")

        # Execute shell command, throws exception when failed
        if flags == "":
            retcode = subprocess.Popen(cmd, shell=True).wait()
            if retcode != 0:
                raise Exception("Executing shell command \"%s\" failed, return code %d" % (cmd, retcode))
            return

        # Execute shell command, throws exception when failed, returns stdout+stderr
        if flags == "stdout":
            proc = subprocess.Popen(cmd,
                                    shell=True,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT)
            out = proc.communicate()[0]
            if proc.returncode != 0:
                raise Exception("Executing shell command \"%s\" failed, return code %d" % (cmd, proc.returncode))
            return out

        # Execute shell command, returns (returncode,stdout+stderr)
        if flags == "retcode+stdout":
            proc = subprocess.Popen(cmd,
                                    shell=True,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT)
            out = proc.communicate()[0]
            return (proc.returncode, out)

        assert False

    @staticmethod
    def shellInteractive(cmd, strInput, flags=""):
        """Execute shell command with input interaction"""

        assert cmd.startswith("/")

        # Execute shell command, throws exception when failed
        if flags == "":
            proc = subprocess.Popen(cmd,
                                    shell=True,
                                    stdin=subprocess.PIPE)
            proc.communicate(strInput)
            if proc.returncode != 0:
                raise Exception("Executing shell command \"%s\" failed, return code %d" % (cmd, proc.returncode))
            return

        # Execute shell command, throws exception when failed, returns stdout+stderr
        if flags == "stdout":
            proc = subprocess.Popen(cmd,
                                    shell=True,
                                    stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT)
            out = proc.communicate(strInput)[0]
            if proc.returncode != 0:
                raise Exception("Executing shell command \"%s\" failed, return code %d, output %s" % (cmd, proc.returncode, out))
            return out

        # Execute shell command, returns (returncode,stdout+stderr)
        if flags == "retcode+stdout":
            proc = subprocess.Popen(cmd,
                                    shell=True,
                                    stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT)
            out = proc.communicate(strInput)[0]
            return (proc.returncode, out)

        assert False

    @staticmethod
    def ipMaskToLen(mask):
        """255.255.255.0 -> 24"""

        netmask = 0
        netmasks = mask.split('.')
        for i in range(0, len(netmasks)):
            netmask *= 256
            netmask += int(netmasks[i])
        return 32 - (netmask ^ 0xFFFFFFFF).bit_length()

    @staticmethod
    def dropPriviledgeTo(userName):
        assert os.getuid() == 0
        pwobj = pwd.getpwnam(userName)
        os.setgid(pwobj.pw_gid)
        os.setuid(pwobj.pw_uid)

    @staticmethod
    def euidInvoke(userName, func, *args):
        if userName is not None:
            oldeuid = os.geteuid()
            oldegid = os.getegid()
            pwobj = pwd.getpwnam(userName)
            try:
                os.setegid(pwobj.pw_gid)
                os.seteuid(pwobj.pw_uid)

                return func(*args)
            finally:
                os.seteuid(oldeuid)
                os.setegid(oldegid)
        else:
            return func(*args)

    @staticmethod
    def idleInvoke(func, *args):
        def _idleCallback(func, *args):
            func(*args)
            return False
        GLib.idle_add(_idleCallback, func, *args)

    @staticmethod
    def timeoutInvoke(timeout, func, *args):
        def _timeoutCallback(func, *args):
            func(*args)
            return False
        GObject.timeout_add_seconds(timeout, _timeoutCallback, func, *args)

    @staticmethod
    def checkSshPubKey(pubkey, keyType, userName, hostName):
        if keyType == "rsa":
            prefix = "ssh-rsa"
        elif keyType == "dsa":
            prefix = "ssh-dss"
        elif keyType == "ecdsa":
            prefix = "ecdsa-sha2-nistp256"
        else:
            assert False

        strList = pubkey.split()
        if len(strList) != 3:
            return False
        if strList[0] != prefix:
            return False
        if strList[2] != "%s@%s" % (userName, hostName):
            return False
        return True

    @staticmethod
    def initSshKeyFile(keyType, userName, hostName, privkeyFile, pubkeyFile):
        needInit = False
        if not os.path.exists(privkeyFile) or not os.path.exists(pubkeyFile):
            needInit = True
        if os.path.exists(pubkeyFile):
            with open(pubkeyFile, "rt") as f:
                pubkey = f.read()
                if not SnUtil.checkSshPubKey(pubkey, keyType, userName, hostName):
                    needInit = True

        if needInit:
            comment = "%s@%s" % (userName, hostName)
            SnUtil.forceDelete(privkeyFile)
            SnUtil.forceDelete(pubkeyFile)

            # fixme don't know why euid can't be child's uid
            #SnUtil.shell("/bin/ssh-keygen -t %s -N \"\" -C \"%s\" -f \"%s\" -q"%(keyType, comment, privkeyFile), "stdout")
            SnUtil.shell("/bin/su -m %s -c \"/usr/bin/ssh-keygen -t %s -N \\\"\\\" -C \\\"%s\\\" -f \\\"%s\\\" -q\"" % (userName, keyType, comment, privkeyFile), "stdout")

            assert os.path.exists(privkeyFile) and os.path.exists(pubkeyFile)

    @staticmethod
    def getSslSocketPeerName(sslSock):
        cert = sslSock.get_peer_certificate()
        if cert is None:
            return None
        subject = cert.get_subject()
        if subject is None:
            return None
        return subject.CN

    @staticmethod
    def getPidBySocket(socketInfo):
        """need to be run by root. socketInfo is like 0.0.0.0:80"""

        rc, ret = SnUtil.shell("/bin/netstat -anp | grep \"%s\"" % (socketInfo), "retcode+stdout")
        if rc != 0:
            return -1

        m = re.search(" +([0-9]+)/.*$", ret, re.MULTILINE)
        assert m is not None
        return int(m.group(1))

    @staticmethod
    def dbusGetUserName(connection, sender):
        if sender is None:
            return None
        uid = connection.get_unix_user(sender)
        return pwd.getpwuid(uid).pw_name

    @staticmethod
    def cbConditionToStr(cb_condition):
        ret = ""
        if cb_condition & GLib.IO_IN:
            ret += "IN "
        if cb_condition & GLib.IO_OUT:
            ret += "OUT "
        if cb_condition & GLib.IO_PRI:
            ret += "PRI "
        if cb_condition & GLib.IO_ERR:
            ret += "ERR "
        if cb_condition & GLib.IO_HUP:
            ret += "HUP "
        if cb_condition & GLib.IO_NVAL:
            ret += "NVAL "
        return ret

    @staticmethod
    def getLoggingLevel(logLevel):
        if logLevel == "CRITICAL":
            return logging.CRITICAL
        elif logLevel == "ERROR":
            return logging.ERROR
        elif logLevel == "WARNING":
            return logging.WARNING
        elif logLevel == "INFO":
            return logging.INFO
        elif logLevel == "DEBUG":
            return logging.DEBUG
        else:
            assert False

    @staticmethod
    def recvLine(sock):
        buf = bytes()
        while True:
            buf2 = sock.recv(1)
            if len(buf2) == 0 or buf2 == b'\n':
                break
            buf += buf2
        return buf


# this socket add watch into GLib default mainloop
# this socket requires logging module be prepared
class PipeObjSocket:

    def __init__(self, fin, fout, recvFunc):
        self.flagError = GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP | GLib.IO_NVAL

        self.fin = fin
        self.fout = fout
        self.recvFunc = recvFunc

        self.recvBuffer = b''
        self.recvSourceId = GLib.io_add_watch(self.fin, GLib.IO_IN | self.flagError, self._onRecv)

    def send(self, data):
        assert self.fin is not None

        data = pickle.dumps(data)
        header = struct.pack("!I", len(data))
        packet = header + data
        self.fout.write(packet)
        self.fout.flush()

    def close(self):
        GLib.source_remove(self.recvSourceId)
        self.fin = None

    def _onRecv(self, source, cb_condition):
        if self.fin is None:
            return False

        if cb_condition & self.flagError:
            logging.error("StdinStdoutObjSocket._onRecv, %s" % (SnUtil.cbConditionToStr(cb_condition)))
            return False

        try:
            # receive
            self.recvBuffer += self.fin.read()

            # get packet header
            headerLen = struct.calcsize("!I")
            if len(self.recvBuffer) < headerLen:
                return True

            # get packet data
            dataLen = struct.unpack("!I", self.recvBuffer[:headerLen])[0]
            totalLen = headerLen + dataLen
            if len(self.recvBuffer) < totalLen:
                return True
            data = self.recvBuffer[headerLen:totalLen]
            self.recvBuffer = self.recvBuffer[totalLen:]

            # invoke callback function
            self.recvFunc(pickle.loads(data))
            return True
        except:
            logging.error(traceback.format_exc())
            return False


# this socket requires full control of sys.stdin and sys.stdout
class StdinStdoutObjSocket(PipeObjSocket):

    def __init__(self, recvFunc):
        fcntl.fcntl(sys.stdin, fcntl.F_SETFL, os.O_NONBLOCK)
        super(PipeObjSocket, self).__init__(sys.stdin, sys.stdout, recvFunc)


class ReliableUdpObjSocket:

    RETRY_TIMEOUT = 10
    BUFFER_SIZE = 4096

    PKT_FLAG_DATA = 0
    PKT_FLAG_ACK = 1

    def __init__(self, localIp, localPort, recvFunc):
        self.flagError = GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP | GLib.IO_NVAL

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((localIp, localPort))

        self.sendTimer = GObject.timeout_add_seconds(1, self._onSend)
        self.recvSourceId = GLib.io_add_watch(self.socket, GLib.IO_IN | self.flagError, self._onRecv)
        self.recvFunc = recvFunc
        self.channels = dict()

    def connect(ip, port):
        assert self.socket is not None
        self.__createChannel((ip, port))

    def drop(ip, port):
        assert self.socket is not None
        del self.channels[(ip, port)]

    def send(ip, port, data):
        assert self.socket is not None
        assert (ip, port) in self.channels

        addr = (ip, port)
        ch = self.channels[addr]

        # serialize data
        data = pickle.dumps(data)
        header = struct.pack("!I", len(data))
        packet = header + data

        # add data into queue, send if possible
        ch["pending_buffer"] += packet
        if ch["sent_buffer"] is None:
            self.__chSend(ch)

    def close(self):
        assert self.socket is not None

        GLib.source_remove(self.sendTimer)
        GLib.recvSourceId(self.recvSourceId)
        self.socket.close()
        self.socket = None

    def _onSend(self):
        if self.socket is None:
            return False

        for addr, ch in self.channels.items():
            if ch["sent_buffer"] is not None:
                if ch["timeout"] > self.RETRY_TIMEOUT:
                    self.socket.sendto(ch["sent_buffer"], addr)
                    ch["timeout"] = 0
                else:
                    ch["timeout"] += 1
            else:
                if ch["pending_buffer"] != b'':
                    self.__chSend(ch)
        return True

    def _onRecv(self, source, cb_condition):
        if self.socket is None:
            return False

        if cb_condition & self.flagError:
            logging.error("ReliableUdpObjSocket._onRecv, %s" % (SnUtil.cbConditionToStr(cb_condition)))
            return False

        try:
            headerLen = struct.calcsize("!BB")

            # receive
            data, addr = self.socket.recvfrom(self.BUFFER_SIZE)
            if addr not in self.channels:
                self.__createChannel(addr)
            ch = self.channels[addr]

            # data packet
            if struct.unpack("!BB", data[:headerLen])[0] == self.PKT_FLAG_DATA:
                code_next = (ch["code_in"] + 1) % 256
                if struct.unpack("!BB", data[:headerLen])[1] != code_next:
                    return True                                                         # invalid code, drop packet
                ch["recv_buffer"] += data[headerLen:]
                ch["code_in"] = code_next

                # send ack
                ackPkt = struct.pack("!BB", self.PKG_FLAG_ACK, code_next)
                self.socket.sendto(ackPkt, addr)

                # get packet header
                headerLen = struct.calcsize("!I")
                if len(ch["recv_buffer"]) < headerLen:
                    return True

                # get packet data
                dataLen = struct.unpack("!I", ch["recv_buffer"][:headerLen])[0]
                totalLen = headerLen + dataLen
                if len(ch["recv_buffer"]) < totalLen:
                    return True
                data = ch["recv_buffer"][headerLen:totalLen]
                ch["recv_buffer"] = ch["recv_buffer"][totalLen:]

                # invoke callback function
                ip, port = addr
                self.recvFunc(ip, port, pickle.loads(data))
                return True

            # ack packet
            if struct.unpack("!BB", data[:headerLen])[0] == self.PKT_FLAG_ACK:
                if struct.unpack("!BB", data[:headerLen])[1] != ch["code_out"]:
                    return True                                                         # invalid code, drop packet
                ch["sent_buffer"] = None
                ch["code_out"] = (ch["code_out"] + 1) % 256
                return True

            # invalid flag, drop packet
            return True
        except:
            logging.error(traceback.format_exc())
            return False

    def __createChannel(self, addr):
        self.channels[addr] = {
            # information for sending
            "pending_buffer": b'',
            "sent_buffer": None,
            "timeout": 0,
            "code_out": 1,
            # information for receiving
            "recv_buffer": b'',
            "code_in": 0,
        }

    def __chSend(self, ch):
        headerLen = struct.calcsize("!BB")
        dataLen = min(self.BUFFER_SIZE, len(ch["pending_buffer"])) - headerLen
        ch["sent_buffer"] = struct.pack("!BB", self.PKT_FLAG_DATA, ch["code_out"]) + ch["pending_buffer"][:dataLen]
        ch["pending_buffer"] = ch["pending_buffer"][dataLen:]
        self.socket.sendto(ch["sent_buffer"], addr)
        ch["timeout"] = 0


class MulticastObjSocket:

    BUFFER_SIZE = 4096

    def __init__(self, multicastIp, multicastPort, recvFunc):
        self.flagError = GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP | GLib.IO_NVAL

        self.ip = multicastIp
        self.port = multicastPort
        self.recvFunc = recvFunc

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, struct.pack('b', 1))
        self.socket.bind((self.ip, self.port))
        self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, struct.pack('4sL', socket.inet_aton((self.ip, self.port)), socket.INADDR_ANY))

# sock.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_IF, socket.inet_aton(host))
#   sock.setsockopt(socket.SOL_IP, socket.IP_ADD_MEMBERSHIP, 
#                    socket.inet_aton(MCAST_GRP) + socket.inet_aton(host))
# https://pypi.org/project/py-multicast/

        self.recvSourceId = GLib.io_add_watch(self.sock, GLib.IO_IN | self.flagError, self._onRecv)

    def close(self):
        assert self.sock is not None
        GLib.source_remove(self.recvSourceId)
        self.socket.close()
        self.sock = None

    def send(self, data):
        self.socket.sendto(pickle.dumps(data), (self.ip, self.port)) 

    def _onRecv(self, source, cb_condition):
        if self.socket is None:
            return False

        if cb_condition & self.flagError:
            logging.error("MulticastObjSocket._onRecv, %s" % (SnUtil.cbConditionToStr(cb_condition)))
            return False

        try:
            data, addr = self.socket.recvfrom(self.BUFFER_SIZE)
            self.recvFunc(pickle.loads(data))
            return True
        except:
            logging.error(traceback.format_exc())
            return False


class SnSleepNotifier:

    SLEEP_TYPE_SUSPEND = 0
    SLEEP_TYPE_HIBERNATE = 1
    SLEEP_TYPE_HYBRID_SLEEP = 2

    def __init__(self, cbBeforeSleep, cbAfterResume):
        self.cbBeforeSleep = cbBeforeSleep
        self.cbAfterResume = cbAfterResume

    def dispose(self):
        pass


class SgwApiClient:

    def __init__(self, ip, peerList, upCallback, downCallback):
        self.peerList = peerList
        self.upCallback = upCallback
        self.downCallback = downCallback

        self.thread = _SgwApiClientThread()
        self.thread.start()

        self.activePeerDict = dict()
        self.sock = None
        self.state = 0                      # 1: get-sock-list command pending; 2: wakup-host command pending

    def isGood(self):
        return (self.thread.sock is not None)

    def cmdWakeup(self, mac):
        return


class _SgwApiClientThread:

    def __init__(self, pObj):
        self.pObj = pObj

    def run(self):
        while True:
            self.pObj.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                self.pObj.sock.connect((ip, 2300))
                
                self.pObj.sock.send(json.dumps({
                    "command": "get-host-list",
                }).encode("utf-8"))
                self.pObj.state = 1     # get-sock-list command pending

                while True:
                    buf = SnUtil.recvLine(self.pObj.sock)
                    if len(buf) == 0:
                        break
                    jsonObj = json.loads(buf)
                    if "return" in jsonObj:
                        if self.pObj.state == 1:
                            for ip, data in jsonObj["return"].items():
                                if "hostname" in data and data["hostname"] in self.peerList:
                                    self.activePeerDict[ip] = data["hostname"]
                                    self.upCallback(self.activePeerDict[ip])
                        elif self.pObj.state == 2:
                            assert False
                        else:
                            continue
                    elif "notify" in jsonObj:
                        if jsonObj["notify"] == "host-appear":
                            for ip, data in jsonObj["data"].items():
                                if "hostname" in data and data["hostname"] in self.peerList:
                                    self.activePeerDict[ip] = data["hostname"]
                                    self.upCallback(self.activePeerDict[ip])
                        elif jsonObj["notify"] == "host-disappear":
                            for ip in jsonObj["data"]:
                                if ip in self.activePeerDict: 
                                    self.downCallback(self.activePeerDict[ip])                           
                                    del self.activePeerDict[ip]
                        else:
                            pass
                    else:
                        pass
            except socket.error as e:
                pass
            finally:
                if True:
                    for hostname in self.activePeerDict.values():
                        self.pObj.downCallback(hostname)
                    self.activePeerDict.clear()
                if True:
                    self.pObj.sock.close()
                    self.pObj.sock = None
                if True:
                    self.pObj.state = 0
                time.sleep(10)