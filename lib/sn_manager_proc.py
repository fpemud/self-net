#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

class SnProcManager:

    def __init__(self, param):
        self.param = param

        self.systemProc = SnWorkProc(self.param, None)

        self.userProcDict = dict()
        for user in SnUtil.getNormalUserList():
            self.userProcDict[user] = SnWorkProc(self.param, user)

    def newModuleSingleton(self, modulePropDict):
        self._sendMessageNewModule(self.systemProc, modulePropDict, None, None, None)

    def newModulePerUser(self, modulePropDict, userName):
        self._sendMessageNewModule(self.userProcDict[userName], modulePropDict, userName, None, None)

    def newModulePerUserHost(self, modulePropDict, userName, peerHostId):
        self._sendMessageNewModule(self.userProcDict[userName], modulePropDict, userName, peerHostId, None)

    def newModulePerUserHostApp(self, modulePropDict, userName, peerHostId, peerAppId):
        self._sendMessageNewModule(self.userProcDict[userName], modulePropDict, userName, peerHostId, peerAppId)

    def deleteModuleSingleton(self):
        assert False


    def _sendMessageNewModule(self, propDict, workerProc, username, peerHostId, peerAppId):
        message = dict()
        message["type"] = "new-module"
        if username is not None:
            message["username"] = username
        message["properties"] = propDict
        if peerHostId is not None:
            message["peer-host-id"] = peerHostId
        if peerAppId is not None:
            messsage["peer-app-id"] = peerAppId

        workProc.stdin.write()


class SnWorkProc:
    
    def __init__(self, param, userName):
        self.proc = None
        self.objSocket = None

        cmdlist = []

        cmdlist.append(param.wokerProcFile)

        tdata = dict()
        if True:
            if userName is None:
                tdata["tmpDir"] = os.path.join(param.tmpDir, "system")
                tdata["logFile"] = os.path.join(param.logDir, "system.log")
            else:
                tdata["username"] = userName
                tdata["tmpDir"] = os.path.join(param.tmpDir, userName)
                tdata["logFile"] = os.path.join(param.logDir, "%s.log" % (userName))
            tdata["logLevel"] = param.logLevel
        cmdlist.append(json.dumps(tdata))

        self.proc = subprocess.Popen(cmdlist, bufsize=-1, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

        self.objSocket = PipeObjSocket(self.proc.stdout, self.proc.stdin, None)    # FIXME


