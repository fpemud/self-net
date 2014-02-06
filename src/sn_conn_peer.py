#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import ssl
import time
import socket
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
		new_sock, addr = self.ssl_sock.accept()
	
		peerName = _Util.getPeerName(new_sock)
		if peerName is None:
			new_sock.close()
			return

		self.acceptFunc(SnPeerSocket(new_sock))

class SnPeerClient:

	def __init__(self, certFile, privkeyFile, caCertFile):
		self.certFile = certFile
		self.privkeyFile = privkeyFile
		self.caCertFile = caCertFile
		self.connectFunc = None
		self.threadList = []

	def dispose(self):
		while len(self.threadList) > 0:
			time.sleep(0.05)

	def setEventFunc(self, funcName, func):
		if funcName == "connected":
			assert self.connectFunc is None and func is not None
			self.connectFunc = func
		else:
			assert False

	def connect(self, connectId, hostname, port):
		t = _ConnThread(self, connectId, hostname, port)
		self.threadList.append(t)			# removes in _ConnThread when error occurs
		t.start()

	def _onIdle(self, t, ssl_sock):
		self.connectFunc(SnPeerSocket(ssl_sock))
		self.threadList.remove(t)
		return False

class SnPeerSocket:

	def __init__(self, ssl_sock):
		self.ssl_sock = ssl_sock

		self.peerName = _Util.getPeerName(self.ssl_sock)
		assert self.peerName is not None

		self.packetQueue = Queue()
		self.sendThread = _SendThread(self)
		self.isClosing = False

		self.recvFunc = None
		self.errorFunc = None

	def setEventFunc(self, funcName, func):
		assert self.ssl_sock is not None and not self.isClosing
		assert func is not None

		if funcName == "recv":
			assert self.recvFunc is None
			self.recvFunc = func
			GLib.io_add_watch(self.ssl_sock, GLib.IO_IN, self._onRecv)
		elif funcName == "error":
			assert self.errorFunc is None
			self.errorFunc = func
			GLib.io_add_watch(self.ssl_sock, GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP, self._onError)
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
		self.packetQueue.put(packet, True)

	def gracefulClose(self):
		assert self.ssl_sock is not None and not self.isClosing

		self.isClosing = True
		self.sendThread.stop(False)

	def close(self):
		assert self.ssl_sock is not None and not self.isClosing

		self.isClosing = True
		self.sendThread.stop(True)

	def _onRecv(self):
		# receive packet header
		headerLen = struct.calcsize("!I")
		header = ""
		while len(header) < headerLen:
			header += self.ssl_sock.recv(headerLen - len(header))

		# receive packet content
		dataLen = struct.unpack("!I", header)
		data = ""
		while len(data) < dataLen:
			data += self.ssl_sock.recv(dataLen - len(data))

		# closing, consume data, don't do real operation
		if self.isClosing:
			return

		# invoke callback function
		dataObj = pickle.loads(data)
		self.recvFunc(self, dataObj)

	def _onError(self):
		# invoke callback function
		self.errorFunc(self)

	def _onClose(self):
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

class _ConnThread(threading.Thread):

	def __init__(self, parent, connectId, hostname, port):
		super(_ConnThread, self).__init__()
		self.parent = parent
		self.connectId = connectId		# for logging
		self.hostname = hostname
		self.port = port

	def run(self):
		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  
		ssl_sock = ssl.wrap_socket(sock, certfile=self.parent.certFile, keyfile=self.parent.privkeyFile,
				                   cert_reqs=ssl.CERT_REQUIRED, ca_certs=self.parent.caCertFile,
				                   ssl_version=ssl.PROTOCOL_SSLv3)

		try:
			ssl_sock.connect((self.hostname, self.port))
		except (socket.error, ssl.SSLError) as e:
			logging.debug("connect to peer failed, %d, %s, %d, %s, %s", self.connectId, self.hostname, self.port, e.__class__, e)
			ssl_sock.close()
			self.parent.threadList.remove(self)
			return

		peerName = _Util.getPeerName(ssl_sock)
		if peerName is None or peerName != self.hostname:
			ssl_sock.close()
			self.parent.threadList.remove(self)
			return

		GLib.idle_add(self.parent._onIdle, self, ssl_sock)

class _SendThread(threading.Thread):

	def __init__(self, parent):
		super(_SendThread, self).__init__()
		self.parent = parent
		self.stopFlag = False
		self.stopImmediateFlag = False

	def stop(self, immediate):
		"""may bring 50ms delay"""
		self.stopFlag = True
		self.stopImmediateFlag = immediate
		self.parent.packetQueue.put(None)		# feed PriorityQueue.get()

	def run(self):
		try:
			while not self.stopFlag:
				packet = self.parent.packetQueue.get(True)
				if packet is None:
					continue
				sendLen = 0
				while not self.stopImmediateFlag:
					sendLen += self.parent.ssl_sock.send(packet[sendLen:])
					if sendLen >= len(packet):
						break
					time.sleep(0.05)
		finally:
			self.parent._onClose()

