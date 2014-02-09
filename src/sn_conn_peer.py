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
		self.flagError = GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP | GLib.IO_NVAL

		self.certFile = certFile
		self.privkeyFile = privkeyFile
		self.caCertFile = caCertFile
		self.acceptFunc = None

		self.serverSock = None
		self.serverSourceId = None
		self.sockDict = dict()			# sockets in handshaking

	def dispose(self):
		if self.serverSock is not None:
			self.stop()

	def setEventFunc(self, funcName, func):
		if funcName == "accept":
			assert self.acceptFunc is None and func is not None
			self.acceptFunc = func
		else:
			assert False

	def start(self, port):
		assert self.serverSock is None
	
		self.serverSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.serverSock.bind(('0.0.0.0', port))
		self.serverSock.listen(5)
		self.serverSock.setblocking(0)

		self.serverAcceptSourceId = GLib.io_add_watch(self.serverSock, GLib.IO_IN, self._onServerAccept)
		self.serverErrorSourceId = GLib.io_add_watch(self.serverSock, self.flagError, self._onServerError)

	def stop(self):
		assert self.serverSock is not None

		GLib.source_remove(self.serverErrorSourceId)
		GLib.source_remove(self.serverAcceptSourceId)
		self.serverSock.close()
		self.serverSock = None

	def _onServerAccept(self, source, cb_condition):
		logging.debug("SnPeerServer._onServerAccept: Start, %s", _cb_condition_to_str(cb_condition))

		assert source == self.serverSock

		try:
			new_sock, addr = self.serverSock.accept()
		except (socket.error) as e:
			logging.debug("SnPeerServer._onServerAccept: Failed, %s, %s", e.__class__, e)
			return True

		new_sock.setblocking(0)
		self._addSock(new_sock)

		logging.debug("SnPeerServer._onServerAccept: End")
		return True

	def _onServerError(self, source, cb_condition):
		assert False

	def _onRecv(self, source, cb_condition):
		logging.debug("SnPeerServer._onRecv: Start, %s", _cb_condition_to_str(cb_condition))

		info = self.sockDict[source]
		spname = source.getpeername()

		if info.state == _ServerConnInfo.HANDSHAKE_NONE:
			# wrap socket
			info.sslSock = ssl.wrap_socket(source, certfile=self.certFile, keyfile=self.privkeyFile,
										   cert_reqs=ssl.CERT_REQUIRED, ca_certs=self.caCertFile,
										   do_handshake_on_connect=False, ssl_version=ssl.PROTOCOL_SSLv3,
										   server_side=True)
			info.state = _ServerConnInfo.HANDSHAKE_WANT_WRITE
			assert info.sendSourceId is None
			info.sendSourceId = GLib.io_add_watch(source, GLib.IO_OUT, self._onSend)
			logging.debug("SnPeerServer._onRecv: Handshake NONE -> WANT_WRITE, %s", spname)
			return True
		elif info.state == _ServerConnInfo.HANDSHAKE_WANT_READ:
			# do handshake
			try:
				info.sslSock.do_handshake()
			except ssl.SSLError as e:
				if e.args[0] == ssl.SSL_ERROR_WANT_READ:
					info.state = _ServerConnInfo.HANDSHAKE_WANT_READ
					logging.debug("SnPeerServer._onRecv: Handshake WANT_READ -> WANT_READ, %s", spname)
					return True
				elif e.args[0] == ssl.SSL_ERROR_WANT_WRITE:
					info.state = _ServerConnInfo.HANDSHAKE_WANT_WRITE
					logging.debug("SnPeerServer._onRecv: Handshake WANT_READ -> WANT_WRITE, %s", spname)
					return True
				else:
					self._removeSock(source)
					source.close()
					logging.debug("SnPeerServer._onRecv: Handshake failed, %s, %s, %s", spname, e.__class__, e)
					return False			# sock closed, return false

			# hand shake complete
			info.state = _ServerConnInfo.HANDSHAKE_COMPLETE
			logging.debug("SnPeerServer._onRecv: Handshake WANT_READ -> COMPLETE, %s", spname)

			# do completion operation
			if not self._handshakeComplete(source):
				self._removeSock(source)
				source.close()
				logging.debug("SnPeerServer._onRecv: Handshake completion failed, %s", spname)
				return False				# sock closed, return false

			logging.debug("SnPeerServer._onRecv: End")
			return False					# process complete, return false
		else:
			assert False

	def _onSend(self, source, cb_condition):
		logging.debug("SnPeerServer._onSend: Start, %s", _cb_condition_to_str(cb_condition))

		info = self.sockDict[source]
		spname = source.getpeername()
		assert info.state == _ServerConnInfo.HANDSHAKE_WANT_WRITE

		# do handshake
		try:
			info.sslSock.do_handshake()
		except ssl.SSLError as e:
			if e.args[0] == ssl.SSL_ERROR_WANT_READ:
				info.state = _ServerConnInfo.HANDSHAKE_WANT_READ
				logging.debug("SnPeerServer._onSend: Handshake WANT_WRITE -> WANT_READ, %s", spname)
				info.sendSourceId = None
				return False				# no more write, return false
			elif e.args[0] == ssl.SSL_ERROR_WANT_WRITE:
				info.state = _ServerConnInfo.HANDSHAKE_WANT_WRITE
				logging.debug("SnPeerServer._onSend: Handshake WANT_WRITE -> WANT_WRITE, %s", spname)
				return True
			else:
				self._removeSock(source)
				source.close()
				logging.debug("SnPeerServer._onSend: Handshake failed, %s, %s, %s", spname, e.__class__, e)
				return False				# sock closed, return false

		# hand shake complete
		info.state = _ServerConnInfo.HANDSHAKE_COMPLETE
		logging.debug("SnPeerServer._onSend: Handshake WANT_READ -> COMPLETE, %s", spname)

		# do completion operation
		if not self._handshakeComplete(source):
			self._removeSock(source)
			source.close()
			logging.debug("SnPeerServer._onSend: Handshake completion failed, %s", spname)
			return False				# sock closed, return false

		logging.debug("SnPeerServer._onSend: End")
		return False						# process complete, return false

	def _onError(self, source, cb_condition):
		logging.debug("SnPeerServer._onError: Start, %s", _cb_condition_to_str(cb_condition))

		info = self.sockDict[source]
		spname = source.getpeername()
		self._removeSock(source)
		source.close()

		logging.debug("SnPeerServer._onError: End, %s", spname)
		return False						# sock closed, return false

	def _handshakeComplete(self, source):
		info = self.sockDict[source]

		# check peer name
		spname = source.getpeername()
		peerName = _getPeerName(info.sslSock)
		if peerName is None or peerName != spname[0]:
			logging.debug("SnPeerServer._handshakeComplete: Hostname incorrect, %s, %s", spname, peerName)
			return False

		# create SnPeerSocket
		self._removeSock(source)
		self.acceptFunc(SnPeerSocket(info.sslSock, peerName))
		return True

	def _addSock(self, sock):
		info = _ServerConnInfo()
		info.state = _ServerConnInfo.HANDSHAKE_NONE
		info.recvSourceId = GLib.io_add_watch(sock, GLib.IO_IN, self._onRecv)
		info.sendSourceId = None
		info.errorSourceId = GLib.io_add_watch(sock, self.flagError, self._onError)
		info.sslSock = None
		self.sockDict[sock] = info

	def _removeSock(self, sock):
		""" doesn't close socket """
		info = self.sockDict[sock]
		if info.errorSourceId is not None:
			GLib.source_remove(self.sockDict[sock].errorSourceId)
		if info.sendSourceId is not None:
			GLib.source_remove(self.sockDict[sock].sendSourceId)
		if info.recvSourceId is not None:
			GLib.source_remove(self.sockDict[sock].recvSourceId)
		del self.sockDict[sock]

