#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import socket
import errno
import ssl
import pickle
import struct
import logging
from gi.repository import GLib
from sn_util import SnUtil

class SnPeerSocket:

	_GC_STATE_NONE = 0
	_GC_STATE_PENDING = 1
	_GC_STATE_COMPLETE = 2

	def __init__(self, sslSock, recvFunc, errorFunc, gcCompleteFunc):
		self.sslSock = sslSock

		self.peerName = SnUtil.getSslSocketPeerName(self.sslSock)
		assert self.peerName is not None

		self.gcState = self._GC_STATE_NONE
		self.recvFunc = recvFunc
		self.errorFunc = errorFunc
		self.gcCompleteFunc = gcCompleteFunc

		self.sendBuffer = ""
		self.recvBuffer = ""
		self.recvSourceId = GLib.io_add_watch(self.sslSock, GLib.IO_IN | _flagError, self._onRecv)
		self.sendSourceId = None

	def getPeerName(self):
		# should be removed from this class

		assert self._checkValid()
		return self.peerName

	def send(self, dataObj):
		assert self._checkValid()

		data = pickle.dumps(dataObj)
		header = struct.pack("!I", len(data))
		packet = header + data
		self.sendBuffer += packet

		if self.sendSourceId is None:
			self.sendSourceId = GLib.io_add_watch(self.sslSock, GLib.IO_OUT, self._onSend)

	def gracefulClose(self):
		"""This function does not close the socket, the socket must be closed
		   by graceful close complete callback funtion"""

		assert self._checkValid()

		# no receiving in graceful closing
		if self.recvSourceId is not None:
			ret = GLib.source_remove(self.recvSourceId)
			assert ret
			self.recvSourceId = None

		# set state
		self.gcState = self._GC_STATE_PENDING
		if self.sendBuffer == "":
			# for consistency sake, gcCompleteFunc should be called in event
			# context, so we use idle callback here
			GLib.idle_add(self._gcCompleteIdleFunc)
		else:
			# assure socket is sending data
			assert self.sendSourceId is not None

	def close(self):
		assert self.sslSock is not None

		if self.sendSourceId is not None:
			ret = GLib.source_remove(self.sendSourceId)
			assert ret
			self.sendSourceId = None

		if self.recvSourceId is not None:
			ret = GLib.source_remove(self.recvSourceId)
			assert ret
			self.recvSourceId = None

		self.sslSock.close()
		self.sslSock = None

	def _onSend(self, source, cb_condition):
		assert source == self.sslSock

		# send data as much as possible
		try:
			if cb_condition & _flagError:
				raise _CbConditionException(cb_condition)
			sendLen = self.sslSock.send(self.sendBuffer)
			self.sendBuffer = self.sendBuffer[sendLen:]
		except (socket.error, ssl.SSLError, _CbConditionException) as e:
			if self.gcState == self._GC_STATE_NONE:
				self.errorFunc(self)
				return False
			elif self.gcState == self._GC_STATE_PENDING:
				self.sendBuffer = ""
				self.gcState = self._GC_STATE_COMPLETE
				self.gcCompleteFunc(self)
				assert self.sslSock is None		# gcCompleteFunc should close the socket
			else:
				assert False
			return False

		# still has data to send
		if self.sendBuffer != "":
			self.sendSourceId = GLib.io_add_watch(self.sslSock, GLib.IO_OUT, self._onSend)
			return False

		# no data to send
		if self.gcState == self._GC_STATE_NONE:
			self.sendSourceId = None
		elif self.gcState == self._GC_STATE_PENDING:
			self.gcState = self._GC_STATE_COMPLETE
			self.gcCompleteFunc(self)
			assert self.sslSock is None			# gcCompleteFunc should close the socket
		else:
			assert False
		return False

	def _onRecv(self, source, cb_condition):
		# fixme: weird, It seems that GLib.source_remove has no effect
		if source != self.sslSock:
			return False
		#assert source == self.sslSock
		assert self.gcState == self._GC_STATE_NONE

		try:
			if cb_condition & _flagError:
				raise _CbConditionException(cb_condition)
			self.recvBuffer += self.sslSock.recv(4096)
		except (socket.error, ssl.SSLError, _CbConditionException) as e:
			if isinstance(e, ssl.SSLError) and e.args[0] == ssl.SSL_ERROR_WANT_READ:
				return True
			self.errorFunc(self)
			ret = self._getRetBySource(self.recvSourceId)
			return ret

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
			if not self._getRetBySource(self.recvSourceId):
				return False

	def _gcCompleteIdleFunc(self):
		self.gcState = self._GC_STATE_COMPLETE
		self.gcCompleteFunc(self)
		assert self.sslSock is None			# gcCompleteFunc should close the socket
		return False

	def _checkValid(self):
		return self.sslSock is not None and self.gcState == self._GC_STATE_NONE

	def _getRetBySource(self, sourceId):
		# I find removing the source handler in callback function has no effect.
		# It is still depended on the return value.
		# I can't understand this design.
		# I write a function here to get the return value by the availability of source handler.

		if sourceId is not None:
			return True
		else:
			return False

class _CbConditionException(Exception):
	def __init__(self, cb_condition):
		s = _cb_condition_to_str(cb_condition)
		super(_CbConditionException, self).__init__(s)

def _cb_condition_to_str(cb_condition):
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

_flagError = GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP | GLib.IO_NVAL

