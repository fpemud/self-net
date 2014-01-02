#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import sys
sys.path.append('../src')
from sn_util import SnUtil
from sn_util import ServerEndPoint

def onAccept(ss):
	print 'got connected from', ss.getPeerName()
	ss.send(0, 'byebye')

def onSend():
	pass

def onRecv(channel, buf):
	print "%d, %s"%(channel, buf)

mainloop = GLib.MainLoop()

s = ServerEndPoint("/etc/selfnetd/cert.pem", "/etc/selfnetd/privkey.pem", "/etc/selfnetd/ca-cert.pem", onAccept, onSend, onRecv)
s.listen(31500)

mainloop.run()


