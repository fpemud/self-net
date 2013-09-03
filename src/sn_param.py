#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

class VirtParam:

	def __init__(self):
		self.cfgDir = "/etc/self-net"
		self.cfgUserDir = ".config/self-net"
		self.libDir = "/usr/lib/self-net"
		self.dataDir = "/usr/share/self-net"
		self.tmpDir = None

		self.mainloop = None
		self.configManager = None
		self.peerManager = None

