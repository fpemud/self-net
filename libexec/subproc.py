#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import sys
from gi.repository import GLib

sys.path.append('/usr/lib/selfnetd')
sys.path.append('/usr/lib/selfnetd/modules')		# fixme
from sn_util import SnUtil
from sn_sub_proc import LocalSockSendObj
from sn_sub_proc import LocalSockSetWorkState
from sn_sub_proc import LocalSockRetn
from sn_sub_proc import LocalSockExcp

class _SubProcObject:

	def __init__(self, mainloop, peerName, userName, moduleName, tmpDir):
		self.mainloop = mainloop
		self.peerName = peerName
		self.userName = userName
		self.moduleName = moduleName
		self.tmpDir = tmpDir
		self.connSock = _SubProcObjSocket(self.onConnRecv, self.onConnError)
		self.mo = None

		# create module object
		exec("from %s import ModuleInstanceObject"%(self.moduleName.replace("-", "_")))
		self.mo = ModuleInstanceObject(self, self.peerName, self.userName, self.moduleName, self.tmpDir)

	def onConnRecv(self, sock, packetObj):
		assert sock == self.connSock
		assert _typeCheck(packetObj, LocalSockCall)

		if packetObj.funcName == "onActive":
			assert len(packetObj.funcArgs) == 0
			try:
				self.mo.onInit()
				self.mo.onActive()
				self._sendRetn(None)
			except Exception as e:
				self._sendExcp(e, traceback.format_exc())
				self.mainloop.quit()
		elif packetObj.funcName == "onRecv":
			assert len(packetObj.funcArgs) == 1
			try:
				self.mo.onRecv(packetObj.funcArgs[0])
				self._sendRetn(None)
			except SnRejectException as e:
				self._sendExcp(e, None)			# no traceback needed for reject exception
			except Exception as e:
				self._sendExcp(e, traceback.format_exc())
				self.mainloop.quit()
		elif packetObj.funcName == "onInactive":
			assert len(packetObj.funcArgs) == 0
			try:
				self.mo.onInactive()
				self._sendRetn(None)
				self.mainloop.quit()
			except Exception as e:
				self._sendExcp(e, traceback.format_exc())
				self.mainloop.quit()
		else:
			assert False

	def onConnError(self, sock):
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

class _SubProcObjSocket:

	def __init__(self, recvFunc, errorFunc):
		self.isClose = False
		self.recvFunc = recvFunc
		self.errorFunc = errorFunc
		self.recvBuffer = ""
		self.recvSourceId = GLib.io_add_watch(sys.stdin, GLib.IO_IN | _flagError, self._onRecv)

	def send(self, dataObj):
		assert not self.isClose

		data = pickle.dumps(dataObj)
		header = struct.pack("!I", len(data))
		packet = header + data
		self.stdout.write(packet)

	def close(self):
		assert not self.isClose
		self.isClose = True

	def _onRecv(self, source, cb_condition):
		assert not self.isClose

		if cb_condition & _flagError:
			self.errorFunc(self)
			assert self.isClose		# errorFunc should close the socket
			return False

		self.recvBuffer += self.stdin.read()
#		try:
#			self.recvBuffer += self.stdin.read()
#		except EOFError:
#			self.errorFunc(self)
#			assert self.isClose		# errorFunc should close the socket
#			return False

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

def _typeCheck(obj, typeobj):
	return str(obj.__class__) == str(typeobj)

_flagError = GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP | GLib.IO_NVAL

################################################################################

assert len(sys.argv) == 5
peerName = sys.argv[1]
userName = sys.argv[2]
moduleName = sys.argv[3]
tmpDir = sys.argv[4]

# drop priviledge
if userName is not None:
	SnUtil.dropPriviledgeTo(userName)

# do work
mainloop = GLib.MainLoop()
_SubProcObject(mainloop, peerName, userName, moduleName, tmpDir)
mainloop.run()

