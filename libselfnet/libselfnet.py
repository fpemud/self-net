#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

class Daemon:

	@staticmethod
	def getInstance():
		pass


	def register(self):
		pass


class Client:





	def release(self):
		pass





class SnParam:

	def __init__(self):
		self.cfgDir = "/etc/selfnetd"
		self.cfgUserDir = ".config/selfnetd"
		self.libDir = "/usr/lib/selfnetd"
		self.dataDir = "/usr/share/selfnetd"
		self.tmpDir = None

		self.peerProbeTimeout = 1000			# 1s
		self.peerKeepAliveTimeout = 1000		# 1s

		self.mainloop = None
		self.configManager = None
		self.peerManager = None

