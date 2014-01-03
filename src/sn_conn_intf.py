#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import socket
import ssl
import struct
import threading
from Queue import PriorityQueue
from gi.repository import GLib

class ServerEndPoint:

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

	def listen(self, port):
		self.port = port

		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.ssl_sock = ssl.wrap_socket(sock, certfile=self.certFile, keyfile=self.privkeyFile,
		                                cert_reqs=ssl.CERT_REQUIRED, ca_certs=self.caCertFile,
		                                ssl_version=ssl.PROTOCOL_SSLv3, server_side=True)
		self.ssl_sock.bind(('0.0.0.0', self.port))
		self.ssl_sock.listen(5)

		GLib.io_add_watch(self.ssl_sock, GLib.IO_IN, self._onAccept)

	def close(self):
		self.ssl_sock.close()
		self.ssl_sock = None

	def _onAccept(self, source, cb_condition):
		new_sock, addr = self.ssl_sock.accept()
	
		peerName = Socket._getPeerName(new_sock)
		if peerName is None:
			new_sock.close()
			return

		self.acceptFunc(Socket(new_sock))

class ClientEndPoint:

	def __init__(self, certFile, privkeyFile, caCertFile):
		self.certFile = certFile
		self.privkeyFile = privkeyFile
		self.caCertFile = caCertFile
		self.connectFunc = None

	def setEventFunc(self, funcName, func):
		if funcName == "connected":
			assert self.connectFunc is None and func is not None
			self.connectFunc = func
		else:
			assert False

	def connect(self, hostname, port):
		# run the thread
		t = _ClientEndPointConnThread(hostname, port)
		t.start()

	def _onIdle(self, ssl_sock):
		self.connectFunc(Socket(ssl_sock))
		return False

class Socket:

	def __init__(self, ssl_sock):
		self.ssl_sock = ssl_sock

		self.peerName = Socket._getPeerName(self.ssl_sock)
		assert self.peerName is not None

		self.packetQueue = PriorityQueue()
		self.sendThread = _SocketSendThread(self)

		self.labelRecvFuncDict = dict()
		self.recvFunc = None
		self.errorFunc = None

	def setEventFunc(self, funcName, *args):
		if funcName == "label_recv":
			assert len(args) == 2 or len(args) == 3
			label = int(args[0])
			func = args[1]
			keepPacket = False
			if len(args) == 3:
				keepPacket = bool(args[2])
			assert label not in self.labelRecvFuncDict and func is not None
			self.labelRecvFuncDict[label] = _SocketRecvFuncInfo(func, keepPacket)
			GLib.io_add_watch(self.ssl_sock, GLib.IO_IN, self._onRecv)
		elif funcName == "recv":
			assert len(args) == 1 or len(args) == 2
			func = args[0]
			keepPacket = False
			if len(args) == 2:
				keepPacket = bool(args[1])
			assert self.recvFunc is None and func is not None
			self.recvFunc = _SocketRecvFuncInfo(func, keepPacket)
			GLib.io_add_watch(self.ssl_sock, GLib.IO_IN, self._onRecv)
		elif funcName == "error":
			assert len(args) == 1
			func = args[0]
			assert self.errorFunc is None and func is not None
			self.errorFunc = func
			GLib.io_add_watch(self.ssl_sock, GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP, self._onError)
		else:
			assert False

	def getPeerName(self):
		return self.peerName

	def send(self, label, data):
		assert len(data) <= 65536
		pri = Socket._getLabelPriority(label)
		self.packetQueue.put((pri, label, data), True)

	def close(self):
		self.sendThread.stop()
		self.ssl_sock.close()
		self.ssl_sock = None

	def _onRecv(self):
		# receive packet header
		headerLen = struct.calcsize("!II")
		header = ""
		while len(header) < headerLen:
			header += self.ssl_sock.recv(headerLen - len(header))

		# receive packet content
		label, dataLen = struct.unpack("!II", header)
		data = ""
		while len(data) < dataLen:
			data += self.ssl_sock.recv(dataLen - len(data))

		# call event func
		if label in self.labelRecvFuncDict:
			if self.labelRecvFuncDict[label].keepPacket:
				data = header + data
			self.labelRecvFuncDict[label].func(self.ssl_sock, label, data)
		else:
			if self.recvFunc.keepPacket:
				data = header + data
			self.recvFunc.func(self.ssl_sock, label, data)

	def _onError(self):
		self.close()

	@staticmethod
	def _getPeerName(ssl_sock):
		cert = ssl_sock.getpeercert()
		if cert is not None and "subject" in cert:
			for item in cert["subject"]:
				if item[0][0] == "commonName":
					return item[0][1]
		return None

	@staticmethod
	def _getLabelPriority(label):
		if label == 0:
			return 0
		else:
			return 1

	@staticmethod
	def _getPacket(label, data):
		header = struct.pack("!II", label, len(data))
		return header + data

class BulkFile:
	pass

class _ClientEndPointConnThread(threading.Thread):

	def __init__(self, hostname, port):
		super(connthread, self).__init__()
		self.hostname = hostname
		self.port = port

	def run(self):
		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  
		ssl_sock = ssl.wrap_socket(sock, certfile=self.certFile, keyfile=self.privkeyFile,
				                   cert_reqs=ssl.CERT_REQUIRED, ca_certs=self.caCertFile,
				                   ssl_version=ssl.PROTOCOL_SSLv3)
		ret = ssl_sock.connect_ex((self.hostname, self.port))
		if ret != 0:
			ssl_sock.close()
			return

		peerName = Socket._getPeerName(ssl_sock)
		if peerName is None or peerName != self.hostname:
			ssl_sock.close()
			return

		GLib.idle_add(self._onIdle, ssl_sock)

class _SocketSendThread(threading.Thread):

	def __init__(self, parent):
		self.parent = parent
		self.stopFlag = False

	def stop(self):
		self.stopFlag = True
		self.parent.packetQueue.put((0xFF, None, None))		# feed PriorityQueue.get()
		self.join()

	def run(self):
		while not self.stopFlag:
			pri, label, data = self.parent.packetQueue.get(True)
			if pri == 0xFF:
				continue
			try:
				p = Socket._getPacket(label, data)
				self.parent.ssl_sock.sendall(p)
			except:
				pass

class _SocketRecvFuncInfo:

	def __init__(self, func, keepPacket):
		self.func = func
		self.keepPacket = keepPacket

