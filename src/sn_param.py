#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os

class SnParam:

	def __init__(self):
		self.cfgDir = "/etc/selfnetd"
		self.cfgUserDir = ".config/selfnetd"
		self.libDir = "/usr/lib/selfnetd"
		self.dataDir = "/usr/share/selfnetd"
		self.moduleDir = os.path.join(self.libDir, "modules")
		self.runDir = "/run/selfnetd"
		self.tmpDir = None

		self.certFile = os.path.join(self.cfgDir, "cert.pem")
		self.privkeyFile = os.path.join(self.cfgDir, "privkey.pem")
		self.caCertFile = os.path.join(self.cfgDir, "ca-cert.pem")
		self.caPrivkeyFile = os.path.join(self.cfgDir, "ca-privkey.pem")

		self.confFile = os.path.join(self.cfgDir, "selfnetd.conf")
		self.hostsFile = os.path.join(self.cfgDir, "hosts.xml")
		self.modulesFile = os.path.join(self.cfgDir, "modules.xml") 
		self.localServerFile = "/run/selfnetd/socket"

		self.mainloop = None
		self.configManager = None
		self.localManager = None
		self.peerManager = None
		self.moduleManager = None

