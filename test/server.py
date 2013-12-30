#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import sys
sys.path.append('../src')
from sn_util import SnUtil
from sn_util import ServerEndPoint

s = ServerEndPoint("/etc/selfnetd/cert.pem", "/etc/selfnetd/privkey.pem", "/etc/selfnetd/ca-cert.pem")
s.listen(31500)
ss = s.accept()
  
print 'got connected from', ss.getPeerName()
  
ss.send(0, 'byebye')  
ra = ss.recv(0)
print ra  

ss.close()  
s.close()  
