#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import fcntl
import shutil
import socket
import logging
import traceback
import subprocess
import collections
from objsocket import objsocket

from sn_util import SnUtil
from sn_util import SnSleepNotifier
from sn_sub_proc import LocalSockSendObj
from sn_sub_proc import LocalSockSetWorkState
from sn_sub_proc import LocalSockCall
from sn_sub_proc import LocalSockRetn
from sn_sub_proc import LocalSockExcp
from sn_module import SnModuleInstance
from sn_module import SnRejectException

# _ModuleObjInternal(moi) life cycle:
#
# moi object is created and destroyed when peer module appears and disappears,
# but moi object must go through a garbage-collection process before destruction
# if it has start functioning (out of PENDING state).
#
# New moi object won't go out of the PENDING state and start work before the
# old moi object is finally destroyed. The new moi object can be destroyed directly
# because it has not begon functioning.
#
# moi object starts receive packet immediately after it is created. Packet is
# received into moi.peerPacketQueue.
#
# moi object can only send / recv business packet (except and reject packet is
# system packet) in ACTIVE or FULL state. And moi object can not send / recv
# packet if it is in garbage-collection.
#

# _ModuleObjInternal FSM state condition:
#
#     new             -> STATE_PENDING     : object created
#   STATE_PENDING     -> STATE_ACTIVE      : old poi object does not exist any more
#
#   STATE_ACTIVE      -> STATE_FULL        : onActive returns, peer normal and peer module normal
#   STATE_ACTIVE      -> STATE_PEER_REJECT : onActive returns, reject received
#   STATE_ACTIVE      -> STATE_PEER_EXCEPT : onActive returns, except received
#   STATE_ACTIVE      -> STATE_INACTIVE    : onActive returns, peer removed or peer module removed
#
#   STATE_FULL        -> STATE_REJECT      : onRecv raise SnRejectException
#   STATE_FULL        -> STATE_PEER_REJECT : onRecv returns, reject received
#   STATE_FULL        -> STATE_PEER_EXCEPT : onRecv returns, except received
#   STATE_FULL        -> STATE_INACTIVE    : peer down or peer module removed
#
#   STATE_PENDING     ->   delete          : peer down or peer module removed
#   STATE_INACTIVE    ->   delete          : onInactive returns or raises exception
#
#   STATE_ACTIVE      -> STATE_EXCEPT      : onActive raises exception
#   STATE_FULL        -> STATE_EXCEPT      : onRecv raises exception
#   STATE_REJECT      -> STATE_EXCEPT      : onInactive raises exception
#   STATE_PEER_REJECT -> STATE_EXCEPT      : onInactive raises exception
#   STATE_PEER_EXCEPT -> STATE_EXCEPT      : onInactive raises exception
#
#   STATE_REJECT      ->   delete          : peer down or peer module removed
#   STATE_PEER_REJECT ->   delete          : peer down or peer module removed
#   STATE_EXCEPT      ->   delete          : peer down or peer module removed
#   STATE_PEER_EXCEPT ->   delete          : peer down or peer module removed
#

# _ModuleObjInternal FSM state action:
#   (action is carried on AFTER state change)
#
#     new             -> STATE_PENDING     : do nothing
#   STATE_PENDING     -> STATE_ACTIVE      : call onActive
#
#   STATE_ACTIVE      -> STATE_FULL        : do nothing
#   STATE_ACTIVE      -> STATE_PEER_REJECT : call onInactive
#   STATE_ACTIVE      -> STATE_PEER_EXCEPT : call onInactive
#   STATE_ACTIVE      -> STATE_INACTIVE    : call onInactive
#
#   STATE_FULL        -> STATE_INACTIVE    : call onInactive
#   STATE_FULL        -> STATE_REJECT      : sendReject, call onInactive
#   STATE_FULL        -> STATE_PEER_REJECT : call onInactive
#   STATE_FULL        -> STATE_PEER_EXCEPT : call onInactive
#
#   STATE_INACTIVE    ->  delete           :
#
#   STATE_ACTIVE      -> STATE_EXCEPT      : sendExcept
#   STATE_FULL        -> STATE_EXCEPT      : sendExcept
#   STATE_REJECT      -> STATE_EXCEPT      : do nothing
#   STATE_PEER_REJECT -> STATE_EXCEPT      : do nothing
#   STATE_PEER_EXCEPT -> STATE_EXCEPT      : do nothing
#
#   STATE_REJECT      ->   delete          :
#   STATE_PEER_REJECT ->   delete          :
#   STATE_EXCEPT      ->   delete          :
#   STATE_PEER_EXCEPT ->   delete          :
#

