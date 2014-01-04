#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

"""
Here we describe the protocol detail of self-net.

Protocol toplogy:
  +----------------------------------------------+             +----------------------------------------------+ 
  |Host1                                         |             |Host2                                         | 
  |                                              |             |                                              | 
  |  +----------+                    +--------+  |             |  +----------+                    +--------+  | 
  |  |Plugin1   |                    |        |  |             |  |Plugin1   |                    |        |  | 
  |  |          |                    |        |<--------+      |  |          |                    |        |<--------+ 
  |  |  +----+  |                    |        |  |      |      |  |  +----+  |                    |        |  |      |
  |  |  |App1|  |                    |        |  |      |      |  |  |App1|  |                    |        |  |      |
  |  |  +----+  | unix-domain-socket |        |  |      |      |  |  +----+  | unix-domain-socket |        |  |      |
  |  |          |<------------------>|        |  |      |      |  |          |<------------------>|        |  |      |
  |  |  +----+  |                    |selfnetd|  |      |      |  |  +----+  |                    |selfnetd|  |      | 
  |  |  |App2|  |                    |        |  |      |      |  |  |App2|  |                    |        |  |      | 
  |  |  +----+  |                    |        |  |      |      |  |  +----+  |                    |        |  |      | 
  |  |          |                    |        |  |      |      |  |          |                    |        |  |      | 
  |  +--------- +                    |        |  |      |      |  +--------- +                    |        |  |      | 
  |                                  |        |  |      |      |                                  |        |  |      | 
  |  +----------+ unix-domain-socket |        |<----+   |      |  +----------+ unix-domain-socket |        |<----+   | 
  |  |Plugin2   |<------------------>|        |  |  |   |      |  |Plugin2   |<------------------>|        |  |  |   | 
  |  +----------+                    +--------+  |  |   |      |  +----------+                    +--------+  |  |   | 
  |                                              |  |   |      |                                              |  |   | 
  +----------------------------------------------+  |   |      +----------------------------------------------+  |   | 
                                                    |   |                                                        |   |
                                                    |   |                    ssl-socket                          |   |
                                                    |   +--------------------------------------------------------+   |
                                                    |                                                                |
                                                    |ssl-socket                                                      |ssl-socket
                                                    |                                                                |
  +----------------------------------------------+  |                                                                |
  |Host3                                         |  |                                                                | 
  |                                              |  |                                                                | 
  |  +----------+                    +--------+  |  |                                                                | 
  |  |Plugin1   |                    |        |  |  |                                                                | 
  |  |          |                    |        |<----+                                                                |
  |  |  +----+  |                    |        |  |                                                                   |
  |  |  |App1|  |                    |        |  |                                                                   | 
  |  |  +----+  | unix-domain-socket |        |  |                                                                   | 
  |  |          |<------------------>|        |  |                                                                   | 
  |  |  +----+  |                    |selfnetd|  |                                                                   | 
  |  |  |App2|  |                    |        |  |                                                                   | 
  |  |  +----+  |                    |        |  |                                                                   | 
  |  |          |                    |        |  |                                                                   | 
  |  +--------- +                    |        |  |                                                                   | 
  |                                  |        |  |                                                                   | 
  |  +----------+ unix-domain-socket |        |<---------------------------------------------------------------------+  
  |  |Plugin2   |<------------------>|        |  | 
  |  +----------+                    +--------+  | 
  |                                              | 
  +----------------------------------------------+ 

From the topology graph above, we can see that every host has a selfnetd daemon,
which are connected by ssl-socket. selfnetd does no business, all the business
are in plugins. Every plugin is a process, it uses unix-domain-socket to
communicate with selfnetd. Sometimes, several light weight business can be hosted
in one plugin as application.

Especially, there would be one application for each user. For example, Host1 runs
a ssh server, Host2 runs ssh client, and Host1 and Host2 both has users foo and
bar. There will be 2 ssh-agent in Host1, one for user foo and one for user bar,
they runs as 2 apps in a plugin, of course the plugin process is priviledged. Also,
there will be 2 ssh-client in Host2, for user foo and bar, run as apps in a
non-priviledged plugin process.

Now you can see heavy socket multiplexing in our network.
The packet path is as follows when Host1_App1 says something with Host2_App1:
  Host1_App1 -> Host1_selfnetd -> Host2_selfnetd -> Host2_App2
In this stream, selfnetd acts as routers, Host1_selfnetd forwards packets to Host2,
Host2_selfnetd forwards packets to App2.

Packet must bring source and destination address for the forwarding to work out,
which is a quadruple:
  (hostName, userName, serviceName, agentOrClient)
But it's too large to be contained in every packet. The problem solver is brought
from MPLS, which is "label".

Packet contains source and destincation label, each label binds to a quadruple.
Plugin registers itself to selfnetd, selfnetd allocates label for it. For the
application case, plugin should register application, and selfnetd allocates label
for each application. selfnetd tells label binding information to plugin/application,
not only the local label binding, but also the label binding of all the online peers.
Having this information, plugin/application can generate/decode packets on itself,
letting selfnetd do pure routing stuff.
"""

class SnRouter:

	def __init__(self, param):
		self.param = param

	def forwardToPeer(self, sock, srcLabel, dstLabel, packet):
		pass

	def forwardToApp(self, sock, srcLabel, dstLabel, packet):
		pass

