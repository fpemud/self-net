#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import socket
import ssl

address = ('127.0.0.1', 31500)  
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  

ssl_sock = ssl.wrap_socket(s, certfile="/etc/selfnetd/cert.pem", keyfile="/etc/selfnetd/privkey.pem",
                           ca_certs="/etc/selfnetd/ca-cert.pem", cert_reqs=ssl.CERT_REQUIRED,
                           ssl_version=ssl.PROTOCOL_SSLv3)
ssl_sock.connect(address)
  
data = ssl_sock.recv(512)  
print 'the data received is',data  
  
ssl_sock.send('hihi')  
ssl_sock.close()