# fixme: needs to consider user change, both local user change and user change received by peer


class SnSysInfo:

    def __init__(self):
        self.userList = None                # list<SnSysInfoUser>
        self.moduleList = None              # list<SnSysInfoModule>


class SnSysInfoUser:

    def __init__(self):
        self.userName = None                # str

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self.userName == other.userName

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self.userName)


class SnSysInfoModule:

    def __init__(self):
        self.moduleName = None              # str
        self.userName = None                # str

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self.moduleName == other.moduleName and self.userName == other.userName

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self.moduleName) ^ hash(self.userName)


class SnDataPacket:

    def __init__(self):
        self.srcUserName = None             # str, can be None
        self.srcModuleName = None           # str
        self.data = None                    # object


class SnDataPacketReject:

    def __init__(self):
        self.message = None                 # str


class SnDataPacketExcept:
    pass


class SnLocalManager:

    WORK_STATE_IDLE = 0
    WORK_STATE_WORKING = 1

    def __init__(self, param):
        logging.debug("SnLocalManager.__init__: Start")

        # variables
        self.param = param
        self.disposeCompleteFunc = None
        self.localInfo = self._getLocalInfo()
        self.moiList = []
        self.moiGcList = []
        self.sleepNotifier = SnSleepNotifier(self.onBeforeSleep, self.onAfterResume)

        # local peer go into up state
        SnUtil.idleInvoke(self.onPeerChange, socket.gethostname(), self.localInfo)

        logging.debug("SnLocalManager.__init__: End")
        return

    def dispose(self, disposeCompleteFunc):
        logging.debug("SnLocalManager.dispose: Start")

        self.localInfo = None
        self.onPeerChange(socket.gethostname(), None)

        self.disposeCompleteFunc = disposeCompleteFunc

        assert len(self.moiList) == 0
        if len(self.moiGcList) == 0:
            SnUtil.idleInvoke(self._disposeComplete)

    def getLocalInfo(self):
        return self.localInfo

    def getWorkState(self):
        for moi in self.moiList:
            if moi.workState == SnModuleInstance.WORK_STATE_WORKING:
                return SnLocalManager.WORK_STATE_WORKING
        return SnLocalManager.WORK_STATE_IDLE

    def debugGetModuleInfo(self):
        moduleStateDict = {
            _MoiObj.STATE_PENDING: "pending",
            _MoiObj.STATE_ACTIVE: "active",
            _MoiObj.STATE_FULL: "full",
            _MoiObj.STATE_REJECT: "reject",
            _MoiObj.STATE_PEER_REJECT: "peer-reject",
            _MoiObj.STATE_EXCEPT: "except",
            _MoiObj.STATE_PEER_EXCEPT: "peer-except",
            _MoiObj.STATE_INACTIVE: "inactive",
        }

        ret = dict()
        for moi in self.moiList:
            key = _moi_key_to_str(moi)
            ret[key] = (moduleStateDict[moi.state], moi.failMessage)
        return ret

    ##### event callback ####

    def onPeerChange(self, peerName, peerInfo):
        logging.debug("SnLocalManager.onPeerChange: Start, %s", peerName)

        if peerInfo is None:
            peerInfo = SnSysInfo()
            peerInfo.moduleList = []

        # module remove
        newMoiList = []
        for moi in self.moiList:
            if moi.peerName == peerName and not self._pmiMatch(peerName, peerInfo, moi):
                if moi.state != _MoiObj.STATE_PENDING:
                    self.moiGcList.append(moi)
                    moi.gcFlag = _MoiObj.GC_START
                    if moi.calling is None:
                        self._moiGcStart(moi)
            else:
                newMoiList.append(moi)
        self.moiList = newMoiList

        # module add
        newMoiList = []
        for moduleName in self.param.configManager.getModuleNameList():
            minfo = self.param.configManager.getModuleInfo(moduleName)
            if peerName == socket.gethostname() and not minfo.moduleObj.getPropDict()["allow-local-peer"]:
                continue
            if minfo.moduleScope == "sys":
                if not self._pmiMatchTuple(peerName, peerInfo, None, moduleName):
                    continue
                self._moiCreate(peerName, None, moduleName, minfo)
                newMoiList.append(self.moiList[-1])
            elif minfo.moduleScope == "usr":
                for userName in SnUtil.getNormalUserList():
                    if userName in self.param.configManager.getUserBlackList():
                        continue
                    if not self._pmiMatchTuple(peerName, peerInfo, userName, moduleName):
                        continue
                    moi = self._moiCreate(peerName, userName, moduleName, minfo)
                    newMoiList.append(self.moiList[-1])
        for moi in newMoiList:
            if self._moiGcFind(moi.peerName, moi.userName, moi.moduleName) is None:
                self._moiChangeState(moi, _MoiObj.STATE_ACTIVE, "")

        logging.debug("SnLocalManager.onPeerChange: End")
        return

    def onPeerSockRecv(self, peerName, userName, srcModuleName, data):
        moi = self._moiGetMapped(peerName, userName, srcModuleName)

        if moi.state == _MoiObj.STATE_PENDING:
            moi.peerPacketQueue.append(data)
        elif moi.state == _MoiObj.STATE_ACTIVE:
            moi.peerPacketQueue.append(data)
        elif moi.state == _MoiObj.STATE_FULL:
            moi.peerPacketQueue.append(data)
            if moi.calling is None:
                assert len(moi.peerPacketQueue) == 1
                self._moiProcessPacket(moi)
        elif moi.state == _MoiObj.STATE_REJECT:
            pass                # redundant packet received
        elif moi.state == _MoiObj.STATE_PEER_REJECT:
            assert False        # shouldn't receive packet after peer reject
        elif moi.state == _MoiObj.STATE_EXCEPT:
            pass                # redundant packet received
        elif moi.state == _MoiObj.STATE_PEER_EXCEPT:
            assert False        # shouldn't receive packet after peer except
        elif moi.state == _MoiObj.STATE_INACTIVE:
            assert False        # shouldn't receive packet after peer down
        else:
            assert False

    def onProcPipeRecv(self, procPipe, packetObj):
        moi = self._moiGcFindByProcPipe(procPipe)
        if moi is None:
            moi = self._moiGetByProcPipe(procPipe)

        if _type_check(packetObj, LocalSockSendObj):
            self._sendObject(moi.peerName, moi.userName, moi.moduleName, packetObj.dataObj)
        elif _type_check(packetObj, LocalSockSetWorkState):
            self._setWorkState(moi.peerName, moi.userName, moi.moduleName, packetObj.workState)
        elif _type_check(packetObj, LocalSockRetn):
            self._moiCallFuncReturn(moi, packetObj.retVal)
        elif _type_check(packetObj, LocalSockExcp):
            self._moiCallFuncExcept(moi, packetObj.excObj, packetObj.excInfo)
        else:
            assert False

    def onProcPipeError(self, procPipe, e):
        gcmoi = self._moiGcFindByProcPipe(procPipe)
        if gcmoi is not None:
            assert gcmoi.calling is None
            gcmoi.procPipe.close()
            gcmoi.procPipe = None
            gcmoi.proc = None
            self._moiGcComplete(gcmoi)
            return

        moi = self._moiGetByProcPipe(procPipe)
        if moi is not None:
            assert moi.calling is None
            gcmoi.procPipe.close()
            moi.procPipe = None
            moi.proc = None
            if moi.state in [_MoiObj.STATE_ACTIVE, _MoiObj.STATE_FULL]:
                self._moiChangeState(moi, _MoiObj.STATE_EXCEPT, str(e))
            elif moi.state in [_MoiObj.STATE_REJECT, _MoiObj.STATE_PEER_REJECT, _MoiObj.STATE_EXCEPT, _MoiObj.STATE_PEER_EXCEPT]:
                pass
            else:
                assert False
            return

        assert False

    def onBeforeSleep(self, sleepType):
        pass

    def onAfterResume(self, sleepType):
        pass

    ##### implementation ####

    def _getLocalInfo(self):
        userList = SnUtil.getNormalUserList()
        ret = SnSysInfo()

        ret.userList = []
        for uname in userList:
            if uname in self.param.configManager.getUserBlackList():
                continue
            n = SnSysInfoUser()
            n.userName = uname
            ret.userList.append(n)

        ret.moduleList = []
        for mname in self.param.configManager.getModuleNameList():
            mInfo = self.param.configManager.getModuleInfo(mname)
            if mInfo.moduleScope == "sys":
                n = SnSysInfoModule()
                n.moduleName = mname
                n.userName = None
                ret.moduleList.append(n)
            elif mInfo.moduleScope == "usr":
                for uname in userList:
                    if uname in self.param.configManager.getUserBlackList():
                        continue
                    n = SnSysInfoModule()
                    n.moduleName = mname
                    n.userName = uname
                    ret.moduleList.append(n)
            else:
                assert False

        return ret

    def _startSubProc(self, peerName, userName, moduleName, tmpDir, logFile):
        cmdlist = []
        cmdlist.append(self.param.subprocFile)
        cmdlist.append(peerName)
        if userName is None:
            cmdlist.append("")
        else:
            cmdlist.append(userName)
        cmdlist.append(moduleName)
        cmdlist.append(tmpDir)
        cmdlist.append(self.param.logLevel)
        cmdlist.append(logFile)

        return subprocess.Popen(cmdlist, bufsize=-1, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def _sendReject(self, peerName, userName, moduleName, rejectMessage):
        if self._moiGcFind(peerName, userName, moduleName) is not None:
            return

        logging.warning("SnLocalManager.sendReject, %s, %s, %s, %s", peerName, userName, moduleName, rejectMessage)

        messageObj = SnDataPacketReject()
        messageObj.message = rejectMessage
        if peerName == socket.gethostname():
            SnUtil.idleInvoke(self.onPeerSockRecv, peerName, userName, moduleName, messageObj)
        else:
            self.param.peerManager.sendDataObject(peerName, userName, moduleName, messageObj)

    def _sendExcept(self, peerName, userName, moduleName):
        if self._moiGcFind(peerName, userName, moduleName) is not None:
            return

        logging.warning("SnLocalManager.sendExcept, %s, %s, %s", peerName, userName, moduleName)

        messageObj = SnDataPacketExcept()
        if peerName == socket.gethostname():
            SnUtil.idleInvoke(self.onPeerSockRecv, peerName, userName, moduleName, messageObj)
        else:
            self.param.peerManager.sendDataObject(peerName, userName, moduleName, messageObj)

    def _sendObject(self, peerName, userName, moduleName, obj):
        if self._moiGcFind(peerName, userName, moduleName) is not None:
            return

        moi = self._moiGet(peerName, userName, moduleName)

        assert moi.state in [_MoiObj.STATE_ACTIVE, _MoiObj.STATE_FULL]
        if peerName == socket.gethostname():
            SnUtil.idleInvoke(self.onPeerSockRecv, peerName, userName, moduleName, obj)
        else:
            self.param.peerManager.sendDataObject(peerName, userName, moduleName, obj)

    def _setWorkState(self, peerName, userName, moduleName, workState):
        if self._moiGcFind(peerName, userName, moduleName) is not None:
            return

        moi = self._moiGet(peerName, userName, moduleName)

        assert moi.state in [_MoiObj.STATE_ACTIVE, _MoiObj.STATE_FULL]
        moi.workState = workState

    def _moduleLog(self, peerName, userName, moduleName, logLevel, msg, args):
        moi = self._moiGet(peerName, userName, moduleName)

        if userName is None:
            modName = "%s-%s" % (peerName, moduleName)
        else:
            modName = "%s-%s-%s" % (peerName, userName, moduleName)

        logging.getLogger(modName).addHandler(logging.FileHandler(moi.logFile))
        logging.getLogger(modName).setLevel(SnUtil.getLoggingLevel(self.param.logLevel))
        logging.getLogger(modName).log(logLevel, msg, args)

    def _procPipeGcComplete(self, procPipe):
        """We don't do graceful close on procPipe"""
        assert False

    def _disposeComplete(self):
        logging.debug("SnLocalManager.dispose: End")
        self.disposeCompleteFunc()

    ##### moi assistant method ####

    def _moiCreate(self, peerName, userName, moduleName, minfo):
        logging.info("SnLocalManager.moiCreate: %s, %s, %s", peerName, userName, moduleName)

        if minfo.moduleScope == "sys":
            assert userName is None
        elif minfo.moduleScope == "usr":
            assert userName is not None
        else:
            assert False

        moi = _MoiObj()
        moi.peerName = peerName
        moi.userName = userName
        moi.moduleName = moduleName
        moi.moduleScope = minfo.moduleScope
        moi.moduleType = minfo.moduleType
        moi.moduleId = minfo.moduleId
        moi.propDict = minfo.moduleObj.getPropDict()
        if userName is None:
            moi.tmpDir = os.path.join(self.param.tmpDir, "%s-%s" % (peerName, moduleName))
            moi.logFile = os.path.join(self.param.logDir, "selfnetd-module-%s-%s.log" % (peerName, moduleName))
        else:
            moi.tmpDir = os.path.join(self.param.tmpDir, "%s-%s-%s" % (peerName, userName, moduleName))
            moi.logFile = os.path.join(self.param.logDir, "selfnetd-module-%s-%s-%s.log" % (peerName, userName, moduleName))
        moi.state = _MoiObj.STATE_PENDING
        moi.failMessage = ""
        moi.workState = SnModuleInstance.WORK_STATE_IDLE
        moi.peerPacketQueue = collections.deque()
        self.moiList.append(moi)

    def _moiGet(self, peerName, userName, moduleName):
        moi = self._moiFind(peerName, userName, moduleName)
        assert moi is not None
        return moi

    def _moiFind(self, peerName, userName, moduleName):
        for moi in self.moiList:
            if moi.peerName == peerName and moi.userName == userName and moi.moduleName == moduleName:
                return moi
        return None

    def _moiGetMapped(self, peerName, userName, srcModuleName):
        moi = self._moiFindMapped(peerName, userName, srcModuleName)
        assert moi is not None
        return moi

    def _moiFindMapped(self, peerName, userName, srcModuleName):
        for moi in self.moiList:
            if moi.peerName == peerName and moi.userName == userName and moi.moduleName == _map_module_name(srcModuleName):
                return moi
        return None

    def _moiGetByProcPipe(self, procPipe):
        moi = self._moiFindByProcPipe(procPipe)
        assert moi is not None
        return moi

    def _moiFindByProcPipe(self, procPipe):
        for moi in self.moiList:
            if moi.procPipe == procPipe:
                return moi
        return None

    def _moiGetByProc(self, proc):
        moi = self._moiFindByProc(proc)
        assert moi is not None
        return moi

    def _moiFindByProc(self, proc):
        for moi in self.moiList:
            if moi.proc == proc:
                return moi
        return None

    def _moiGcFind(self, peerName, userName, moduleName):
        for gcObj in self.moiGcList:
            if gcObj.peerName == peerName and gcObj.userName == userName and gcObj.moduleName == moduleName:
                return gcObj
        return None

    def _moiGcFindByProc(self, proc):
        for gcObj in self.moiGcList:
            if gcObj.proc == proc:
                return gcObj
        return None

    def _moiGcFindByProcPipe(self, procPipe):
        for gcObj in self.moiGcList:
            if gcObj.procPipe == procPipe:
                return gcObj
        return None

    def _moiChangeState(self, moi, newState, failMessage=""):
        assert _moi_state_is_valid(newState, failMessage)
        assert moi.calling is None

        # change state
        oldState = moi.state
        logging.info("SnLocalManager.moiChangeState: %s, %s -> %s", _moi_key_to_str(moi), _moi_state_to_str(oldState), _moi_state_to_str(newState))
        moi.state = newState

        # change workState, clear peerPacketQueue
        if newState in [_MoiObj.STATE_INACTIVE, _MoiObj.STATE_REJECT, _MoiObj.STATE_PEER_REJECT, _MoiObj.STATE_EXCEPT, _MoiObj.STATE_PEER_EXCEPT]:
            moi.workState = SnModuleInstance.WORK_STATE_IDLE
            moi.peerPacketQueue.clear()

        # change failMessage
        if newState in [_MoiObj.STATE_REJECT, _MoiObj.STATE_PEER_REJECT, _MoiObj.STATE_EXCEPT]:
            moi.failMessage = failMessage

        # do post change operation
        if True:
            if newState == _MoiObj.STATE_ACTIVE:
                assert moi.failMessage == ""
                assert moi.workState == SnModuleInstance.WORK_STATE_IDLE

                if not moi.propDict["standalone"]:
                    exec("import %s" % (moi.moduleName.replace("-", "_")))
                    exec("moi.mo = %s.ModuleInstanceObject(self, moi.peerName, moi.userName, moi.moduleName, moi.tmpDir)" % (moi.moduleName.replace("-", "_")))
                else:
                    moi.proc = self._startSubProc(moi.peerName, moi.userName, moi.moduleName, moi.tmpDir, moi.logFile)
                    fcntl.fcntl(moi.proc.stdout, fcntl.F_SETFL, os.O_NONBLOCK)
                    moi.procPipe = objsocket(objsocket.SOCKTYPE_PIPE_PAIR, (moi.proc.stdout, moi.proc.stdin), self.onProcPipeRecv, self.onProcPipeError, self._procPipeGcComplete)
                self._moiCallFunc(moi, "onActive")
                return

            if newState == _MoiObj.STATE_FULL:
                assert moi.failMessage == ""
                assert moi.workState == SnModuleInstance.WORK_STATE_IDLE

                if len(moi.peerPacketQueue) > 0:
                    self._moiProcessPacket(moi)
                return

            if newState == _MoiObj.STATE_INACTIVE:
                assert moi.failMessage == ""
                moi.workState = SnModuleInstance.WORK_STATE_IDLE

                self._moiCallFunc(moi, "onInactive")
                return

            if newState == _MoiObj.STATE_REJECT:
                moi.failMessage = failMessage
                moi.workState = SnModuleInstance.WORK_STATE_IDLE

                self._sendReject(moi.peerName, moi.userName, moi.moduleName, moi.failMessage)
                self._moiCallFunc(moi, "onInactive")
                return

            if newState == _MoiObj.STATE_PEER_REJECT:
                moi.failMessage = failMessage
                moi.workState = SnModuleInstance.WORK_STATE_IDLE

                self._moiCallFunc(moi, "onInactive")
                return

            if newState == _MoiObj.STATE_EXCEPT:
                moi.failMessage = failMessage
                moi.workState = SnModuleInstance.WORK_STATE_IDLE

                if oldState in [_MoiObj.STATE_ACTIVE, _MoiObj.STATE_FULL]:
                    self._sendExcept(moi.peerName, moi.userName, moi.moduleName)
                if moi.propDict["standalone"]:
                    if moi.proc is not None:
                        moi.proc.terminate()
                return

            if newState == _MoiObj.STATE_PEER_EXCEPT:
                moi.failMessage = ""
                moi.workState = SnModuleInstance.WORK_STATE_IDLE

                self._moiCallFunc(moi, "onInactive")
                return

            assert False
            return

    def _moiGcStart(self, gcmoi):
        assert gcmoi.gcFlag == _MoiObj.GC_START
        logging.debug("SnLocalManager.moiGcStart: %s", _moi_key_to_str(gcmoi))
        gcmoi.gcFlag = _MoiObj.GC_STARTED

        if gcmoi.state in [_MoiObj.STATE_ACTIVE, _MoiObj.STATE_FULL]:
            self._moiChangeState(gcmoi, _MoiObj.STATE_INACTIVE, "")
        elif gcmoi.state in [_MoiObj.STATE_REJECT, _MoiObj.STATE_PEER_REJECT, _MoiObj.STATE_EXCEPT, _MoiObj.STATE_PEER_EXCEPT]:
            if not gcmoi.propDict["standalone"]:
                assert gcmoi.mo is not None
                SnUtil.idleInvoke(self._moiGcComplete, gcmoi)
            else:
                if gcmoi.proc is not None:
                    pass
                else:
                    SnUtil.idleInvoke(self._moiGcComplete, gcmoi)
        else:
            assert False

    def _moiGcComplete(self, gcmoi):
        assert gcmoi.gcFlag == _MoiObj.GC_STARTED
        logging.debug("SnLocalManager.moiGcComplete: %s", _moi_key_to_str(gcmoi))
        self.moiGcList.remove(gcmoi)

        moi = self._moiFind(gcmoi.peerName, gcmoi.userName, gcmoi.moduleName)
        if moi is not None:
            assert moi.state == _MoiObj.STATE_PENDING
            self._moiChangeState(moi, _MoiObj.STATE_ACTIVE, "")

        if self.disposeCompleteFunc is not None:
            assert len(self.moiList) == 0
            if len(self.moiGcList) == 0:
                self._disposeComplete()

    def _moiCallFunc(self, moi, funcName, *args):
        assert moi.calling is None

        logging.debug("SnLocalManager.moiCallFunc: %s, call, %s", funcName, _moi_key_to_str(moi))
        moi.calling = funcName

        if not moi.propDict["standalone"]:
            assert moi.mo is not None
            SnUtil.idleInvoke(self._moiCallFuncImpl, moi, *args)
        else:
            if moi.proc is not None:
                p = LocalSockCall()
                p.funcName = funcName
                p.funcArgs = args
                moi.procPipe.send(p)
            else:
                assert False

    def _moiCallFuncImpl(self, moi, *args):
        try:
            if moi.calling == "onActive":
                assert len(args) == 0
                SnUtil.euidInvoke(moi.userName, moi.mo.onInit)
                SnUtil.euidInvoke(moi.userName, moi.mo.onActive)
            elif moi.calling == "onRecv":
                assert len(args) == 1
                SnUtil.euidInvoke(moi.userName, moi.mo.onRecv, args[0])
            elif moi.calling == "onInactive":
                assert len(args) == 0
                SnUtil.euidInvoke(moi.userName, moi.mo.onInactive)
            else:
                assert False
        except Exception as e:
            self._moiCallFuncExcept(moi, e, traceback.format_exc())
            return
        shutil.rmtree(moi.tmpDir, True)
        self._moiCallFuncReturn(moi, None)

    def _moiCallFuncReturn(self, moi, retVal):
        # finish function call
        funcName = moi.calling
        logging.debug("SnLocalManager.moiCallFunc: %s, return, %s", moi.calling, _moi_key_to_str(moi))
        moi.calling = None

        # do post call operation
        if moi.gcFlag is None:
            if funcName == "onActive":
                self._moiChangeState(moi, _MoiObj.STATE_FULL, "")
            elif funcName == "onRecv":
                if len(moi.peerPacketQueue) > 0:
                    self._moiProcessPacket(moi)
            elif funcName == "onInactive":
                if moi.propDict["standalone"]:
                    assert moi.proc is not None
                    moi.proc.terminate()
            else:
                assert False
        else:
            if moi.gcFlag == _MoiObj.GC_START:
                self._moiGcStart(moi)
                return
            elif moi.gcFlag == _MoiObj.GC_STARTED:
                assert funcName == "onInactive" and moi.state == _MoiObj.STATE_INACTIVE
                if not moi.propDict["standalone"]:
                    assert moi.mo is not None
                    self._moiGcComplete(moi)
                else:
                    if moi.proc is not None:
                        moi.proc.terminate()
                    else:
                        self._moiGcComplete(moi)
            else:
                assert False

    def _moiCallFuncExcept(self, moi, excObj, excInfo):
        # finish function call
        funcName = moi.calling
        logging.debug("SnLocalManager.moiCallFunc: %s, except, %s, %s, %s\n%s", moi.calling, _moi_key_to_str(moi), excObj.__class__, excObj, excInfo)
        moi.calling = None

        # do post call operation
        if moi.gcFlag is None:
            if funcName == "onActive":
                self._moiChangeState(moi, _MoiObj.STATE_EXCEPT, excInfo)
            elif funcName == "onRecv":
                if _type_check(excObj, SnRejectException):
                    self._moiChangeState(moi, _MoiObj.STATE_REJECT, excObj.message)
                else:
                    self._moiChangeState(moi, _MoiObj.STATE_EXCEPT, excInfo)
            elif funcName == "onInactive":
                self._moiChangeState(moi, _MoiObj.STATE_EXCEPT, excInfo)
            else:
                assert False
        else:
            if not moi.propDict["standalone"]:
                assert moi.mo is not None
                self._moiGcComplete(moi)
            else:
                if moi.proc is not None:
                    moi.proc.terminate()
                else:
                    self._moiGcComplete(moi)

    def _moiProcessPacket(self, moi):
        assert moi.state == _MoiObj.STATE_FULL
        assert moi.calling is None

        data = moi.peerPacketQueue.popleft()
        if _type_check(data, SnDataPacketReject):
            self._moiChangeState(moi, _MoiObj.STATE_PEER_REJECT)
        elif _type_check(data, SnDataPacketExcept):
            self._moiChangeState(moi, _MoiObj.STATE_PEER_EXCEPT)
        else:
            self._moiCallFunc(moi, "onRecv", data)

    ##### pmi assistant method ####

    def _pmiMatch(self, peerName, peerInfo, moi):
        assert moi.peerName == peerName
        return self._pmiMatchTuple(peerName, peerInfo, moi.userName, moi.moduleName)

    def _pmiMatchTuple(self, peerName, peerInfo, userName, moduleName):
        for pmi in peerInfo.moduleList:
            if userName == pmi.userName and moduleName == _map_module_name(pmi.moduleName):
                return True
        return False


class _MoiObj:

    """MOI: module object internal"""

    STATE_PENDING = 0
    STATE_ACTIVE = 1
    STATE_FULL = 2
    STATE_REJECT = 3
    STATE_PEER_REJECT = 4
    STATE_EXCEPT = 5
    STATE_PEER_EXCEPT = 6
    STATE_INACTIVE = 7

    GC_START = 1
    GC_STARTED = 2

    peerName = None                            # str
    userName = None                            # str, can be None
    moduleName = None                        # str, "sys-server-name"
    moduleScope = None                        # str, "sys" "usr"
    moduleType = None                        # str, "server" "client" "peer"
    moduleId = None                            # str
    propDict = None                            # dict
    tmpDir = None                            # str
    logFile = None                            # str
    mo = None                                # obj, SnModuleInstance, standalone module: None
    proc = None                                # obj, not-standalone module: None
    procPipe = None                            # obj, not-standalone module: None
    state = None                            # enum
    failMessage = None                        # str
    calling = None                            # str
    workState = None                        # enum
    gcFlag = None                            # enum, can be None
    peerPacketQueue = None                    # deque<obj>


def _moi_key_to_str(moi):
    if moi.userName is None:
        return "%s, %s" % (moi.peerName, moi.moduleName)
    else:
        return "%s, %s, %s" % (moi.peerName, moi.userName, moi.moduleName)


def _moi_state_is_valid(moiState, failMessage):
    if moiState == _MoiObj.STATE_PENDING and failMessage == "":
        return True
    elif moiState == _MoiObj.STATE_ACTIVE and failMessage == "":
        return True
    elif moiState == _MoiObj.STATE_FULL and failMessage == "":
        return True
    elif moiState == _MoiObj.STATE_REJECT and failMessage != "":
        return True
    elif moiState == _MoiObj.STATE_PEER_REJECT and failMessage != "":
        return True
    elif moiState == _MoiObj.STATE_EXCEPT and failMessage != "":
        return True
    elif moiState == _MoiObj.STATE_PEER_EXCEPT and failMessage == "":
        return True
    elif moiState == _MoiObj.STATE_INACTIVE and failMessage == "":
        return True
    else:
        return False


def _moi_state_to_str(moiState):
    if moiState == _MoiObj.STATE_PENDING:
        return "STATE_PENDING"
    elif moiState == _MoiObj.STATE_ACTIVE:
        return "STATE_ACTIVE"
    elif moiState == _MoiObj.STATE_FULL:
        return "STATE_FULL"
    elif moiState == _MoiObj.STATE_REJECT:
        return "STATE_REJECT"
    elif moiState == _MoiObj.STATE_PEER_REJECT:
        return "STATE_PEER_REJECT"
    elif moiState == _MoiObj.STATE_EXCEPT:
        return "STATE_EXCEPT"
    elif moiState == _MoiObj.STATE_PEER_EXCEPT:
        return "STATE_PEER_EXCEPT"
    elif moiState == _MoiObj.STATE_INACTIVE:
        return "STATE_INACTIVE"
    else:
        assert False


def _map_module_name(moduleName):
    strList = moduleName.split("-")
    if strList[1] == "server":
        strList[1] = "client"
    elif strList[1] == "client":
        strList[1] = "server"
    return "-".join(strList)


def _type_check(obj, typeobj):
    return str(obj.__class__) == str(typeobj)
