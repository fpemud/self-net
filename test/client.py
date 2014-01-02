#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import sys
from gi.repository import GLib
sys.path.append('../src')
from sn_conn_intf import ClientEndPoint

class Main:

	def __init__(self):
		self.ss = None

	def onConnect(self, ss):
		print 'connected to', ss.getPeerName()
		self.ss = ss
		self.ss.setEventFunc("recv", 0, self.onRecv)

	def onRecv(self, ss, channel, buf):
		print 'the data received is',buf  
		ss.send(0, "hihi")
		ss.close()

	def run(self):
		mainloop = GLib.MainLoop()

		c = ClientEndPoint("/etc/selfnetd/cert.pem", "/etc/selfnetd/privkey.pem", "/etc/selfnetd/ca-cert.pem")
		c.setEventFunc("connected", self.onConnect)

		mainloop.run()

m = Main()
m.run()

