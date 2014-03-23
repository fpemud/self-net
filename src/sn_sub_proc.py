#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import pickle
import struct
import traceback
import multiprocessing
from gi.repository import GLib

from sn_util import SnUtil
from sn_param import SnParam
from sn_module import SnRejectException

class LocalSockSendObj:
	dataObj = None							# obj

class LocalSockSetWorkState:
	workState = None						# enum

class LocalSockCall:
	funcName = None							# str
	funcArgs = None							# list<obj>

class LocalSockRetn:
	retVal = None							# obj, None means no return value

class LocalSockExcp:
	excObj = None							# str
	excInfo = None							# str

class SnSubProcBuilder:

	def startSubProc(self, peerName, userName, moduleName, tmpDir):
		parent_conn, child_conn = multiprocessing.Pipe()
		pargs = (peerName, userName, moduleName, tmpDir, child_conn)
		proc = multiprocessing.Process(target=_subproc_main, args=pargs)
		proc.start()
		return (proc, parent_conn)

def _subproc_main(peerName, userName, moduleName, tmpDir, pipeConn):

	print "********* debug2, %d"%(os.getpid())

	# drop priviledge
	if userName is not None:
		SnUtil.dropPriviledgeTo(userName)

	mainloop = GLib.MainLoop()
	_SubprocObject(mainloop, peerName, userName, moduleName, tmpDir, pipeConn)
	mainloop.run()

class _SubprocObject:

	def __init__(self, mainloop, peerName, userName, moduleName, tmpDir, pipeConn):
		self.mainloop = mainloop
		self.peerName = peerName
		self.userName = userName
		self.moduleName = moduleName
		self.tmpDir = tmpDir
		self.connSock = _SubProcObjSocket(pipeConn, self.onConnRecv, self.onConnError)
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

	def __init__(self, mySock, recvFunc, errorFunc):
		self.mySock = mySock
		self.recvFunc = recvFunc
		self.errorFunc = errorFunc
		self.recvBuffer = ""
		self.recvSourceId = GLib.io_add_watch(self.mySock, GLib.IO_IN | _flagError, self._onRecv)

	def send(self, dataObj):
		data = pickle.dumps(dataObj)
		header = struct.pack("!I", len(data))
		packet = header + data
		self.mySock.send_bytes(packet)

	def _onRecv(self, source, cb_condition):
		assert source == self.mySock

		if cb_condition & _flagError:
			self.errorFunc(self)
			assert self.mySock is None		# errorFunc should close the socket
			return False

		try:
			self.recvBuffer += self.mySock.recv_bytes()
		except EOFError:
			self.errorFunc(self)
			assert self.mySock is None		# errorFunc should close the socket
			return False

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
			if self.mySock is None:
				return False

def _typeCheck(obj, typeobj):
	return str(obj.__class__) == str(typeobj)

_flagError = GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP | GLib.IO_NVAL

