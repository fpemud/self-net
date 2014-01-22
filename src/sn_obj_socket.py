#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

class SnObjSocket:

	def __init__(self, sock):
		self.sock = sock

		self.recvFunc = None
		self.errorFunc = None
		self.sendThread = _SendThread(self)
		self.recvThread = _RecvThread(self)

	def setEventFunc(self, funcName, func):
		if funcName == "receive":
			assert self.recvFunc is None
			self.recvFunc = func
		elif funcName == "error":
			assert self.errorFunc is None
			self.errorFunc = func
		else:
			assert False

	def sendObject(self, obj):
		pass

	def close(self):
		self.sock.close()
		self.sock = None

class _RecvThread(threading.Thread):

	def __init__(self, parent):
		super(_RecvThread, self).__init__()
		self.parent = parent
		self.sf = self.parent.sock.makefile()
		self.recvBuffer = ""
		self.recvObjQueue = PriorityQueue()
		self.stopFlag = False

	def stop(self):
		"""may wait forever"""
		self.stopFlag = True
		self.join()

	def run(self):
		while not self.stopFlag:
			pkt = pickle.load(self.sf)
			self.recvObjQueue.put((pkt.head.priority, pkt.obj))

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
