#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import socket
import sctp

address = ('127.0.0.1', 31500)  
s = sctp.sctpsocket_tcp(socket.AF_INET) 
s.connect(address)  
  
data = s.sctp_recv(512)  
print 'the data received is',data  
  
s.sctp_send('hihi')  
  
s.close()
