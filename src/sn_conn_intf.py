#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import socket
import ssl
import struct
import threading
from gi.repository import GLib

class ServerEndPoint:

	def __init__(self, certFile, privkeyFile, caCertFile):
		self.certFile = certFile
		self.privkeyFile = privkeyFile
		self.caCertFile = caCertFile
		self.port = None
		self.sock = None
		self.ssl_sock = None
		self.allowedPeerList = []
		self.acceptFunc = None

	def setAllowedPeerList(self, peerList):
		self.allowedPeerList = peerList

	def setEventFunc(self, funcName, func):
		if funcName == "accept":
			assert self.acceptFunc is None and func is not None
			self.acceptFunc = func
		else:
			assert False

	def listen(self, port):
		self.port = port

		self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.ssl_sock = ssl.wrap_socket(self.sock, certfile=self.certFile, keyfile=self.privkeyFile,
		                                cert_reqs=ssl.CERT_REQUIRED, ca_certs=self.caCertFile,
		                                ssl_version=ssl.PROTOCOL_SSLv3, server_side=True)
		self.ssl_sock.bind(('0.0.0.0', self.port))
		self.ssl_sock.listen(5)

		GLib.io_add_watch(self.sock, GLib.IO_IN, self._onAccept)

	def close(self):
		self.ssl_sock.close()
		self.ssl_sock = None
		self.sock = None

	def _onAccept(self, source, cb_condition):
		new_sock, addr = self.ssl_sock.accept()
	
		peerName = Socket._getPeerName(new_sock)
		if peerName is None or peerName not in self.allowedPeerList:
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
		# create thread class
		class connthread(threading.Thread):
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
				if peerName is None or peerName != hostname:
					ssl_sock.close()
					return

				GLib.idle_add(self.connectFunc, Socket(ssl_sock))

		# run the thread
		t = connthread(hostname, port)
		t.start()

class Socket:

	def __init__(self, ssl_sock):
		self.ssl_sock = ssl_sock

		self.peerName = Socket._getPeerName(self.ssl_sock)
		assert self.peerName is not None

		self.recvFuncDict = dict()
		self.errorFunc = None

	def setEventFunc(self, funcName, *args):
		if funcName == "recv":
			assert len(args) == 2
			channel = args[0]
			func = args[1]
			assert isinstance(channel, int) and channel not in self.recvFuncDict and func is not None
			self.recvFuncDict[channel] = func
			GLib.io_add_watch(self.ssl_sock, GLib.IO_IN, self._onRecv)
		if funcName == "error":
			assert len(args) == 1
			func = args[0]
			assert self.errorFunc is None and func is not None
			self.errorFunc = func
			GLib.io_add_watch(self.ssl_sock, GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP, self._onError)
		else:
			assert False

	def getPeerName(self):
		return self.peerName

	def send(self, channel, data):
		"""raise exception when failure"""

		header = struct.pack("!II", channel, len(data))
		self.ssl_sock.sendall(header + data)

	def close(self):
		self.ssl_sock.close()
		self.ssl_sock = None

	def _onRecv(self):
		# receive packet header
		headerLen = struct.calcsize("!II")
		header = ""
		while len(header) < headerLen:
			header += self.ssl_sock.recv(headerLen - len(header))

		# receive packet content
		channel, dataLen = struct.unpack("!II", header)
		data = ""
		while len(data) < dataLen:
			data += self.ssl_sock.recv(dataLen - len(data))

		self.recvFuncDict[0](data)

	def _onError(self):
		pass

	@staticmethod
	def _getPeerName(ssl_sock):
		cert = ssl_sock.getpeercert()
		if cert is not None and "subject" in cert:
			for item in cert["subject"]:
				if item[0][0] == "commonName":
					return item[0][1]
		return None

class BulkFile:
	pass

