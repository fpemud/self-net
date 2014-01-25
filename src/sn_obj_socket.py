#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

class SnObjSocket:
	"""SnObjSocket has 4 functions:
	     1. send & receive objects
	     2. object has priority
	     3. do sending & receiving in background
	     4. receive & error callback in main thread
	"""

	def __init__(self, sock, recvFunc, errorFunc):
		self.sock = sock
		self.recvFunc = recvFunc
		self.errorFunc = errorFunc
		self.recvThread = _RecvThread(self)
		self.sendThread = _SendThread(self)
		self.sendThread.start()
		self.recvThread.start()

	def sendObject(self, *args):
		if len(args) == 0:
			raise Exception("argument error")
		elif len(args) == 1:
			pri = 0
			obj = args[0]
		else:
			pri = args[0]
			obj = args[1]
		self.sendThread.sendObjQueue.put((pri, obj))

	def close(self):
		self.recvThread.stop()
		self.sendThread.stop()
		self.sock.close()
		self.sock = None

	def _onIdle(self):
		assert self.sock is not None

		obj = self.recvObjQueue.get(False)
		if obj is not None:
			self.recvFunc(obj)
		return False

class _RecvThread(threading.Thread):

	def __init__(self, parent):
		super(_RecvThread, self).__init__()
		self.parent = parent
		self.sock = parent.sock
		self.recvObjQueue = PriorityQueue()
		self.stopFlag = False

	def stop(self):
		"""may wait forever"""
		self.stopFlag = True
		self.join()

	def run(self):
		while not self.stopFlag:
			# receive packet header
			headerLen = struct.calcsize("!II")
			header = ""
			while len(header) < headerLen:
				header += self.sock.recv(headerLen - len(header))
			dataPri, dataLen = struct.unpack("!II", header)

			# receive packet content
			data = ""
			while len(data) < dataLen:
				data += self.sock.recv(dataLen - len(data))

			# packet -> object
			obj = pickle.loads(data)
			self.recvObjQueue.put((dataPri, obj))
			
			# register callback
			GLib.idle_add(self.parent._onIdle)

class _SendThread(threading.Thread):

	def __init__(self, sock):
		super(_SendThread, self).__init__()
		self.sock = sock
		self.sendObjQueue = PriorityQueue()
		self.stopFlag = False

	def stop(self):
		"""may bring 50ms delay"""
		self.stopFlag = True
		self.sendObjQueue.put((0xFF, None))		# feed PriorityQueue.get()
		self.join()

	def run(self):
		while not self.stopFlag:
			pri, obj = self.sendObjQueue.get(True)
			if pri == 0xFF:
				continue

			data = pickle.dumps(obj)
			header = struct.unpack("!II", pri, len(data))
			packet = header + data

			sendLen = 0
			while not self.stopFlag:
				sendLen += self.sock.send(packet[sendLen:])
				if sendLen >= len(packet):
					break
				time.sleep(0.05)

