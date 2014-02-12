#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import socket
import errno
import ssl
import pickle
import struct
import logging
from gi.repository import GLib

class SnPeerServer:

	def __init__(self, handshaker):
		self.handshaker = handshaker
		self.serverSock = None
		self.serverSourceId = None

	def dispose(self):
		if self.serverSock is not None:
			self.stop()

	def start(self, port):
		assert self.serverSock is None
	
		self.serverSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.serverSock.bind(('0.0.0.0', port))
		self.serverSock.listen(5)
		self.serverSock.setblocking(0)
		self.serverSourceId = GLib.io_add_watch(self.serverSock, GLib.IO_IN | _flagError, self._onServerAccept)

	def stop(self):
		assert self.serverSock is not None

		ret = GLib.source_remove(self.serverSourceId)
		assert ret

		self.serverSock.close()
		self.serverSock = None

	def _onServerAccept(self, source, cb_condition):
		logging.debug("SnPeerServer._onServerAccept: Start, %s", _cb_condition_to_str(cb_condition))

		assert not (cb_condition & _flagError)
		assert source == self.serverSock

		try:
			new_sock, addr = self.serverSock.accept()
			self.handshaker.addSocket(new_sock, True)

			logging.debug("SnPeerServer._onServerAccept: End")
			return True
		except socket.error as e:
			logging.debug("SnPeerServer._onServerAccept: Failed, %s, %s", e.__class__, e)
			return True

class SnPeerClient:

	def __init__(self, handshaker):
		self.handshaker = handshaker

	def dispose(self):
		pass

	def connect(self, connectId, hostname, port):
		logging.debug("SnPeerClient.connect: Start, %d, %s, %d", connectId, hostname, port)

		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		sock.setblocking(0)

		try:
			# ssl.SSLSocket.connect has bug when socket is non-blocking,
			# so ssl.wrap_socket() must be called after socket is connected
			sock.connect((hostname, port))
		except socket.error as e:
			if e.errno == errno.EAGAIN or e.errno == errno.EINPROGRESS:
				pass
			else:
				logging.debug("SnPeerClient.connect: Failed, %s, %s", e.__class__, e)
				sock.close()
				return

		self.handshaker.addSocket(sock, False, connectId, hostname, port)

		logging.debug("SnPeerClient.connect: End")
		return

