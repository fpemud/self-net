#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import sys
sys.path.append('../src')
from sn_util import SnUtil
from sn_util import ClientEndPoint

c = ClientEndPoint("/etc/selfnetd/cert.pem", "/etc/selfnetd/privkey.pem", "/etc/selfnetd/ca-cert.pem")
ss = c.connect("127.0.0.1", 31500)

print 'connected to', ss.getPeerName()

data = ss.recv(0)
print 'the data received is',data  

ss.send(0, "hihi")
ss.close()

