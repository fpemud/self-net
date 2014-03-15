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
from sn_conn_local import SnLocalServer
from sn_module import SnRejectException

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
		self.moduleObjDict = self._getModuleObjDict()
		self.sleepNotifier = SnSleepNotifier(self.onBeforeSleep, self.onAfterResume)

		# init modules
		self._initModuleObjDict()

		# active local peers
		GLib.idle_add(self._idleLocalPeerActive)

		logging.debug("SnLocalManager.__init__: End")
		return

	def dispose(self):
		logging.debug("SnLocalManager.dispose: Start")

		# set modules of local peer to inactive state
		if socket.gethostname() in self.moduleObjDict:
			self.onPeerRemove(socket.gethostname())

		# check modules' state
		for moiList in self.moduleObjDict.values():
			for moi in moiList:
				assert moi.state in [ _ModuleInfoInternal.STATE_EXCEPT, _ModuleInfoInternal.STATE_INACTIVE ]

		logging.debug("SnLocalManager.dispose: End")
		return

	def getLocalInfo(self):
		return self.localInfo

	def getWorkState(self):
		for moiList in self.moduleObjDict.values():
			for moi in moiList:
				if moi.workState == _ModuleInfoInternal.WORK_STATE_WORKING:
					return SnLocalManager.WORK_STATE_WORKING
		return SnLocalManager.WORK_STATE_IDLE

	def getModuleKeyList(self):
		ret = []
		for moiList in self.moduleObjDict.values():
			for moi in moiList:
				ret.append((moi.peerName, moi.userName, moi.moduleName))
		return ret

	def getModuleState(self, peerName, userName, moduleName):
		moi = self._getMoi(peerName, userName, moduleName)
		return (moi.state, moi.failMessage)

	##### event callback ####

	def onPeerChange(self, peerName, peerInfo):
		logging.debug("SnLocalManager.onPeerChange: Start, %s", peerName)

		# no peer module
		for moi in self.moduleObjDict[peerName]:
			if self._matchPmi(peerName, peerInfo, moi):
				continue

			if moi.state == _ModuleInfoInternal.STATE_ACTIVE:
				logging.debug("SnLocalManager.onPeerChange: mo active -> inactive start, %s", _dbgmsg_moi_key(moi))
				try:
					moi.state = _ModuleInfoInternal.STATE_INACTIVE
					moi.failMessage = ""
					SnUtil.euidInvoke(moi.userName, moi.mo.onInactive)
					shutil.rmtree(moi.tmpDir, True)
					logging.debug("SnLocalManager.onPeerChange: mo active -> inactive end")
				except Exception as e:
					moi.state = _ModuleInfoInternal.STATE_EXCEPT
					moi.failMessage = traceback.format_exc()
					logging.debug("SnLocalManager.onPeerChange: mo onInactive failed, %s, %s", e.__class__, e)
			elif moi.state == _ModuleInfoInternal.STATE_INACTIVE:
				pass
			elif moi.state == _ModuleInfoInternal.STATE_REJECT:
				logging.debug("SnLocalManager.onPeerChange: mo reject -> inactive start, %s", _dbgmsg_moi_key(moi))
				moi.state = _ModuleInfoInternal.STATE_INACTIVE
				moi.failMessage = ""
				logging.debug("SnLocalManager.onPeerChange: mo reject -> inactive end")
			elif moi.state == _ModuleInfoInternal.STATE_PEER_REJECT:
				logging.debug("SnLocalManager.onPeerChange: mo peer_reject -> inactive start, %s", _dbgmsg_moi_key(moi))
				moi.state = _ModuleInfoInternal.STATE_INACTIVE
				moi.failMessage = ""
				logging.debug("SnLocalManager.onPeerChange: mo peer_reject -> inactive end")
			elif moi.state == _ModuleInfoInternal.STATE_EXCEPT:
				pass
			elif moi.state == _ModuleInfoInternal.STATE_PEER_EXCEPT:
				logging.debug("SnLocalManager.onPeerChange: mo peer_except -> inactive start, %s", _dbgmsg_moi_key(moi))
				moi.state = _ModuleInfoInternal.STATE_INACTIVE
				moi.failMessage = ""
				logging.debug("SnLocalManager.onPeerChange: mo peer_except -> inactive end")
			else:
				assert False

		# has peer module
		for pmi in peerInfo.moduleList:
			moi = self._findMoiMapped(peerName, pmi.userName, pmi.moduleName)
			if moi is None:
				continue

			# found module
			if moi.state == _ModuleInfoInternal.STATE_ACTIVE:
				pass
			elif moi.state == _ModuleInfoInternal.STATE_INACTIVE:
				logging.debug("SnLocalManager.onPeerChange: mo inactive -> active start, %s", _dbgmsg_moi_key(moi))
				try:
					moi.state = _ModuleInfoInternal.STATE_ACTIVE
					moi.failMessage = ""
					SnUtil.euidInvoke(moi.userName, moi.mo.onActive)
					logging.debug("SnLocalManager.onPeerChange: mo inactive -> active end")
				except Exception as e:
					self._toExceptWithMessage(moi, traceback.format_exc())
					logging.debug("SnLocalManager.onPeerChange: mo onActive failed, %s, %s", e.__class__, e)
			elif moi.state == _ModuleInfoInternal.STATE_REJECT:
				pass
			elif moi.state == _ModuleInfoInternal.STATE_PEER_REJECT:
				pass
			elif moi.state == _ModuleInfoInternal.STATE_EXCEPT:
				pass
			elif moi.state == _ModuleInfoInternal.STATE_PEER_EXCEPT:
				pass
			else:
				assert False

		logging.debug("SnLocalManager.onPeerChange: End")
		return

	def onPeerRemove(self, peerName):
		logging.debug("SnLocalManager.onPeerRemove: Start, %s", peerName)

		for moi in self.moduleObjDict[peerName]:
			if moi.state == _ModuleInfoInternal.STATE_ACTIVE:
				logging.debug("SnLocalManager.onPeerRemove: mo active -> inactive start, %s", _dbgmsg_moi_key(moi))
				try:
					moi.state = _ModuleInfoInternal.STATE_INACTIVE
					moi.failMessage = ""
					SnUtil.euidInvoke(moi.userName, moi.mo.onInactive)
					shutil.rmtree(moi.tmpDir, True)
					logging.debug("SnLocalManager.onPeerRemove: mo active -> inactive end")
				except Exception as e:
					moi.state = _ModuleInfoInternal.STATE_EXCEPT
					moi.failMessage = traceback.format_exc()
					logging.debug("SnLocalManager.onPeerChange: mo onInactive failed, %s, %s", e.__class__, e)
			elif moi.state == _ModuleInfoInternal.STATE_INACTIVE:
				pass
			elif moi.state == _ModuleInfoInternal.STATE_REJECT:
				logging.debug("SnLocalManager.onPeerRemove: mo reject -> inactive start, %s", _dbgmsg_moi_key(moi))
				moi.state = _ModuleInfoInternal.STATE_INACTIVE
				moi.failMessage = ""
				logging.debug("SnLocalManager.onPeerRemove: mo reject -> inactive end")
			elif moi.state == _ModuleInfoInternal.STATE_PEER_REJECT:
				logging.debug("SnLocalManager.onPeerRemove: mo peer_reject -> inactive start, %s", _dbgmsg_moi_key(moi))
				moi.state = _ModuleInfoInternal.STATE_INACTIVE
				moi.failMessage = ""
				logging.debug("SnLocalManager.onPeerRemove: mo peer_reject -> inactive end")
			elif moi.state == _ModuleInfoInternal.STATE_EXCEPT:
				pass
			elif moi.state == _ModuleInfoInternal.STATE_PEER_EXCEPT:
				logging.debug("SnLocalManager.onPeerRemove: mo peer_except -> inactive start, %s", _dbgmsg_moi_key(moi))
				moi.state = _ModuleInfoInternal.STATE_INACTIVE
				moi.failMessage = ""
				logging.debug("SnLocalManager.onPeerRemove: mo peer_except -> inactive end")
			else:
				assert False

		logging.debug("SnLocalManager.onPeerRemove: End")
		return

	def onPacketRecv(self, peerName, userName, srcModuleName, data):
		logging.debug("SnLocalManager.onPacketRecv: Start, %s, %s, %s", peerName, userName, srcModuleName)

		moi = self._getMoiMapped(peerName, userName, srcModuleName)
		assert moi.state == _ModuleInfoInternal.STATE_ACTIVE

		if self._typeCheck(data, SnDataPacketReject):
			try:
				moi.state = _ModuleInfoInternal.STATE_PEER_REJECT
				moi.failMessage = ""
				SnUtil.euidInvoke(moi.userName, moi.mo.onInactive)
				shutil.rmtree(moi.tmpDir, True)
			except Exception as e:
				moi.state = _ModuleInfoInternal.STATE_EXCEPT
				moi.failMessage = traceback.format_exc()
				logging.debug("SnLocalManager.onPacketRecv: mo onInactive failed, %s, %s", e.__class__, e)
		elif self._typeCheck(data, SnDataPacketExcept):
			try:
				moi.state = _ModuleInfoInternal.STATE_PEER_EXCEPT
				moi.failMessage = ""
				SnUtil.euidInvoke(moi.userName, moi.mo.onInactive)
				shutil.rmtree(moi.tmpDir, True)
			except Exception as e:
				moi.state = _ModuleInfoInternal.STATE_EXCEPT
				moi.failMessage = traceback.format_exc()
				logging.debug("SnLocalManager.onPacketRecv: mo onInactive failed, %s, %s", e.__class__, e)
		else:
			try:
				SnUtil.euidInvoke(moi.userName, moi.mo.onRecv, data)
			except SnRejectException as e:
				self._toRejectWithMessage(moi, e.message)
				logging.debug("SnLocalManager.onPacketRecv: mo onRecv failed, %s, %s", e.__class__, e)
			except Exception as e:
				self._toExceptWithMessage(moi, traceback.format_exc())
				logging.debug("SnLocalManager.onPacketRecv: mo onRecv failed, %s, %s", e.__class__, e)

		logging.debug("SnLocalManager.onPacketRecv: End")

	def onBeforeSleep(self, sleepType):
		pass

	def onAfterResume(self, sleepType):
		pass

	def onLoSockRecv(self, peerName, userName, moduleName, packetObj):
		moi = self._getMoi(peerName, userName, moduleName)

		if self._typeCheck(packetObj, _LoSockInitComplete):
			assert moi.state == _ModuleInfoInternal.STATE_INIT
			p = _LoSockCall()
			p.funcName = "onInit"
			p.funcArgs = []
			moi.proc.get_pipe().send(p)
			moi.calling = _ModuleInfoInternal.CALLING_ON_INIT
		elif self._typeCheck(packetObj, _LoSockSendObj):
			assert moi.state == _ModuleInfoInternal.STATE_ACTIVE:
			self._sendObject(packetObj.peerName, packetObj.userName, packetObj.moduleName, packetObj.dataObj)
		elif self._typeCheck(packetObj, _LoSockRetn):
			if moi.calling == _ModuleInfoInternal.CALLING_NONE:
				assert False
			elif moi.calling == _ModuleInfoInternal.CALLING_ON_INIT:
				peerInfo = self.param.peerManager.getPeerInfo(moi.peerName)
				if peerInfo is not None and self._matchPmi(moi.peerName, self.param.peerManager.getPeerInfo(moi.peerName), moi):
					moi.state = _ModuleInfoInternal.STATE_ACTIVE
					moi.failMessage = ""
					p = _LoSockCall()
					p.funcName = "onActive"
					p.funcArgs = []
					moi.proc.get_pipe().send(p)
					moi.calling = _ModuleInfoInternal.CALLING_ON_ACTIVE
				else:
					moi.state = _ModuleInfoInternal.STATE_INACTIVE
					moi.failMessage = ""
			elif moi.calling == _ModuleInfoInternal.CALLING_ON_INACTIVE:
				pass
			elif moi.calling == _ModuleInfoInternal.CALLING_ON_ACTIVE:
				pass
			elif moi.calling == _ModuleInfoInternal.CALLING_ON_RECV:
				pass
			else:
				assert False
		elif self._typeCheck(packetObj, _LoSockExcp):
			if moi.calling == _ModuleInfoInternal.CALLING_NONE:
				assert False
			elif moi.calling in [ _ModuleInfoInternal.CALLING_ON_INIT, _ModuleInfoInternal.CALLING_ON_INACTIVE ]:
				moi.state = _ModuleInfoInternal.STATE_EXCEPT
				moi.failMessage = packetObj.excInfo
			elif moi.calling == _ModuleInfoInternal.CALLING_ON_ACTIVE:
				self._toExceptWithMessage(moi, packetObj.excInfo)
			elif moi.calling == _ModuleInfoInternal.CALLING_ON_RECV:
				if _typeCheck(packetObj.excObj, SnRejectException):
					self._toRejectWithMessage(moi, packetObj.excObj.message)
				else:
					self._toExceptWithMessage(moi, packetObj.excInfo)
			else:
				assert False
		else:
			assert False

	##### implementation ####

	def _sendObject(self, peerName, userName, moduleName, obj):
		if peerName == socket.gethostname():
			GLib.idle_add(self._idleLocalPeerRecv, peerName, userName, moduleName, obj)
		else:
			self.param.peerManager._sendDataObject(peerName, userName, moduleName, obj)

	def _toExceptWithMessage(self, moi, exceptMessage):
		moi.state = _ModuleInfoInternal.STATE_EXCEPT
		moi.failMessage = exceptMessage
		self._sendExcept(moi.peerName, moi.userName, moi.moduleName)

	def _toRejectWithMessage(self, moi, rejectMessage):
		try:
			moi.state = _ModuleInfoInternal.STATE_REJECT
			moi.failMessage = rejectMessage
			SnUtil.euidInvoke(moi.userName, moi.mo.onInactive)
			shutil.rmtree(moi.tmpDir, True)
			self._sendReject(moi.peerName, moi.userName, moi.moduleName, rejectMessage)
		except Exception as e:
			self._toExceptWithMessage(moi, traceback.format_exc())
			logging.debug("SnLocalManager._toReject: mo onInactive failed, %s, %s", e.__class__, e)

	def _sendReject(self, peerName, userName, moduleName, rejectMessage):
		logging.warning("send reject, %s, %s, %s, %s", peerName, userName, moduleName, rejectMessage)

		messageObj = SnDataPacketReject()
		messageObj.message = rejectMessage
		if peerName == socket.gethostname():
			GLib.idle_add(self._idleLocalPeerRecv, peerName, userName, moduleName, messageObj)
		else:
			self.param.peerManager._sendDataObject(peerName, userName, moduleName, messageObj)

	def _sendExcept(self, peerName, userName, moduleName):
		logging.warning("send except, %s, %s, %s", peerName, userName, moduleName)

		messageObj = SnDataPacketExcept()
		if peerName == socket.gethostname():
			GLib.idle_add(self._idleLocalPeerRecv, peerName, userName, moduleName, messageObj)
		else:
			self.param.peerManager._sendDataObject(peerName, userName, moduleName, messageObj)

	def _idleLocalPeerActive(self):
		self.onPeerChange(socket.gethostname(), self.localInfo)
		return False

	def _idleLocalPeerRecv(self, peerName, userName, moduleName, data):
		self.onPacketRecv(peerName, userName, moduleName, data)
		return False

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

	def _getModuleObjDict(self):
		"""Create a full module object collection"""

		pgs = strict_pgs.PasswdGroupShadow("/")
		ret = dict()

		# create self.moduleObjDict
		for pname in self.param.configManager.getHostNameList():
			moiList = []
			for mname in self.param.configManager.getModuleNameList():
				minfo = self.param.configManager.getModuleInfo(mname)
				if pname == socket.gethostname() and not minfo.moduleObj.getPropDict()["allow-local-peer"]:
					continue
				if minfo.moduleScope == "sys":
					moi = _ModuleInfoInternal()
					moi.peerName = pname
					moi.userName = None
					moi.moduleName = mname
					moi.moduleScope = minfo.moduleScope
					moi.moduleType = minfo.moduleType
					moi.moduleId = minfo.moduleId
					moi.tmpDir = os.path.join(self.param.tmpDir, mname)
					moiList.append(moi)
				elif minfo.moduleScope == "usr":
					for uname in pgs.getNormalUserList():
						if uname in self.param.configManager.getUserBlackList():
							continue
						moi = _ModuleInfoInternal()
						moi.peerName = pname
						moi.userName = uname
						moi.moduleName = mname
						moi.moduleScope = minfo.moduleScope
						moi.moduleType = minfo.moduleType
						moi.moduleId = minfo.moduleId
						moi.tmpDir = os.path.join(self.param.tmpDir, "%s-%s"%(mname, uname)
						moiList.append(moi)
				else:
					assert False
			ret[pname] = moiList

		# create SnModuleInstance
		for moiList in ret.values():
			for moi in moiList:
				exec("from %s import ModuleInstanceObject"%(moi.moduleName.replace("-", "_")))
				moi.mo = ModuleInstanceObject(self, moi.peerName, moi.userName, moi.moduleName, moi.tmpDir)
				moi.state = _ModuleInfoInternal.STATE_INIT
				moi.failMessage = ""
				moi.calling = _ModuleInfoInternal.CALLING_NONE

		return ret

	def _initModuleObjDict(self):
		for moiList in self.moduleObjDict.values():
			for moi in moiList:
				logging.debug("SnLocalManager._getModuleObjDict: mo init, %s, %s, %s", moi.peerName, moi.userName, moi.moduleName)
				try:
					SnUtil.euidInvoke(moi.userName, moi.mo.onInit)
					moi.state = _ModuleInfoInternal.STATE_INACTIVE
					moi.failMessage = ""
					logging.debug("SnLocalManager._getModuleObjDict: mo init end")
				except Exception as e:
					moi.state = _ModuleInfoInternal.STATE_EXCEPT
					moi.failMessage = traceback.format_exc()
					logging.debug("SnLocalManager._getModuleObjDict: mo onInit failed, %s, %s", e.__class__, e)

	def _getMoi(self, peerName, userName, moduleName):
		for moi in self.moduleObjDict[peerName]:
			if moi.userName == userName and moi.moduleName == moduleName:
				return moi
		assert False

	def _getMoiMapped(self, peerName, userName, srcModuleName):
		moi = self._findMoiMapped(peerName, userName, srcModuleName)
		assert moi is not None
		return moi

	def _findMoiMapped(self, peerName, userName, srcModuleName):
		for moi in self.moduleObjDict[peerName]:
			if moi.userName == userName and moi.moduleName == self._mapModuleName(srcModuleName):
				return moi
		return None

	def _matchMoiMapped(self, peerName, userName, srcModuleName):
		moi = self._findMoiMapped(peerName, userName, srcModuleName)
		return moi is not None

	def _matchPmi(self, peerName, peerInfo, moi):
		"""pmi stands for peer-module-info"""

		for pmi in peerInfo.moduleList:
			if (moi.peerName == peerName and moi.userName == pmi.userName
					and moi.moduleName == self._mapModuleName(pmi.moduleName)):
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

class _ModuleInfoInternal:
	STATE_INIT = 0
	STATE_INACTIVE = 1
	STATE_ACTIVE = 2
	STATE_REJECT = 3
	STATE_PEER_REJECT = 4
	STATE_EXCEPT = 5
	STATE_PEER_EXCEPT = 6

	WORK_STATE_IDLE = 0
	WORK_STATE_WORKING = 1

	CALLING_NONE = 0
	CALLING_ON_INIT = 1
	CALLING_ON_ACTIVE = 2
	CALLING_ON_INACTIVE = 3
	CALLING_ON_RECV = 4

	peerName = None							# str
	userName = None							# str, can be None
	moduleName = None						# str, "sys-server-name"
	moduleScope = None						# str, "sys" "usr"
	moduleType = None						# str, "server" "client" "peer"
	moduleId = None							# str
	tmpDir = None							# str
	mo = None								# obj, SnModuleInstance, standalone module: None
	proc = None								# obj, not-standalone module: None
	state = None							# enum
	failMessage = None						# str
	calling = None							# enum
	workState = None						# enum

class _LoSockInitComplete:
	pass

class _LoSockSendObj:
	peerName = None							# str
	userName = None							# str
	moduleName = None						# str
	dataObj = None							# obj

class _LoSockCall:
	funcName = None							# str
	funcArgs = None							# list<obj>

class _LoSockRetn:
	retVal = None							# obj, None means no return value

class _LoSockExcp:
	excObj = None							# str
	excInfo = None							# str

def _dbgmsg_moi_key(moi):
	return "%s, %s, %s"%(moi.peerName, moi.userName, moi.moduleName)

