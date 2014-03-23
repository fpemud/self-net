#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import socket
import pickle
import struct
from OpenSSL import SSL
from gi.repository import GLib
from sn_util import SnUtil

class objsocket:

	SOCKTYPE_SSL = 0
	SOCKTYPE_MULTIPROCESSING_PIPE = 1

	_GC_STATE_NONE = 0
	_GC_STATE_PENDING = 1
	_GC_STATE_COMPLETE = 2

	def __init__(self, mySock, mySockType, recvFunc, errorFunc, gcCompleteFunc):
		assert mySockType in [ self.SOCKTYPE_SSL, self.SOCKTYPE_MULTIPROCESSING_PIPE ]

		self.mySock = mySock
		self.mySockType = mySockType
		self.gcState = self._GC_STATE_NONE
		self.recvFunc = recvFunc
		self.errorFunc = errorFunc
		self.gcCompleteFunc = gcCompleteFunc

		self.sendBuffer = ""
		self.recvBuffer = ""
		self.recvSourceId = GLib.io_add_watch(self.mySock, GLib.IO_IN | _flagError, self._onRecv)
		self.sendSourceId = None

	def send(self, dataObj):
		"""Never raise exception, errorFunc is called if the socket is broken"""

		assert self.mySock is not None and self.gcState == self._GC_STATE_NONE

		data = pickle.dumps(dataObj)
		header = struct.pack("!I", len(data))
		packet = header + data
		self.sendBuffer += packet

		if self.sendSourceId is None:
			self.sendSourceId = GLib.io_add_watch(self.mySock, GLib.IO_OUT, self._onSend)

	def gracefulClose(self):
		"""This function does not close the socket, the socket must be closed
		   by graceful close complete callback funtion"""

		assert self.mySock is not None and self.gcState == self._GC_STATE_NONE

		# no receiving in graceful closing
		if self.recvSourceId is not None:
			ret = GLib.source_remove(self.recvSourceId)
			assert ret
			self.recvSourceId = None

		# set state
		self.gcState = self._GC_STATE_PENDING
		if len(self.sendBuffer) == 0:
			SnUtil.idleInvoke(self._gcComplete)
		else:
			# assure socket is sending data
			assert self.sendSourceId is not None

	def close(self):
		assert self.mySock is not None

		if self.sendSourceId is not None:
			ret = GLib.source_remove(self.sendSourceId)
			assert ret
			self.sendSourceId = None

		if self.recvSourceId is not None:
			ret = GLib.source_remove(self.recvSourceId)
			assert ret
			self.recvSourceId = None

		self.mySock.close()
		self.mySock = None

	def _onSend(self, source, cb_condition):
		assert source == self.mySock

		# send data as much as possible
		try:
			if cb_condition & _flagError:
				raise _ObjSocketException(CbConditionException(cb_condition))
			if self.mySockType == self.SOCKTYPE_SSL:
				sendLen = self._doSendTypeSsl(self.mySock, self.sendBuffer)
			elif self.mySockType == self.SOCKTYPE_MULTIPROCESSING_PIPE:
				sendLen = self._doSendTypeMultiprocessingPipe(self.mySock, self.sendBuffer)
			else:
				assert False
			self.sendBuffer = self.sendBuffer[sendLen:]
		except _ObjSocketException as e:
			if self.gcState == self._GC_STATE_NONE:
				self.errorFunc(self, e)
				assert self.mySock is None		# errorFunc should close the socket
				return False
			elif self.gcState == self._GC_STATE_PENDING:
				self.sendBuffer = ""
				self._gcComplete()
				return False
			else:
				assert False

		# still has data to send
		if len(self.sendBuffer) > 0:
			return True

		# no data to send
		if self.gcState == self._GC_STATE_NONE:
			self.sendSourceId = None
			return False
		elif self.gcState == self._GC_STATE_PENDING:
			self._gcComplete()
			return False
		else:
			assert False

	def _onRecv(self, source, cb_condition):
		assert source == self.mySock
		assert self.gcState == self._GC_STATE_NONE

		try:
			if cb_condition & _flagError:
				raise _ObjSocketException(CbConditionException(cb_condition))
			if self.mySockType == self.SOCKTYPE_SSL:
				ret = self._doRecvTypeSsl(self.mySock)
			elif self.mySockType == self.SOCKTYPE_MULTIPROCESSING_PIPE:
				ret = self._doRecvTypeMultiprocessingPipe(self.mySock)
			else:
				assert False
			self.recvBuffer += ret
		except _ObjSocketException as e:
			self.errorFunc(self, e.excObj)
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
			if self.mySock is None or self.gcState != self._GC_STATE_NONE:
				return False

	@staticmethod
	def _doSendTypeSsl(mySock, sendBuffer):
		if len(sendBuffer) > 128:						# fixme
			sendLen = 128
		else:
			sendLen = len(sendBuffer)

		try:
			return mySock.send(sendBuffer[:sendLen])
		except (SSL.WantReadError, SSL.WantWriteError):
			return 0
		except (socket.error, SSL.Error) as e:
			raise _ObjSocketException(e.excObj)

	@staticmethod
	def _doRecvTypeSsl(mySock):
		try:
			recvBuf = mySock.recv(4096)
			if len(recvBuf) == 0:
				raise EOFError()
			return recvBuf
		except (SSL.WantReadError, SSL.WantWriteError):
			return ""
		except (socket.error, SSL.Error, EOFError) as e:
			raise _ObjSocketException(e)

	@staticmethod
	def _doSendTypeMultiprocessingPipe(mySock, sendBuffer):
		try:
			return mySock.send_bytes(sendBuffer)
		except ValueError as e:
			raise _ObjSocketException(e)

	@staticmethod
	def _doRecvTypeMultiprocessingPipe(mySock):
		try:
			return mySock.recv_bytes()
		except EOFError as e:
			raise _ObjSocketException(e)

	def _gcComplete(self):
		self.gcState = self._GC_STATE_COMPLETE
		self.gcCompleteFunc(self)
		assert self.mySock is None			# gcCompleteFunc should close the socket

class CbConditionException(Exception):
	def __init__(self, cb_condition):
		s = SnUtil.cbConditionToStr(cb_condition)
		super(CbConditionException, self).__init__(s)

class _ObjSocketException(Exception):
	def __init__(self, excObj):
		super(_ObjSocketException, self).__init__()
		self.excObj = excObj

_flagError = GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP | GLib.IO_NVAL

