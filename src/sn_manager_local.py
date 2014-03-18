#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import shutil
import socket
import logging
import traceback
import strict_pgs
from gi.repository import GLib

from sn_util import SnUtil
from sn_util import SnSleepNotifier
from sn_sub_proc import SnSubProcess
from sn_sub_proc import LocalSockSendObj
from sn_sub_proc import LocalSockCall
from sn_sub_proc import LocalSockRetn
from sn_sub_proc import LocalSockExcp
from sn_module import SnModuleInstance
from sn_module import SnRejectException

"""
ModuleInstance FSM trigger table:
  (STATE_INIT is the initial state)

  STATE_INIT        -> STATE_INACTIVE    : initialized
  STATE_INACTIVE    -> STATE_ACTIVE      : peer added, peer module added
  STATE_ACTIVE      -> STATE_INACTIVE    : peer removed, peer module removed

  STATE_ACTIVE      -> STATE_REJECT      : onRecv raise SnRejectException
  STATE_ACTIVE      -> STATE_PEER_REJECT : reject received
  STATE_REJECT      -> STATE_INACTIVE    : peer removed, peer module removed
  STATE_PEER_REJECT -> STATE_INACTIVE    : peer removed, peer module removed

  STATE_INIT        -> STATE_EXCEPT      : onInit raise exception
  STATE_INACTIVE    -> STATE_EXCEPT      : onActive raise exception
  STATE_ACTIVE      -> STATE_EXCEPT      : onRecv / onInactive raise exception
  STATE_ACTIVE      -> STATE_PEER_EXCEPT : except received
  STATE_REJECT      -> STATE_EXCEPT      : onInactive raise exception
  STATE_PEER_EXCEPT -> STATE_INACTIVE    : peer removed, peer module removed

"""

"""
ModuleInstance FSM event callback table:
  (module has no way to control the state change, it can only adapte to it)

  STATE_INIT     -> STATE_INACTIVE    : call onInit        BEFORE state change
  STATE_INACTIVE -> STATE_ACTIVE      : call onActive      AFTER state change
  STATE_ACTIVE   -> STATE_INACTIVE    : call onInactive    AFTER state change
  STATE_ACTIVE   -> STATE_REJECT      : call onInactive    AFTER state change
  STATE_ACTIVE   -> STATE_PEER_REJECT : call onInactive    AFTER state change
  STATE_ACTIVE   -> STATE_PEER_EXCEPT : call onInactive    AFTER state change

"""

"""
ModuleInstance FSM sendReject / sendExcept table:

  STATE_INIT        -> onInit     -> excGeneral   -> STATE_EXCEPT
  STATE_ACTIVE      -> onActive   -> excGeneral   -> STATE_EXCEPT -> sendExcept
  STATE_ACTIVE      -> onRecv     -> excGeneral   -> STATE_EXCEPT -> sendExcept
  STATE_INACTIVE    -> onInactive -> excGeneral   -> STATE_EXCEPT
  STATE_PEER_REJECT -> onInactive -> excGeneral   -> STATE_EXCEPT
  STATE_PEER_EXCEPT -> onInactive -> excGeneral   -> STATE_EXCEPT
  STATE_REJECT      -> onInactive -> return                       -> sendReject
  STATE_REJECT      -> onInactive -> excGeneral   -> STATE_EXCEPT -> sendExcept

"""

# fixme: needs to consider user change, both local user change and user change received by peer

class SnSysInfo:
	userList = None					# list<SnSysInfoUser>
	moduleList = None				# list<SnSysInfoModule>

class SnSysInfoUser:
	userName = None					# str

	def __eq__(self, other):
		return isinstance(other, self.__class__) and self.userName == other.userName
	def __ne__(self, other):
		return not self.__eq__(other)
	def __hash__(self):
		return hash(self.userName)

class SnSysInfoModule:
	moduleName = None				# str
	userName = None					# str

	def __eq__(self, other):
		return isinstance(other, self.__class__) and self.moduleName == other.moduleName and self.userName == other.userName
	def __ne__(self, other):
		return not self.__eq__(other)
	def __hash__(self):
		return hash(self.moduleName) ^ hash(self.userName)

class SnDataPacket:
	srcUserName = None				# str, can be None
	srcModuleName = None			# str
	data = None						# object

class SnDataPacketReject:
	message = None					# str

class SnDataPacketExcept:
	pass

