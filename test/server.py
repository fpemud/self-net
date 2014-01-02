#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import sys
from gi.repository import GLib
sys.path.append('../src')
from sn_conn_intf import ServerEndPoint

class Main:

	def __init__(self):
		self.ss = None

	def onAccept(self, ss):
		print 'got connected from', ss.getPeerName()
		self.ss = ss

		self.ss.setEventFunc("recv", 0, self.onRecv)
		self.ss.send(0, 'byebye')

	def onRecv(self, ss, channel, buf):
		print "%d %s"%(channel, buf)

	def run(self):
		mainloop = GLib.MainLoop()

		s = ServerEndPoint("/etc/selfnetd/cert.pem", "/etc/selfnetd/privkey.pem", "/etc/selfnetd/ca-cert.pem")
		s.setAllowedPeerList(["fpemud-workstation"])
		s.setEventFunc("accept", self.onAccept)
		s.listen(31500)

		mainloop.run()

m = Main()
m.run()


