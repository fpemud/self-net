#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import socket
import errno
import ssl
import time
import pickle
import struct
import threading
import logging
from Queue import Queue
from gi.repository import GLib

class SnPeerServer:

	def __init__(self, certFile, privkeyFile, caCertFile):
		self.certFile = certFile
		self.privkeyFile = privkeyFile
		self.caCertFile = caCertFile
		self.port = None
		self.ssl_sock = None
		self.acceptFunc = None

	def setEventFunc(self, funcName, func):
		if funcName == "accept":
			assert self.acceptFunc is None and func is not None
			self.acceptFunc = func
		else:
			assert False

	def start(self, port):
		assert self.port is None and self.ssl_sock is None

		self.port = port

		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.ssl_sock = ssl.wrap_socket(sock, certfile=self.certFile, keyfile=self.privkeyFile,
		                                cert_reqs=ssl.CERT_REQUIRED, ca_certs=self.caCertFile,
		                                ssl_version=ssl.PROTOCOL_SSLv3, server_side=True)
		self.ssl_sock.bind(('0.0.0.0', self.port))
		self.ssl_sock.listen(5)

		GLib.io_add_watch(self.ssl_sock, GLib.IO_IN, self._onAccept)

	def stop(self):
		assert self.port is not None and self.ssl_sock is not None

		self.ssl_sock.close()
		self.ssl_sock = None
		self.port = None

	def dispose(self):
		pass

	def _onAccept(self, source, cb_condition):
		assert source == self.ssl_sock

		try:
			new_sock, addr = self.ssl_sock.accept()
		except (socket.error, ssl.SSLError) as e:
			logging.debug("peer accept failed, %s, %s", e.__class__, e)
			return

		peerName = _Util.getPeerName(new_sock)
		if peerName is None:
			new_sock.close()
			return

		self.acceptFunc(SnPeerSocket(new_sock))

class SnPeerClient:

	def __init__(self, certFile, privkeyFile, caCertFile):
		self.flagFull = GLib.IO_IN | GLib.IO_OUT | GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP | GLib.IO_NVAL
		self.flagError = GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP | GLib.IO_NVAL

		self.certFile = certFile
		self.privkeyFile = privkeyFile
		self.caCertFile = caCertFile
		self.connectFunc = None
		self.sockDict = dict()

	def dispose(self):
		for ssl_sock in self.sockDict:
			ssl_sock.close()
		self.sockDict.clear()
		self.connectFunc = None

	def setEventFunc(self, funcName, func):
		if funcName == "connected":
			assert self.connectFunc is None and func is not None
			self.connectFunc = func
		else:
			assert False

	def connect(self, connectId, hostname, port):
		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		sock.setblocking(0)

		try:
			# ssl.SSLSocket.connect has bug when socket is non-blocking, so ssl.wrap_socket() must be after socket.connect()
			sock.connect((hostname, port))
		except socket.error as e:
			if e.errno == errno.EAGAIN or e.errno == errno.EINPROGRESS:
				pass
			else:
				logging.debug("peer connect failed, %d, %s, %d, %s, %s", connectId, hostname, port, e.__class__, e)
				sock.close()
				return

		info = _SockConnInfo()
		info.connectId = connectId
		info.hostname = hostname
		info.port = port
		info.state = _SockConnInfo.HANDSHAKE_NONE
		info.sourceId = GLib.io_add_watch(sock, self.flagFull, self._onEvent)
		info.ssl_sock = None
		self.sockDict[sock] = info

	def _onEvent(self, source, cb_condition):
		info = self.sockDict[source]
		ssl_sock = self.sockDict[source].ssl_sock

		# check error
		if (cb_condition & self.flagError) != 0:
			logging.debug("peer connect failed, %d, %s, %d, 0x%x", info.connectId, info.hostname, info.port, (cb_condition & self.flagError))
			self._removeSock(source)
			return

		# wrap socket
		if (cb_condition & GLib.IO_OUT) != 0 and info.state == _SockConnInfo.HANDSHAKE_NONE:
			self.sockDict[source].state = _SockConnInfo.HANDSHAKE_WANT_WRITE
			self.sockDict[source].ssl_sock = ssl.wrap_socket(source, certfile=self.certFile, keyfile=self.privkeyFile,
										                     cert_reqs=ssl.CERT_REQUIRED, ca_certs=self.caCertFile,
										                     do_handshake_on_connect=False, ssl_version=ssl.PROTOCOL_SSLv3)
			ssl_sock = self.sockDict[source].ssl_sock

		# do handshake
		if (((cb_condition & GLib.IO_OUT) != 0 and info.state == _SockConnInfo.HANDSHAKE_WANT_WRITE)
				or ((cb_condition & GLib.IO_IN) != 0 and info.state == _SockConnInfo.HANDSHAKE_WANT_READ)):
			try:
				ssl_sock.do_handshake()
				self.sockDict[source].state = _SockConnInfo.HANDSHAKE_COMPLETE
			except ssl.SSLError as e:
				if e.args[0] == ssl.SSL_ERROR_WANT_READ:
					self.sockDict[source].state = _SockConnInfo.HANDSHAKE_WANT_READ
					return
				elif e.args[0] == ssl.SSL_ERROR_WANT_WRITE:
					self.sockDict[source].state = _SockConnInfo.HANDSHAKE_WANT_WRITE
					return
				else:
					logging.debug("peer connect failed, %d, %s, %d, %s, %s", info.connectId, info.hostname, info.port, e.__class__, e)
					self._removeSock(source)
					return

		# check peer name
		peerName = _Util.getPeerName(source)
		if peerName is None or peerName != info.hostname:
			logging.debug("peer connect failed, %d, %s, %d, %s", info.connectId, info.hostname, info.port, "inconsistent peer name")
			self._removeSock(source)
			return

		# transfer to SnPeerSocket
		logging.debug("peer connect success, %d, %s, %d", info.connectId, info.hostname, info.port)
		GLib.source_remove(self.sockDict[source].sourceId)
		del self.sockDict[source]
		self.connectFunc(SnPeerSocket(ssl_sock))

	def _removeSock(self, source):
		GLib.source_remove(self.sockDict[source].sourceId)
		del self.sockDict[source]
		source.close()