class SnLocalManager:

	WORK_STATE_IDLE = 0
	WORK_STATE_WORKING = 1

	def __init__(self, param):
		logging.debug("SnLocalManager.__init__: Start")

		# variables
		self.param = param
		self.localInfo = self._getLocalInfo()
		self.poiDict = self._getPoiDict()
		self.sleepNotifier = SnSleepNotifier(self.onBeforeSleep, self.onAfterResume)

		GLib.idle_add(self._idleInitMoiList)
		GLib.idle_add(self._idleLocalPeerActive)

		logging.debug("SnLocalManager.__init__: End")
		return

	def dispose(self):
		logging.debug("SnLocalManager.dispose: Start")

		self.localInfo = None
		self.onPeerChange(socket.gethostname(), None)

		for pname, moiList in self.poiDict.items():
			for moi in moiList:
				assert moi.state in [ _ModuleObjInternal.STATE_EXCEPT, _ModuleObjInternal.STATE_INACTIVE ]

		logging.debug("SnLocalManager.dispose: End")
		return

	def getLocalInfo(self):
		return self.localInfo

	def getWorkState(self):
		for pname, moiList in self.poiDict.items():
			for moi in moiList:
				if moi.workState == SnModuleInstance.WORK_STATE_WORKING:
					return SnLocalManager.WORK_STATE_WORKING
		return SnLocalManager.WORK_STATE_IDLE

	def getModuleKeyList(self):
		ret = []
		for pname, moiList in self.poiDict.items():
			for moi in moiList:
				ret.append((moi.peerName, moi.userName, moi.moduleName))
		return ret

	def getModuleState(self, peerName, userName, moduleName):
		moi = self._getMoi(peerName, userName, moduleName)
		return (moi.state, moi.failMessage)

	##### event callback ####

	def onPeerChange(self, peerName, peerInfo):
		logging.debug("SnLocalManager.onPeerChange: Start, %s", peerName)

		moiList = self.poiDict[peerName]
		for moi in moiList:
			self._moiPeerUpdate(peerName, peerInfo, moi)

		logging.debug("SnLocalManager.onPeerChange: End")
		return

	def onPeerSockRecv(self, peerName, userName, srcModuleName, data):
		moi = self._getMoiMapped(peerName, userName, srcModuleName)
		if moi.state != _ModuleObjInternal.STATE_ACTIVE:
			return

		if self._typeCheck(data, SnDataPacketReject):
			self._moiChangeState(moi, _ModuleObjInternal.STATE_PEER_REJECT)
			self._moiCallFunc(moi, "onInactive")
		elif self._typeCheck(data, SnDataPacketExcept):
			self._moiChangeState(moi, _ModuleObjInternal.STATE_PEER_EXCEPT)
			self._moiCallFunc(moi, "onInactive")
		else:
			self._moiCallFunc(moi, "onRecv", data)

	def onLocalSockRecv(self, peerName, userName, moduleName, packetObj):
		moi = self._getMoi(peerName, userName, moduleName)
		if self._typeCheck(packetObj, LocalSockSendObj):
			self._sendObject(packetObj.peerName, packetObj.userName, packetObj.moduleName, packetObj.dataObj)
		elif self._typeCheck(packetObj, LocalSockRetn):
			self._moiCallFuncReturn(moi, packetObj.retVal)
		elif self._typeCheck(packetObj, LocalSockExcp):
			self._moiCallFuncExcept(packetObj, packetObj.excObj, packetObj.excInfo)
		else:
			assert False

	def onBeforeSleep(self, sleepType):
		pass

	def onAfterResume(self, sleepType):
		pass

	##### implementation ####

	def _sendObject(self, peerName, userName, moduleName, obj):
		if peerName == socket.gethostname():
			GLib.idle_add(self._idleLocalPeerRecv, peerName, userName, moduleName, obj)
		else:
			self.param.peerManager._sendDataObject(peerName, userName, moduleName, obj)

	def _sendReject(self, peerName, userName, moduleName, rejectMessage):
		logging.warning("SnLocalManager.sendReject, %s, %s, %s, %s", peerName, userName, moduleName, rejectMessage)

		messageObj = SnDataPacketReject()
		messageObj.message = rejectMessage
		if peerName == socket.gethostname():
			GLib.idle_add(self._idleLocalPeerRecv, peerName, userName, moduleName, messageObj)
		else:
			self.param.peerManager._sendDataObject(peerName, userName, moduleName, messageObj)

	def _sendExcept(self, peerName, userName, moduleName):
		logging.warning("SnLocalManager.sendExcept, %s, %s, %s", peerName, userName, moduleName)

		messageObj = SnDataPacketExcept()
		if peerName == socket.gethostname():
			GLib.idle_add(self._idleLocalPeerRecv, peerName, userName, moduleName, messageObj)
		else:
			self.param.peerManager._sendDataObject(peerName, userName, moduleName, messageObj)

	def _setWorkState(self, peerName, userName, moduleName, workState):
		moi = self._getMoi(peerName, userName, moduleName)
		assert moi.state == _ModuleObjInternal.STATE_ACTIVE
		moi.workState = workState

	def _idleLocalPeerActive(self):
		self.onPeerChange(socket.gethostname(), self.localInfo)
		return False

	def _idleLocalPeerRecv(self, peerName, userName, moduleName, data):
		self.onPeerSockRecv(peerName, userName, moduleName, data)
		return False

	def _idleInitMoiList(self):
		for pname, moiList in self.poiDict.items():
			for moi in moiList:
				if not moi.propDict["standalone"]:
					exec("from %s import ModuleInstanceObject"%(moi.moduleName.replace("-", "_")))
					moi.mo = ModuleInstanceObject(self, moi.peerName, moi.userName, moi.moduleName, moi.tmpDir)
				else:
					moi.proc = SnSubProcess(moi.peerName, moi.userName, moi.moduleName, moi.tmpDir, self.onLocalSockRecv, None)
					moi.proc.start()
				moi.state = _ModuleObjInternal.STATE_INIT
				moi.failMessage = ""
				moi.workState = SnModuleInstance.WORK_STATE_IDLE
				self._moiCallFunc(moi, "onInit")

	def _getLocalInfo(self):
		pgs = strict_pgs.PasswdGroupShadow("/")
		ret = SnSysInfo()

		ret.userList = []
		for uname in pgs.getNormalUserList():
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
				for uname in pgs.getNormalUserList():
					if uname in self.param.configManager.getUserBlackList():
						continue
					n = SnSysInfoModule()
					n.moduleName = mname
					n.userName = uname
					ret.moduleList.append(n)
			else:
				assert False

		return ret

	def _getPoiDict(self):
		"""Create a full module object collection"""

		pgs = strict_pgs.PasswdGroupShadow("/")
		poiDict = dict()
		for pname in self.param.configManager.getHostNameList():
			moiList = []
			for mname in self.param.configManager.getModuleNameList():
				minfo = self.param.configManager.getModuleInfo(mname)
				if pname == socket.gethostname() and not minfo.moduleObj.getPropDict()["allow-local-peer"]:
					continue
				if minfo.moduleScope == "sys":
					moi = _ModuleObjInternal()
					moi.peerName = pname
					moi.userName = None
					moi.moduleName = mname
					moi.moduleScope = minfo.moduleScope
					moi.moduleType = minfo.moduleType
					moi.moduleId = minfo.moduleId
					moi.propDict = minfo.moduleObj.getPropDict()
					moi.tmpDir = os.path.join(self.param.tmpDir, mname)
					moiList.append(moi)
				elif minfo.moduleScope == "usr":
					for uname in pgs.getNormalUserList():
						if uname in self.param.configManager.getUserBlackList():
							continue
						moi = _ModuleObjInternal()
						moi.peerName = pname
						moi.userName = uname
						moi.moduleName = mname
						moi.moduleScope = minfo.moduleScope
						moi.moduleType = minfo.moduleType
						moi.moduleId = minfo.moduleId
						moi.propDict = minfo.moduleObj.getPropDict()
						moi.tmpDir = os.path.join(self.param.tmpDir, "%s-%s"%(mname, uname))
						moiList.append(moi)
				else:
					assert False
			poiDict[pname] = moiList
		return poiDict

	def _getMoi(self, peerName, userName, moduleName):
		moiList = self.poiDict[peerName]
		for moi in moiList:
			assert moi.peerName == peerName
			if moi.userName == userName and moi.moduleName == moduleName:
				return moi
		assert False

	def _getMoiMapped(self, peerName, userName, srcModuleName):
		moi = self._findMoiMapped(peerName, userName, srcModuleName)
		assert moi is not None
		return moi

	def _findMoiMapped(self, peerName, userName, srcModuleName):
		moiList = self.poiDict[peerName]
		for moi in self.moiList:
			assert moi.peerName == peerName
			if moi.userName == userName and moi.moduleName == self._mapModuleName(srcModuleName):
				return moi
		return None

	def _matchMoiMapped(self, peerName, userName, srcModuleName):
		moi = self._findMoiMapped(peerName, userName, srcModuleName)
		return moi is not None

	def _matchPmi(self, peerName, peerInfo, moi):
		"""pmi stands for peer-module-info"""

		assert moi.peerName == peerName
		for pmi in peerInfo.moduleList:
			if moi.userName == pmi.userName and moi.moduleName == self._mapModuleName(pmi.moduleName):
				return True
		return False

	def _mapModuleName(self, moduleName):
		strList = moduleName.split("-")
		if strList[1] == "server":
			strList[1] = "client"
		elif strList[1] == "client":
			strList[1] = "server"
		return "-".join(strList)

	def _typeCheck(self, obj, typeobj):
		return str(obj.__class__) == str(typeobj)

	def _moiChangeState(self, moi, newState, failMessage=""):
		if newState in [ _ModuleObjInternal.STATE_REJECT, _ModuleObjInternal.STATE_PEER_REJECT, _ModuleObjInternal.STATE_EXCEPT ]:
			assert failMessage != ""
		else:
			assert failMessage == ""

		logging.info("SnLocalManager.moiChangeState: %s -> %s, %s", _module_state_to_str(moi.state), 
				_module_state_to_str(newState), _dbgmsg_moi_key(moi))
		moi.state = newState
		moi.failMessage = failMessage

	def _moiCallFunc(self, moi, funcName, *args):
		assert moi.calling is None

		logging.debug("SnLocalManager.moiCallFunc: %s, call, %s", funcName, _dbgmsg_moi_key(moi))
		moi.calling = funcName

		if moi.mo is not None:
			GLib.idle_add(self._idleMoiCallFuncImpl, moi, *args)
		elif moi.proc is not None:
			p = LocalSockCall()
			p.funcName = funcName
			p.funcArgs = args
			moi.proc.get_pipe().send(p)
		else:
			assert False

	def _idleMoiCallFuncImpl(self, moi, *args):
		ret = None
		try:
			exec("ret = SnUtil.euidInvoke(moi.userName, moi.mo.%s, *args)"%(moi.calling))
		except Exception as e:
			self._moiCallFuncExcept(moi, e, traceback.format_exc())
			return
		shutil.rmtree(moi.tmpDir, True)
		self._moiCallFuncReturn(moi, ret)

	def _moiCallFuncReturn(self, moi, retVal):
		# finish function call
		funcName = moi.calling
		logging.debug("SnLocalManager.moiCallFunc: %s, return, %s", moi.calling, _dbgmsg_moi_key(moi))
		moi.calling = None

		# do post call operation
		if funcName == "onInit":
			self._moiChangeState(moi, _ModuleObjInternal.STATE_INACTIVE)
		elif funcName == "onInactive":
			assert moi.workState == SnModuleInstance.WORK_STATE_IDLE
			if moi.state == _ModuleObjInternal.STATE_REJECT:
				self._sendReject(moi.peerName, moi.userName, moi.moduleName, moi.failMessage)
		elif funcName == "onActive":
			pass
		elif funcName == "onRecv":
			pass
		else:
			assert False

		# do peer update
		if moi.peerName == socket.gethostname():
			self._moiPeerUpdate(moi.peerName, self.localInfo, moi)
		else:
			peerInfo = self.param.peerManager.getPeerInfo(moi.peerName)
			self._moiPeerUpdate(moi.peerName, peerInfo, moi)
		
	def _moiCallFuncExcept(self, moi, excObj, excInfo):
		# finish function call
		funcName = moi.calling
		logging.debug("SnLocalManager.moiCallFunc: %s, except, %s, %s, %s", moi.calling, 
				_dbgmsg_moi_key(moi), excObj.__class__, excObj)
		moi.calling = None

		# do post call operation
		if funcName == "onInit":
			moi.workState = SnModuleInstance.WORK_STATE_IDLE
			self._moiChangeState(moi, _ModuleObjInternal.STATE_EXCEPT, excInfo)
		elif funcName == "onInactive":
			moi.workState = SnModuleInstance.WORK_STATE_IDLE
			self._moiChangeState(moi, _ModuleObjInternal.STATE_EXCEPT, excInfo)
			if moi.state == _ModuleObjInternal.STATE_REJECT:
				self._sendExcept(moi.peerName, moi.userName, moi.moduleName)
		elif funcName == "onActive":
			moi.workState = SnModuleInstance.WORK_STATE_IDLE
			self._moiChangeState(moi, _ModuleObjInternal.STATE_EXCEPT, excInfo)
			self._sendExcept(moi.peerName, moi.userName, moi.moduleName)
		elif funcName == "onRecv":
			if self._typeCheck(excObj, SnRejectException):
				self._moiChangeState(moi, _ModuleObjInternal.STATE_REJECT, excObj.message)
				self._moiCallFunc(moi, "onInactive")
			else:
				moi.workState = SnModuleInstance.WORK_STATE_IDLE
				self._moiChangeState(moi, _ModuleObjInternal.STATE_EXCEPT, excInfo)
				self._sendExcept(moi.peerName, moi.userName, moi.moduleName)
		else:
			assert False

		# do peer update
		if moi.peerName == socket.gethostname():
			self._moiPeerUpdate(moi.peerName, self.localInfo, moi)
		else:
			peerInfo = self.param.peerManager.getPeerInfo(moi.peerName)
			self._moiPeerUpdate(moi.peerName, peerInfo, moi)

	def _moiPeerUpdate(self, peerName, peerInfo, moi):
		if moi.calling is not None:
			return

		if peerInfo is not None and self._matchPmi(peerName, peerInfo, moi):
			# peer exist
			if moi.state == _ModuleObjInternal.STATE_INIT:
				pass
			elif moi.state == _ModuleObjInternal.STATE_ACTIVE:
				pass
			elif moi.state == _ModuleObjInternal.STATE_INACTIVE:
				self._moiChangeState(moi, _ModuleObjInternal.STATE_ACTIVE)
				self._moiCallFunc(moi, "onActive")
			elif moi.state == _ModuleObjInternal.STATE_REJECT:
				pass
			elif moi.state == _ModuleObjInternal.STATE_PEER_REJECT:
				pass
			elif moi.state == _ModuleObjInternal.STATE_EXCEPT:
				pass
			elif moi.state == _ModuleObjInternal.STATE_PEER_EXCEPT:
				pass
			else:
				assert False
		else:
			# peer not exist
			if moi.state == _ModuleObjInternal.STATE_INIT:
				pass
			elif moi.state == _ModuleObjInternal.STATE_ACTIVE:
				self._moiChangeState(moi, _ModuleObjInternal.STATE_INACTIVE)
				self._moiCallFunc(moi, "onInactive")
			elif moi.state == _ModuleObjInternal.STATE_INACTIVE:
				pass
			elif moi.state == _ModuleObjInternal.STATE_REJECT:
				self._moiChangeState(moi, _ModuleObjInternal.STATE_INACTIVE)
			elif moi.state == _ModuleObjInternal.STATE_PEER_REJECT:
				self._moiChangeState(moi, _ModuleObjInternal.STATE_INACTIVE)
			elif moi.state == _ModuleObjInternal.STATE_EXCEPT:
				pass
			elif moi.state == _ModuleObjInternal.STATE_PEER_EXCEPT:
				self._moiChangeState(moi, _ModuleObjInternal.STATE_INACTIVE)
			else:
				assert False