class SnPeerClient:

	def __init__(self, certFile, privkeyFile, caCertFile):
		self.flagError = GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP | GLib.IO_NVAL

		self.certFile = certFile
		self.privkeyFile = privkeyFile
		self.caCertFile = caCertFile
		self.connectFunc = None

		self.sockDict = dict()			# sockets in handshaking

	def dispose(self):
		for sock in self.sockDict:
			sock.close()
		self.sockDict.clear()

	def setEventFunc(self, funcName, func):
		if funcName == "connected":
			assert self.connectFunc is None and func is not None
			self.connectFunc = func
		else:
			assert False

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

		self._addSock(sock, connectId, hostname, port)

		logging.debug("SnPeerClient.connect: End")
		return

	def _onRecv(self, source, cb_condition):
		logging.debug("SnPeerClient._onRecv: Start, %s", _cb_condition_to_str(cb_condition))

		info = self.sockDict[source]

		if info.state == _ClientConnInfo.HANDSHAKE_NONE:
			# wrap socket
			info.sslSock = ssl.wrap_socket(source, certfile=self.certFile, keyfile=self.privkeyFile,
										                    cert_reqs=ssl.CERT_REQUIRED, ca_certs=self.caCertFile,
										                    do_handshake_on_connect=False, ssl_version=ssl.PROTOCOL_SSLv3)
			info.state = _ClientConnInfo.HANDSHAKE_WANT_WRITE
			assert info.sendSourceId is None
			info.sendSourceId = GLib.io_add_watch(source, GLib.IO_OUT, self._onSend)
			logging.debug("SnPeerClient._onRecv: Handshake NONE -> WANT_WRITE, %s", self._info2str(info))
			return True
		elif info.state == _ClientConnInfo.HANDSHAKE_WANT_READ:
			# do handshake
			try:
				info.sslSock.do_handshake()
			except ssl.SSLError as e:
				if e.args[0] == ssl.SSL_ERROR_WANT_READ:
					info.state = _ClientConnInfo.HANDSHAKE_WANT_READ
					logging.debug("SnPeerClient._onRecv: Handshake WANT_READ -> WANT_READ, %s", self._info2str(info))
					return True
				elif e.args[0] == ssl.SSL_ERROR_WANT_WRITE:
					info.state = _ClientConnInfo.HANDSHAKE_WANT_WRITE
					logging.debug("SnPeerClient._onRecv: Handshake WANT_READ -> WANT_WRITE, %s", self._info2str(info))
					return True
				else:
					self._removeSock(source)
					source.close()
					logging.debug("SnPeerClient._onRecv: Handshake failed, %s, %s, %s", self._info2str(info), e.__class__, e)
					return False			# sock closed, return false

			# hand shake complete
			info.state = _ClientConnInfo.HANDSHAKE_COMPLETE
			logging.debug("SnPeerClient._onRecv: Handshake WANT_READ -> COMPLETE, %s", self._info2str(info))

			# do completion operation
			if not self._handshakeComplete(source):
				self._removeSock(source)
				source.close()
				logging.debug("SnPeerClient._onRecv: Handshake completion failed, %s", self._info2str(info))
				return False				# sock closed, return false

			logging.debug("SnPeerClient._onRecv: End")
			return False					# process complete, return false
		else:
			assert False

	def _onSend(self, source, cb_condition):
		logging.debug("SnPeerClient._onSend: Start, %s", _cb_condition_to_str(cb_condition))

		info = self.sockDict[source]
		assert info.state == _ClientConnInfo.HANDSHAKE_WANT_WRITE

		# do handshake
		try:
			info.sslSock.do_handshake()
		except ssl.SSLError as e:
			if e.args[0] == ssl.SSL_ERROR_WANT_READ:
				info.state = _ClientConnInfo.HANDSHAKE_WANT_READ
				logging.debug("SnPeerClient._onSend: Handshake WANT_WRITE -> WANT_READ, %s", self._info2str(info))
				info.sendSourceId = None
				return False				# no more write, return false
			elif e.args[0] == ssl.SSL_ERROR_WANT_WRITE:
				info.state = _ClientConnInfo.HANDSHAKE_WANT_WRITE
				logging.debug("SnPeerClient._onSend: Handshake WANT_WRITE -> WANT_WRITE, %s", self._info2str(info))
				return True
			else:
				self._removeSock(source)
				source.close()
				logging.debug("SnPeerClient._onSend: Handshake failed, %s, %s, %s", self._info2str(info), e.__class__, e)
				return False				# sock closed, return false

		# hand shake complete
		info.state = _ClientConnInfo.HANDSHAKE_COMPLETE
		logging.debug("SnPeerClient._onSend: Handshake WANT_READ -> COMPLETE, %s", self._info2str(info))

		# do completion operation
		if not self._handshakeComplete(source):
			self._removeSock(source)
			source.close()
			logging.debug("SnPeerClient._onSend: Handshake completion failed, %s", self._info2str(info))
			return False					# sock closed, return false

		logging.debug("SnPeerClient._onSend: End")
		return False						# process complete, return false

	def _onError(self, source, cb_condition):
		logging.debug("SnPeerClient._onError: Start, %s", _cb_condition_to_str(cb_condition))

		info = self.sockDict[source]
		self._removeSock(source)
		source.close()

		logging.debug("SnPeerClient._onError: End, %d, %s, %d", info.connectId, info.hostname, info.port)
		return False						# sock closed, return false

	def _handshakeComplete(self, source):
		info = self.sockDict[source]

		# check peer name
		spname = source.getpeername()
		peerName = _getPeerName(info.sslSock)
		if peerName is None or peerName != spname[0] or peerName != info.hostname:
			logging.debug("SnPeerClient._handshakeComplete: Hostname incorrect, %s, %s, %s", self._info2str(info), spname, peerName)
			return False

		# create SnPeerSocket
		self._removeSock(source)
		self.connectFunc(SnPeerSocket(info.sslSock, peerName))
		return True

	def _addSock(self, sock, connectId, hostname, port):
		info = _ClientConnInfo()
		info.connectId = connectId
		info.hostname = hostname
		info.port = port
		info.state = _ClientConnInfo.HANDSHAKE_NONE
		info.recvSourceId = GLib.io_add_watch(sock, GLib.IO_IN, self._onRecv)
		info.sendSourceId = None
		info.errorSourceId = GLib.io_add_watch(sock, self.flagError, self._onError)
		info.sslSock = None
		self.sockDict[sock] = info

	def _removeSock(self, sock):
		""" doesn't close socket """
		info = self.sockDict[sock]
		if info.errorSourceId is not None:
			GLib.source_remove(self.sockDict[sock].errorSourceId)
		if info.sendSourceId is not None:
			GLib.source_remove(self.sockDict[sock].sendSourceId)
		if info.recvSourceId is not None:
			GLib.source_remove(self.sockDict[sock].recvSourceId)
		del self.sockDict[sock]

	def _info2str(self, info):
		return "%d, %s, %d"%(info.connectId, info.hostname, info.port)