class SnPeerSocket:

	def __init__(self, ssl_sock):
		self.flagFull = GLib.IO_IN | GLib.IO_OUT | GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP | GLib.IO_NVAL
		self.flagError = GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP | GLib.IO_NVAL

		self.ssl_sock = ssl_sock
		self.peerName = _Util.getPeerName(self.ssl_sock)
		self.isClosing = False
		self.recvFunc = None
		self.errorFunc = None

		self.sendBuffer = ""
		self.recvBuffer = ""
		self.sendSourceId = GLib.io_add_watch(self.ssl_sock, GLib.IO_OUT, self._onSend)
		self.recvSourceId = None
		self.errorSourceId = None

	def setEventFunc(self, funcName, func):
		assert self.ssl_sock is not None and not self.isClosing
		assert func is not None

		if funcName == "recv":
			assert self.recvFunc is None
			self.recvFunc = func
			self.recvSourceId = GLib.io_add_watch(self.ssl_sock, GLib.IO_IN, self._onRecv)
		elif funcName == "error":
			assert self.errorFunc is None
			self.errorFunc = func
			self.errorSourceId = GLib.io_add_watch(self.ssl_sock, self.flagError, self._onError)
		else:
			assert False

	def getPeerName(self):
		assert self.ssl_sock is not None and not self.isClosing
		return self.peerName

	def send(self, dataObj):
		assert self.ssl_sock is not None and not self.isClosing

		data = pickle.dumps(dataObj)
		header = struct.pack("!I", len(data))
		packet = header + data
		self.sendBuffer += packet

	def gracefulClose(self):
		assert self.ssl_sock is not None and not self.isClosing
		self.isClosing = True

	def close(self):
		assert self.ssl_sock is not None and not self.isClosing
		self._doClose()

	def _onSend(self, source, cb_condition):
		assert source == self.ssl_sock
		
		# send data as much as possible
		sendLen = self.ssl_sock.send(self.sendBuffer)
		self.sendBuffer = self.sendBuffer[sendLen:]

		# closing, do close after all data is sent
		if self.isClosing and self.sendBuffer == "":
			self._doClose()

	def _onRecv(self, source, cb_condition):
		assert source == self.ssl_sock

		try:
			# receive packet header
			headerLen = struct.calcsize("!I")
			if len(self.recvBuffer) < headerLen:
				self.recvBuffer += self.ssl_sock.recv(headerLen - len(self.recvBuffer))

			# receive packet content
			dataLen = headerLen + struct.unpack("!I", self.recvBuffer)
			while len(self.recvBuffer) < dataLen:
				self.recvBuffer += self.ssl_sock.recv(dataLen - len(self.recvBuffer))
		except socket.error as e:
			if e.errno == errno.EAGAIN or e.errno == errno.EINPROGRESS:
				return		# recvBuffer is not filled, need to receive again
			else:
				raise

		# closing, consume data, don't do real operation
		if self.isClosing:
			return

		# invoke callback function
		dataObj = pickle.loads(self.recvBuffer)
		self.recvBuffer = ""
		self.recvFunc(self, dataObj)

	def _onError(self, source, cb_condition):
		assert source == self.ssl_sock

		# invoke callback function
		self.errorFunc(self)

	def _doClose(self):
		if self.errorSourceId is not None:
			GLib.source_remove(self.errorSourceId)
		if self.recvSourceId is not None:
			GLib.source_remove(self.recvSourceId)
		if self.sendSourceId is not None:
			GLib.source_remove(self.sendSourceId)
		self.ssl_sock.close()
		self.ssl_sock = None

class _Util:

	@staticmethod
	def getPeerName(ssl_sock):
		cert = ssl_sock.getpeercert()
		if cert is not None and "subject" in cert:
			for item in cert["subject"]:
				if item[0][0] == "commonName":
					return item[0][1]
		return None

class _SockConnInfo:
	HANDSHAKE_NONE = 0
	HANDSHAKE_WANT_READ = 1
	HANDSHAKE_WANT_WRITE = 2
	HANDSHAKE_COMPLETE = 3

	connectId = None			# int
	hostname = None				# str
	port = None					# int
	sourceId = None				# int
	state = None				# enum
	ssl_sock = None				# obj

