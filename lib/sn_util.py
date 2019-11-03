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
        self.fin = fin
        self.fout = fout
        self.recvFunc = recvFunc

        self.flagError = GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP | GLib.IO_NVAL
        self.isClose = False
        self.recvBuffer = ""
        self.recvSourceId = GLib.io_add_watch(self.fin, GLib.IO_IN | self.flagError, self._onRecv)

    def send(self, data):
        assert not self.isClose

        data = pickle.dumps(data)
        header = struct.pack("!I", len(data))
        packet = header + data
        self.fout.write(packet)
        self.fout.flush()

    def close(self):
        assert not self.isClose
        self.isClose = True

    def _onRecv(self, source, cb_condition):
        if self.isClose:
            return False

        try:
            if cb_condition & self.flagError:
                logging.error("StdinStdoutObjSocket._onRecv, %s" % (SnUtil.cbConditionToStr(cb_condition)))
                return False

            self.recvBuffer += self.fin.read()
            while True:
                # get packet header
                headerLen = struct.calcsize("!I")
                if len(self.recvBuffer) < headerLen:
                    return True

                # get packet data
                dataLen = struct.unpack("!I", self.recvBuffer[:headerLen])[0]
                totalLen = headerLen + dataLen
                if len(self.recvBuffer) < totalLen:
                    return True

                # invoke callback function
                data = pickle.loads(self.recvBuffer[headerLen:totalLen])
                self.recvBuffer = self.recvBuffer[totalLen:]
                self.recvFunc(self, data)
                if self.isClose:
                    return False
        except:
            logging.error(traceback.format_exc())
            return False


# this socket requires full control of sys.stdin and sys.stdout
class StdinStdoutObjSocket(PipeObjSocket):

    def __init__(self, recvFunc):
        fcntl.fcntl(sys.stdin, fcntl.F_SETFL, os.O_NONBLOCK)
        super(PipeObjSocket, self).__init__(sys.stdin, sys.stdout, recvFunc)


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