class SnPeerSocket:

	def __init__(self, sslSock, peerName):
		self.flagFull = GLib.IO_IN | GLib.IO_OUT | GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP | GLib.IO_NVAL
		self.flagError = GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP | GLib.IO_NVAL

		self.sslSock = sslSock
		self.peerName = peerName
		self.isClosing = False
		self.recvFunc = None
		self.errorFunc = None

		self.sendBuffer = ""
		self.recvBuffer = ""
		self.sendSourceId = GLib.io_add_watch(self.sslSock, GLib.IO_OUT, self._onSend)
		self.recvSourceId = None
		self.errorSourceId = None

	def setEventFunc(self, funcName, func):
		assert self.sslSock is not None and not self.isClosing
		assert func is not None

		if funcName == "recv":
			assert self.recvFunc is None
			self.recvFunc = func
			self.recvSourceId = GLib.io_add_watch(self.sslSock, GLib.IO_IN, self._onRecv)
		elif funcName == "error":
			assert self.errorFunc is None
			self.errorFunc = func
			self.errorSourceId = GLib.io_add_watch(self.sslSock, self.flagError, self._onError)
		else:
			assert False

	def getPeerName(self):
		assert self.sslSock is not None and not self.isClosing
		return self.peerName

	def send(self, dataObj):
		assert self.sslSock is not None and not self.isClosing

		data = pickle.dumps(dataObj)
		header = struct.pack("!I", len(data))
		packet = header + data
		self.sendBuffer += packet

	def gracefulClose(self):
		assert self.sslSock is not None and not self.isClosing
		self.isClosing = True

	def close(self):
		assert self.sslSock is not None and not self.isClosing
		self._doClose()

	def _onSend(self, source, cb_condition):
		assert source == self.sslSock
		
		# send data as much as possible
		sendLen = self.sslSock.send(self.sendBuffer)
		self.sendBuffer = self.sendBuffer[sendLen:]

		# closing, do close after all data is sent
		if self.isClosing and self.sendBuffer == "":
			self._doClose()

		return True

	def _onRecv(self, source, cb_condition):
		assert source == self.sslSock

		try:
			# receive packet header
			headerLen = struct.calcsize("!I")
			if len(self.recvBuffer) < headerLen:
				self.recvBuffer += self.sslSock.recv(headerLen - len(self.recvBuffer))

			# receive packet content
			dataLen = headerLen + struct.unpack("!I", self.recvBuffer)
			while len(self.recvBuffer) < dataLen:
				self.recvBuffer += self.sslSock.recv(dataLen - len(self.recvBuffer))
		except socket.error as e:
			if e.errno == errno.EAGAIN or e.errno == errno.EINPROGRESS:
				return True		# recvBuffer is not filled, need to receive again
			else:
				raise

		# closing, consume data, don't do real operation
		if self.isClosing:
			return True

		# invoke callback function
		dataObj = pickle.loads(self.recvBuffer)
		self.recvBuffer = ""
		self.recvFunc(self, dataObj)
		return True

	def _onError(self, source, cb_condition):
		assert source == self.sslSock
		self.errorFunc(self)
		return True

	def _doClose(self):
		if self.errorSourceId is not None:
			GLib.source_remove(self.errorSourceId)
		if self.recvSourceId is not None:
			GLib.source_remove(self.recvSourceId)
		if self.sendSourceId is not None:
			GLib.source_remove(self.sendSourceId)
		self.sslSock.close()
		self.sslSock = None

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


class _ServerConnInfo:
	HANDSHAKE_NONE = 0
	HANDSHAKE_WANT_READ = 1
	HANDSHAKE_WANT_WRITE = 2
	HANDSHAKE_COMPLETE = 3

	recvSourceId = None			# int
	sendSourceId = None			# int
	errSourceId = None			# int
	state = None				# enum
	sslSock = None				# obj

class _ClientConnInfo:
	HANDSHAKE_NONE = 0
	HANDSHAKE_WANT_READ = 1
	HANDSHAKE_WANT_WRITE = 2
	HANDSHAKE_COMPLETE = 3

	recvSourceId = None			# int
	sendSourceId = None			# int
	errSourceId = None			# int
	hostname = None				# str
	port = None					# int
	sourceId = None				# int
	state = None				# enum
	sslSock = None				# obj

