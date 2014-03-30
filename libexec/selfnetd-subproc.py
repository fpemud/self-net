#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import sys
import fcntl
import struct
import pickle
import logging
import traceback
from gi.repository import GLib

sys.path.append('/usr/lib/selfnetd')
sys.path.append('/usr/lib/selfnetd/modules')		# fixme
from sn_util import SnUtil
from sn_sub_proc import LocalSockSendObj
from sn_sub_proc import LocalSockSetWorkState
from sn_sub_proc import LocalSockCall
from sn_sub_proc import LocalSockRetn
from sn_sub_proc import LocalSockExcp

class _SubProcObject:

	def __init__(self, mainloop, peerName, userName, moduleName, tmpDir):
		logging.debug("_SubProcObject.init: Start")

		# variables
		self.mainloop = mainloop
		self.peerName = peerName
		self.userName = userName
		self.moduleName = moduleName
		self.tmpDir = tmpDir
		self.mo = None
		self.connSock = None

		# create module object
		exec("from %s import ModuleInstanceObject"%(self.moduleName.replace("-", "_")))
		self.mo = ModuleInstanceObject(self, self.peerName, self.userName, self.moduleName, self.tmpDir)

		# create connSock object
		fcntl.fcntl(sys.stdin, fcntl.F_SETFL, os.O_NONBLOCK)
		self.connSock = _SubProcObjSocket(self.onConnRecv)

		logging.debug("_SubProcObject.init: End")
		return

	def onConnRecv(self, sock, packetObj):
		assert sock == self.connSock
		assert _type_check(packetObj, LocalSockCall)

		if packetObj.funcName == "onActive":
			assert len(packetObj.funcArgs) == 0
			try:
				logging.debug("_SubProcObject.onActive: Start")
				self.mo.onInit()
				self.mo.onActive()
				logging.debug("_SubProcObject.onActive: End")
				self._sendRetn(None)
			except Exception as e:
				logging.debug("_SubProcObject.onActive: Except, %s", traceback.format_exc())
				self._sendExcp(e, traceback.format_exc())
		elif packetObj.funcName == "onRecv":
			assert len(packetObj.funcArgs) == 1
			try:
				logging.debug("_SubProcObject.onRecv: Start")
				self.mo.onRecv(packetObj.funcArgs[0])
				logging.debug("_SubProcObject.onRecv: End")
				self._sendRetn(None)
			except SnRejectException as e:
				logging.debug("_SubProcObject.onRecv: Reject")
				self._sendExcp(e, None)			# no traceback needed for reject exception
			except Exception as e:
				logging.debug("_SubProcObject.onRecv: Except, %s", traceback.format_exc())
				self._sendExcp(e, traceback.format_exc())
		elif packetObj.funcName == "onInactive":
			assert len(packetObj.funcArgs) == 0
			try:
				logging.debug("_SubProcObject.onInactive: Start")
				self.mo.onInactive()
				logging.debug("_SubProcObject.onInactive: End")
				self._sendRetn(None)
			except Exception as e:
				logging.debug("_SubProcObject.onInactive: Except, %s", traceback.format_exc())
				self._sendExcp(e, traceback.format_exc())
		else:
			assert False

	def _sendRetn(self, retVal):
		packetObj = LocalSockRetn()
		packetObj.retVal = retVal
		self.connSock.send(packetObj)

	def _sendExcp(self, excObj, excInfo):
		packetObj = LocalSockExcp()
		packetObj.excObj = excObj
		packetObj.excInfo = excInfo
		self.connSock.send(packetObj)

	def _sendObject(self, peerName, userName, moduleName, obj):
		packetObj = LocalSockSendObj()
		packetObj.dataObj = obj
		self.connSock.send(packetObj)

	def _setWorkState(self, peerName, userName, moduleName, workState):
		packetObj = LocalSockSetWorkState()
		packetObj.workState = workState
		self.connSock.send(packetObj)

	def _moduleLog(self, peerName, userName, moduleName, logLevel, msg, args):
		logging.log(logLevel, msg, args)

class _SubProcObjSocket:

	def __init__(self, recvFunc):
		self.isClose = False
		self.recvFunc = recvFunc
		self.recvBuffer = ""
		self.recvSourceId = GLib.io_add_watch(sys.stdin, GLib.IO_IN | _flagError, self._onRecv)

	def send(self, dataObj):
		assert not self.isClose

		data = pickle.dumps(dataObj)
		header = struct.pack("!I", len(data))
		packet = header + data
		sys.stdout.write(packet)
		sys.stdout.flush()
		logging.debug("****** debug, %d", len(packet))

	def close(self):
		assert not self.isClose
		self.isClose = True

	def _onRecv(self, source, cb_condition):
		try:
			assert not self.isClose

			if cb_condition & _flagError:
				logging.error("_SubProcObjSocket._onRecv, %s"%(SnUtil.cbConditionToStr(cb_condition)))
				return False

			self.recvBuffer += sys.stdin.read()
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
				dataObj = pickle.loads(self.recvBuffer[headerLen:totalLen])
				self.recvBuffer = self.recvBuffer[totalLen:]
				self.recvFunc(self, dataObj)
				if self.isClose:
					return False
		except Exception as e:
			logging.error(traceback.format_exc())

def _type_check(obj, typeobj):
	return str(obj.__class__) == str(typeobj)

_flagError = GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP | GLib.IO_NVAL

################################################################################

assert len(sys.argv) == 7
peerName = sys.argv[1]
userName = None if sys.argv[2] == "" else sys.argv[2]
moduleName = sys.argv[3]
tmpDir = sys.argv[4]
logLevel = sys.argv[5]
logFile = sys.argv[6]

logging.getLogger().addHandler(logging.FileHandler(logFile))
logging.getLogger().setLevel(SnUtil.getLoggingLevel(logLevel))

# drop priviledge
if userName is not None:
	SnUtil.dropPriviledgeTo(userName)

# do work
try:
	logging.info("selfnetd-subproc: Mainloop begins")

	mainloop = GLib.MainLoop()
	_SubProcObject(mainloop, peerName, userName, moduleName, tmpDir)
	mainloop.run()

	logging.info("selfnetd-subproc: Mainloop exits")
except Exception as e:
	logging.error(traceback.format_exc())

