#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import socket
import ssl
import struct
import threading
from Queue import PriorityQueue
from gi.repository import GLib

class SnPluginServer:

	def __init__(self):
		self.serverFile = None
		self.sock = None
		self.source_id = None
		self.acceptFunc = None

	def setEventFunc(self, funcName, func):
		if funcName == "accept":
			assert self.acceptFunc is None and func is not None
			self.acceptFunc = func
		else:
			assert False

	def start(self, serverFile):
		assert self.serverFile is None

		self.serverFile = serverFile

		# Make sure the socket does not already exist
		try:
			os.unlink(self.serverFile)
		except OSError:
			if os.path.exists(self.serverFile):
				raise

		self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
		self.sock.bind(self.serverFile)
		self.sock.listen(5)

		self.source_id = GLib.io_add_watch(self.sock, GLib.IO_IN, self._onAccept)

	def stop(self):
		assert self.serverFile is not None

		GLib.source_remove(self.source_id)
		self.source_id = None
		self.sock.close()
		self.sock = None
		self.serverFile = None

	def _onAccept(self, source, cb_condition):
		new_sock, addr = self.sock.accept()
		self.acceptFunc(SnPluginSocket(new_sock))
		return True

class SnPluginSocket:

	def __init__(self, sock):
		self.sock = sock

		self.packetQueue = PriorityQueue()
		self.sendThread = _SendThread(self)
		self.err_source_id = GLib.io_add_watch(self.sock, GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP, self._onError)
		self.recv_source_id = None

		self.sysDataRecvFunc = None
		self.recvFunc = None

	def setEventFunc(self, funcName, *args):
		if funcName == "system_data_received":
			assert sysDataRecvFunc is None and func is not None
			self.sysDataRecvFunc = func
			if self.recv_source_id is None:
				self.recv_source_id = GLib.io_add_watch(self.sock, GLib.IO_IN, self._onRecv)
		elif funcName == "application_packet_received":
			assert self.recvFunc is None and func is not None
			self.recvFunc = func
			if self.recv_source_id is None:
				self.recv_source_id = GLib.io_add_watch(self.sock, GLib.IO_IN, self._onRecv)
		else:
			assert False

	def getPeerUserId(self):
		return 0

	def getPeerUserName(self):
		return ""

	def sendSystemData(self, data):
		pri = 1
		header = struct.pack("!QQI", 0, 0, len(data))
		packet = header + data
		self.packetQueue.put((pri, packet), True)

	def sendApplicationPacket(self, packet):
		pri = 2
		self.packetQueue.put((pri, packet), True)

	def reject(self, rejectMessage):
		self._doCloseStage1()
		if True:
			# send reject message, ignore failure
			header = struct.pack("!QQI", 0, 1, len(data))
			packet = header + data
			self.sock.send(packet)
		self._doCloseStage2()

	def close(self):
		self._doClose()

	def _onRecv(self):
		# receive packet header
		headerLen = struct.calcsize("!QQI")
		header = ""
		while len(header) < headerLen:
			header += self.sock.recv(headerLen - len(header))
		srcLabel, dstLabel, dataLen = struct.unpack("!QQI", header)

		# receive packet content
		data = ""
		while len(data) < dataLen:
			data += self.sock.recv(dataLen - len(data))

		# for system data
		if dstLabel == 0:
			self.sysDataRecvFunc(self.sock, data)
			return

		# for application packet
		self.recvFunc(self.sock, srcLabel, dstLabel, header + data)

	def _onError(self):
		self._doClose()

	def _doClose(self):
		self._doCloseStage1()
		self._doCloseStage2()

	def _doCloseStage1(self):
		GLib.source_remove(self.err_source_id)
		self.err_source_id = None
		if self.recv_source_id is not None:
			GLib.source_remove(self.recv_source_id)
			self.recv_source_id = None
		self.sendThread.stop()

	def _doCloseStage2(self):
		self.sock.close()
		self.sock = None

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
				sendLen += self.parent.sock.send(packet[sendLen:])
				if sendLen >= len(packet):
					break
				time.sleep(0.05)