class _PeerObjInternal:
	PEER_STATE_IN_INIT
	PEER_STATE_IN_ACTIVE
	PEER_STATE_IN_INACTIVE

	state = None
	packetQueue = None						# List<obj>
	moiList = None							# List<_ModuleInfoInternal

class _ModuleObjInternal:
	STATE_INIT = 0
	STATE_INACTIVE = 1
	STATE_ACTIVE = 2
	STATE_REJECT = 3
	STATE_PEER_REJECT = 4
	STATE_EXCEPT = 5
	STATE_PEER_EXCEPT = 6

	peerName = None							# str
	userName = None							# str, can be None
	moduleName = None						# str, "sys-server-name"
	moduleScope = None						# str, "sys" "usr"
	moduleType = None						# str, "server" "client" "peer"
	moduleId = None							# str
	propDict = None							# dict
	tmpDir = None							# str
	mo = None								# obj, SnModuleInstance, standalone module: None
	proc = None								# obj, not-standalone module: None
	state = None							# enum
	failMessage = None						# str
	calling = None							# str
	workState = None						# enum

def _dbgmsg_moi_key(moi):
	if moi.userName is None:
		return "%s, %s"%(moi.peerName, moi.moduleName)
	else:
		return "%s, %s, %s"%(moi.peerName, moi.userName, moi.moduleName)

def _module_state_to_str(moduleState):
	if moduleState == _ModuleObjInternal.STATE_INIT:
		return "STATE_INIT"
	elif moduleState == _ModuleObjInternal.STATE_INACTIVE:
		return "STATE_INACTIVE"
	elif moduleState == _ModuleObjInternal.STATE_ACTIVE:
		return "STATE_ACTIVE"
	elif moduleState == _ModuleObjInternal.STATE_REJECT:
		return "STATE_REJECT"
	elif moduleState == _ModuleObjInternal.STATE_PEER_REJECT:
		return "STATE_PEER_REJECT"
	elif moduleState == _ModuleObjInternal.STATE_EXCEPT:
		return "STATE_EXCEPT"
	elif moduleState == _ModuleObjInternal.STATE_PEER_EXCEPT:
		return "STATE_PEER_EXCEPT"
	else:
		assert False

