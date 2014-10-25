#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

"""
Selfnet module name consists of 3 parts: scope, type, id, separated by "-".
Some example: sys-server-distcc, sys-client-distcc, usr-server-ssh, usr-client-ssh
"scope" can have 2 values: sys and usr.
"type" can have 3 values: server, client, peer.
"id" is a string with maximum length of 32 characters, for which valid charater is [A-Za-z0-9_].

Replace "-" with "_" can selfnet module name be converted to python module name.
"""

import os
import socket
import logging


class SnModule:

    def getModuleName(self):
        assert False            # implement by subclass

    def getPropDict(self):
        """Property list: allow-local-peer: true | false
                          suid: true | false
                          standalone: true | false"""
        assert False            # implement by subclass


class SnModuleInstance:

    WORK_STATE_IDLE = 0
    WORK_STATE_WORKING = 1

    def __init__(self, coreObj, peerName, userName, moduleName, tmpDir):
        self.coreObj = coreObj
        self.peerName = peerName
        self.userName = userName
        self.moduleName = moduleName
        self.tmpDir = tmpDir

    ##### callback functions ####

    def onInit(self):
        """Called after the module instance object is created"""
        assert False            # implement by subclass

    def onActive(self):
        """Called after the peer changes to active state"""
        assert False            # implement by subclass

    def onInactive(self):
        """Called before the peer changes to inactive state"""
        assert False            # implement by subclass

    def onRecv(self, dataObj):
        """Called when data is received from the peer"""
        assert False            # implement by subclass

    ##### assistant functions ####

    def getPeerName(self):
        return self.peerName

    def getUserName(self):
        return self.userName

    def getModuleName(self):
        return self.moduleName

    def getHostName(self):
        return socket.gethostname()

    def isLocalPeer(self):
        return self.peerName == socket.gethostname()

    def getTmpDir(self):
        """Temp directory is created when being used for the first time, deleted
           before change to inactive state"""

        if not os.path.exists(self.tmpDir):
            os.mkdir(self.tmpDir)
        return self.tmpDir

    def sendObject(self, obj):
        self.coreObj._sendObject(self.peerName, self.userName, self.moduleName, obj)

    def setWorkState(self, workState):
        assert workState in [SnModuleInstance.WORK_STATE_IDLE, SnModuleInstance.WORK_STATE_WORKING]
        self.coreObj._setWorkState(self.peerName, self.userName, self.moduleName, workState)

    def logDebug(self, pattern, *args):
        self.coreObj._moduleLog(self.peerName, self.userName, self.moduleName, logging.DEBUG, pattern, args)

    def logInfo(self, pattern, *args):
        self.coreObj._moduleLog(self.peerName, self.userName, self.moduleName, logging.INFO, pattern, args)

    def logWarning(self, pattern, *args):
        self.coreObj._moduleLog(self.peerName, self.userName, self.moduleName, logging.WARNING, pattern, args)

    def logError(self, pattern, *args):
        self.coreObj._moduleLog(self.peerName, self.userName, self.moduleName, logging.ERROR, pattern, args)

    def logCritical(self, pattern, *args):
        self.coreObj._moduleLog(self.peerName, self.userName, self.moduleName, logging.CRITICAL, pattern, args)


class SnRejectException(Exception):
    pass