class SnPeerHandShaker:

	HANDSHAKE_NONE = 0
	HANDSHAKE_WANT_READ = 1
	HANDSHAKE_WANT_WRITE = 2
	HANDSHAKE_COMPLETE = 3

	def __init__(self, certFile, privkeyFile, caCertFile, connectFunc):
		self.certFile = certFile
		self.privkeyFile = privkeyFile
		self.caCertFile = caCertFile
		self.connectFunc = connectFunc
		self.sockDict = dict()

	def dispose(self):
		pass

	def addSocket(self, sock, serverSide, connectId=None, hostname=None, port=None):
		logging.debug("SnPeerHandShaker.addSocket: Start")

		info = _HandShakerConnInfo()
		info.serverSide = serverSide
		info.state = SnPeerHandShaker.HANDSHAKE_NONE
		info.sslSock = None
		info.connectId = connectId
		info.hostname = hostname
		info.port = port
		info.spname = None					# value of socket.getpeername()
		self.sockDict[sock] = info

		sock.setblocking(0)
		GLib.io_add_watch(sock, GLib.IO_IN | GLib.IO_OUT | _flagError, self._onEvent)

		logging.debug("SnPeerHandShaker.addSocket: End")
		return

	def _onEvent(self, source, cb_condition):
		logging.debug("SnPeerHandShaker._onEvent: Start, %s", _cb_condition_to_str(cb_condition))

		info = self.sockDict[source]
		oldState = info.state

		try:
			# check error
			if cb_condition & _flagError:
				raise _ConnException("Socket error")

			# HANDSHAKE_NONE
			if info.state == SnPeerHandShaker.HANDSHAKE_NONE:
				info.spname = source.getpeername()
				info.sslSock = ssl.wrap_socket(source, certfile=self.certFile, keyfile=self.privkeyFile,
											   cert_reqs=ssl.CERT_REQUIRED, ca_certs=self.caCertFile,
											   do_handshake_on_connect=False, ssl_version=ssl.PROTOCOL_SSLv3,
											   server_side=info.serverSide)
				info.state = SnPeerHandShaker.HANDSHAKE_WANT_WRITE

			# HANDSHAKE_WANT_READ & HANDSHAKE_WANT_WRITE
			if ((info.state == SnPeerHandShaker.HANDSHAKE_WANT_READ and cb_condition & GLib.IO_IN) or
					(info.state == SnPeerHandShaker.HANDSHAKE_WANT_WRITE and cb_condition & GLib.IO_OUT)):
				try:
					info.sslSock.do_handshake()
					info.state = SnPeerHandShaker.HANDSHAKE_COMPLETE
				except ssl.SSLError as e:
					if e.args[0] == ssl.SSL_ERROR_WANT_READ:
						info.state = SnPeerHandShaker.HANDSHAKE_WANT_READ
					elif e.args[0] == ssl.SSL_ERROR_WANT_WRITE:
						info.state = SnPeerHandShaker.HANDSHAKE_WANT_WRITE
					else:
						raise _ConnException("Handshake failed, %s"%(_handshake_info_to_str(info)), e)

			# HANDSHAKE_COMPLETE
			if info.state == SnPeerHandShaker.HANDSHAKE_COMPLETE:
				# check peer name
				peerName = _getPeerName(info.sslSock)
				if info.serverSide:
					if peerName is None:
						raise _ConnException("Hostname incorrect, %s, %s"%(_handshake_info_to_str(info), peerName))
				else:
					if peerName is None or peerName != info.hostname:
						raise _ConnException("Hostname incorrect, %s, %s"%(_handshake_info_to_str(info), peerName))

				# completion log
				logging.debug("SnPeerHandShaker._onEvent: %s -> %s", _handshake_state_to_str(oldState),
						_handshake_state_to_str(info.state))

				# create SnPeerSocket
				del self.sockDict[source]
				self.connectFunc(info.sslSock)

				logging.debug("SnPeerHandShaker._onEvent: End")
				return False

		except _ConnException as e:
			del self.sockDict[source]
			source.close()
			if not e.hasExcObj:
				logging.debug("SnPeerHandShaker._onEvent: %s, %s", e.message, _handshake_info_to_str(info))
			else:
				logging.debug("SnPeerHandShaker._onEvent: %s, %s, %s, %s", e.message, _handshake_info_to_str(info),
						e.excName, e.excMessage)
			return False

		# register io watch callback again
		if info.state == SnPeerHandShaker.HANDSHAKE_WANT_READ:
			GLib.io_add_watch(source, GLib.IO_IN | _flagError, self._onEvent)
		elif info.state == SnPeerHandShaker.HANDSHAKE_WANT_WRITE:
			GLib.io_add_watch(source, GLib.IO_OUT | _flagError, self._onEvent)
		else:
			assert False

		logging.debug("SnPeerHandShaker._onEvent: End, %s -> %s", _handshake_state_to_str(oldState),
				_handshake_state_to_str(info.state))
		return False

