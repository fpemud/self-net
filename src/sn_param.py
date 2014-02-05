#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os

class SnParam:

	def __init__(self):
		self.cfgDir = "/etc/selfnetd"
		self.libDir = "/usr/lib/selfnetd"
		self.dataDir = "/usr/share/selfnetd"
		self.moduleDir = os.path.join(self.libDir, "modules")
		self.runDir = "/run/selfnetd"
		self.logDir = "/var/log/selfnetd"

		self.certFile = os.path.join(self.cfgDir, "cert.pem")
		self.privkeyFile = os.path.join(self.cfgDir, "privkey.pem")
		self.caCertFile = os.path.join(self.cfgDir, "ca-cert.pem")
		self.caPrivkeyFile = os.path.join(self.cfgDir, "ca-privkey.pem")

		self.confFile = os.path.join(self.cfgDir, "selfnetd.conf")
		self.hostsFile = os.path.join(self.cfgDir, "hosts.xml")
		self.modulesFile = os.path.join(self.cfgDir, "modules.xml") 

		self.pidFile = os.path.join(self.runDir, "selfnetd.pid")
		self.logFile = os.path.join(self.logDir, "selfnetd.log")

		# to be set
		self.tmpDir = None				# str
		self.logLevel = None			# enum

		self.mainloop = None			# obj
		self.configManager = None		# obj
		self.localManager = None		# obj
		self.peerManager = None			# obj

