#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import socket
import ssl

address = ('127.0.0.1', 31500)
ss = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
ssl_ss = ssl.wrap_socket(ss, certfile="/etc/selfnetd/cert.pem", keyfile="/etc/selfnetd/privkey.pem",
                         ca_certs="/etc/selfnetd/ca-cert.pem", cert_reqs=ssl.CERT_REQUIRED,
                         ssl_version=ssl.PROTOCOL_SSLv3, server_side=True)

ssl_ss.bind(address)
ssl_ss.listen(5)

ssl_sock, addr = ssl_ss.accept()
print 'got connected from', addr


ssl_sock.send('byebye')
ra = ssl_sock.recv(512)
print ra

cert = ssl_sock.getpeercert()
print cert["subject"]["commonName"]

ssl_sock.shutdown(socket.SHUT_RDWR)
ssl_sock.close()

ssl_ss.close()  