class SnPeerSocket:

	_GC_STATE_NONE = 0
	_GC_STATE_PENDING = 1
	_GC_STATE_COMPLETE = 2

	def __init__(self, sslSock):
		self.sslSock = sslSock

		self.peerName = _getPeerName(self.sslSock)
		assert self.peerName is not None

		self.gcState = self._GC_STATE_NONE
		self.recvFunc = None
		self.errorFunc = None
		self.gcCompleteFunc = None

		self.sendBuffer = ""
		self.recvBuffer = ""
		self.recvSourceId = None
		self.sendSourceId = None

	def setEventFunc(self, funcName, func):
		assert self._checkValid()
		assert func is not None

		if funcName == "recv":
			assert self.recvFunc is None
			self.recvFunc = func
			if self.recvSourceId is None:
				self.recvSourceId = GLib.io_add_watch(self.sslSock, GLib.IO_IN | _flagError, self._onRecv)
		elif funcName == "error":
			assert self.errorFunc is None
			self.errorFunc = func
			if self.recvSourceId is None:
				self.recvSourceId = GLib.io_add_watch(self.sslSock, GLib.IO_IN | _flagError, self._onRecv)
		elif funcName == "gracefulCloseComplete":
			assert self.gcCompleteFunc is None
			self.gcCompleteFunc = func
		else:
			assert False

	def getPeerName(self):
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
		assert self.gcCompleteFunc is not None

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

		logging.debug("SnPeerSocket._onSend: Start, %s, %s", self.peerName, _cb_condition_to_str(cb_condition))

		# check error
		if cb_condition & _flagError:
			if self.gcState == self._GC_STATE_NONE:
				logging.debug("SnPeerSocket._onSend: Socket error")
				self.sendBuffer = ""
				self.sendSourceId = None
			elif self.gcState == self._GC_STATE_PENDING:
				logging.debug("SnPeerSocket._onSend: Socket error, graceful close complete")
				self.sendBuffer = ""
				self.gcState = self._GC_STATE_COMPLETE
				self.gcCompleteFunc(self)
				assert self.sslSock is None		# gcCompleteFunc should close the socket
			else:
				assert False
			return False
		
		# send data as much as possible
		sendLen = self.sslSock.send(self.sendBuffer)
		self.sendBuffer = self.sendBuffer[sendLen:]

		# still has data to send
		if self.sendBuffer != "":
			self.sendSourceId = GLib.io_add_watch(self.sslSock, GLib.IO_OUT, self._onSend)
			logging.debug("SnPeerSocket._onSend: Data remains")
			return False

		# no data to send
		if self.gcState == self._GC_STATE_NONE:
			logging.debug("SnPeerSocket._onSend: No data remains")
			self.sendSourceId = None
		elif self.gcState == self._GC_STATE_PENDING:
			logging.debug("SnPeerSocket._onSend: No data remains, graceful close complete")
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

		logging.debug("SnPeerSocket._onRecv: Start, %s, %s", self.peerName, _cb_condition_to_str(cb_condition))

		if cb_condition & _flagError:
			# do error processing
			if self.errorFunc is not None:
				self.errorFunc(self)
				ret = self._getRetBySource(self.recvSourceId)
				logging.debug("SnPeerSocket._onRecv: Socket error")
				return ret
			return True
		elif self.recvFunc is not None:
			# receive packet header
			headerLen = struct.calcsize("!I")
			while len(self.recvBuffer) < headerLen:
				ret = self.sslSock.recv(headerLen - len(self.recvBuffer))
				if ret == "":
					logging.debug("SnPeerSocket._onRecv: More data needed")
					return True
				self.recvBuffer += ret

			# receive packet data
			dataLen = headerLen + struct.unpack("!I", self.recvBuffer[:headerLen])[0]
			while len(self.recvBuffer) < dataLen:
				ret = self.sslSock.recv(dataLen - len(self.recvBuffer))
				if ret == "":
					logging.debug("SnPeerSocket._onRecv: More data needed")
					return True
				self.recvBuffer += ret

			# invoke callback function
			dataObj = pickle.loads(self.recvBuffer[headerLen:])
			self.recvBuffer = ""
			self.recvFunc(self, dataObj)
			ret = self._getRetBySource(self.recvSourceId)

			logging.debug("SnPeerSocket._onRecv: Data received")
			return ret
		else:
			assert False

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

class _ConnException(Exception):
	def __init__(self, message, excObj=None):
		super(_ConnException, self).__init__(message)

		self.hasExcObj = False
		if excObj is not None:
			self.hasExcObj = True
			self.excName = excObj.__class__
			self.excMessage = excObj.message

class _HandShakerConnInfo:
	serverSide = None			# bool
	state = None				# enum
	sslSock = None				# obj
	connectId = None			# int
	hostname = None				# str
	port = None					# int
	spname = None				# str

def _getPeerName(sslSock):
	cert = sslSock.getpeercert()
	if cert is not None and "subject" in cert:
		for item in cert["subject"]:
			if item[0][0] == "commonName":
				return item[0][1]
	return None

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

def _handshake_state_to_str(handshake_state):
	if handshake_state == SnPeerHandShaker.HANDSHAKE_NONE:
		return "NONE"
	elif handshake_state == SnPeerHandShaker.HANDSHAKE_WANT_READ:
		return "WANT_READ"
	elif handshake_state == SnPeerHandShaker.HANDSHAKE_WANT_WRITE:
		return "WANT_WRITE"
	elif handshake_state == SnPeerHandShaker.HANDSHAKE_COMPLETE:
		return "COMPLETE"
	else:
		assert False

def _handshake_info_to_str(info):
	if info.serverSide:
		return info.spname
	else:
		return "%d, %s, %d"%(info.connectId, info.hostname, info.port)

_flagError = GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP | GLib.IO_NVAL

