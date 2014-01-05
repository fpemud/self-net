#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import socket
import ssl
import struct
import threading
from Queue import PriorityQueue
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

	def _onAccept(self, source, cb_condition):
		new_sock, addr = self.ssl_sock.accept()
	
		peerName = SnPeerSocket._getPeerName(new_sock)
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

	def setEventFunc(self, funcName, func):
		if funcName == "connected":
			assert self.connectFunc is None and func is not None
			self.connectFunc = func
		else:
			assert False

	def connect(self, hostname, port):
		# run the thread
		t = _ConnThread(hostname, port)
		t.start()

	def _onIdle(self, ssl_sock):
		self.connectFunc(SnPeerSocket(ssl_sock))
		return False

class SnPeerSocket:

	def __init__(self, ssl_sock):
		self.ssl_sock = ssl_sock

		self.peerName = SnPeerSocket._getPeerName(self.ssl_sock)
		assert self.peerName is not None

		self.packetQueue = PriorityQueue()
		self.sendThread = _SendThread(self)
		self.isClosing = False

		self.sysDataRecvFunc = None
		self.rejectFunc = None
		self.errorFunc = None
		self.recvFunc = None

	def setEventFunc(self, funcName, *args):
		if funcName == "system_data_received":
			assert sysDataRecvFunc is None and func is not None
			self.sysDataRecvFunc = func
			GLib.io_add_watch(self.ssl_sock, GLib.IO_IN, self._onRecv)
		elif funcName == "rejection_received":
			assert self.rejectFunc is None and func is not None
			self.rejectFunc = func
			GLib.io_add_watch(self.ssl_sock, GLib.IO_IN, self._onRecv)
		elif funcName == "low_level_error":
			assert self.errorFunc is None and func is not None
			self.errorFunc = func
			GLib.io_add_watch(self.ssl_sock, GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP, self._onError)
		elif funcName == "application_packet_received":
			assert self.recvFunc is None and func is not None
			self.recvFunc = func
			GLib.io_add_watch(self.ssl_sock, GLib.IO_IN, self._onRecv)
		else:
			assert False

	def getPeerName(self):
		return self.peerName

	def sendSystemData(self, data):
		pri = 1
		header = struct.pack("!QQI", 0, 0, len(data))
		packet = header + data
		self.packetQueue.put((pri, packet), True)

	def sendApplicationPacket(self, packet):
		pri = 2
		self.packetQueue.put((pri, packet), True)

	def reject(self, rejectMessage):
		self.isClosing = True
		self.sendThread.stop()

		# send reject message, ignore failure
		header = struct.pack("!QQI", 0, 1, len(data))
		packet = header + data
		self.ssl_sock.send(packet)

		self.ssl_sock.close()
		self.ssl_sock = None

	def close(self):
		self._doClose()

	def _onRecv(self):
		# receive packet header
		headerLen = struct.calcsize("!QQI")
		header = ""
		while len(header) < headerLen:
			header += self.ssl_sock.recv(headerLen - len(header))

		# receive packet content
		srcLabel, dstLabel, dataLen = struct.unpack("!QQI", header)
		data = ""
		while len(data) < dataLen:
			data += self.ssl_sock.recv(dataLen - len(data))

		# closing, consume data, don't do real operation
		if self.isClosing:
			return

		# for system data
		if dstLabel == 0:
			self.sysDataRecvFunc(self.ssl_sock, data)
			return

		# for rejection
		if dstLabel == 1:
			self.rejectFunc(self.ssl_sock, data)
			self._doClose()
			return

		# for application packet
		self.recvFunc(self.ssl_sock, srcLabel, dstLabel, header + data)

	def _onError(self):
		self._doClose()

	def _doClose(self):
		self.isClosing = True
		self.sendThread.stop()
		self.ssl_sock.close()
		self.ssl_sock = None

	@staticmethod
	def _getPeerName(ssl_sock):
		cert = ssl_sock.getpeercert()
		if cert is not None and "subject" in cert:
			for item in cert["subject"]:
				if item[0][0] == "commonName":
					return item[0][1]
		return None

	@staticmethod
	def _getPacket(srcLabel, dstLabel, data):
		header = struct.pack("!QQI", srcLabel, dstLabel, len(data))
		return header + data

class _ConnThread(threading.Thread):

	def __init__(self, parent, hostname, port):
		super(_ConnThread, self).__init__()
		self.parent = parent
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

		peerName = SnPeerSocket._getPeerName(ssl_sock)
		if peerName is None or peerName != self.hostname:
			ssl_sock.close()
			return

		GLib.idle_add(self.parent._onIdle, ssl_sock)

class _SendThread(threading.Thread):

	def __init__(self, parent):
		super(_SendThread, self).__init__()
		self.parent = parent
		self.stopFlag = False

	def stop(self):
		"""may bring 50ms delay"""
		self.stopFlag = True
		self.parent.packetQueue.put((0xFF, None))		# feed PriorityQueue.get()
		self.join()

	def run(self):
		while not self.stopFlag:
			pri, packet = self.parent.packetQueue.get(True)
			if pri == 0xFF:
				continue
			sendLen = 0
			while not self.stopFlag:
				sendLen += self.parent.ssl_sock.send(packet[sendLen:])
				if sendLen >= len(packet):
					break
				time.sleep(0.05)

