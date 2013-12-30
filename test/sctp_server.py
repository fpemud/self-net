#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import socket
import sctp

address = ('127.0.0.1', 31500)
s = sctp.sctpsocket_tcp(socket.AF_INET)
s.bind(address)  
s.listen(5)

ss, addr = s.accept()  
print 'got connected from',addr  
  
ss.sctp_send('byebye')  
ra = ss.sctp_recv(512)  
print ra  
  
ss.close()  
s.close()  
