#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

"""
Here we describe some protocol detail of self-net.

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
non-priviledged plugin process. Of course there's system level business, for which
the user is None.

The packet path is as follows when Host1_App1 says something with Host2_App1:
  Host1_App1 -> Host1_selfnetd -> Host2_selfnetd -> Host2_App2
In this data stream, selfnetd acts as routers, Host1_selfnetd forwards packets to
Host2, Host2_selfnetd forwards packets to App2.

Packet must bring source and destination address for the forwarding to work out,
which is:
  (hostName, userName, appName, agentOrClient, systemOrUser)
But it's too large to be contained in every packet. The problem solver is use a 
interger format address, which we call it "label".

Packet contains source and destincation label, each label binds to a triple.
Plugin registers itself to selfnetd, selfnetd allocates label for it. For the
application case, plugin should register application, and selfnetd allocates label
for each application. selfnetd tells label binding information to plugin/application,
not only the local label binding, but also the label binding of all the online peers.
Having this information, plugin/application can generate/decode packets on itself,
letting selfnetd do pure routing stuff.

Label is defined as a 64bit unsigned integer, detail format is as follows:

   63        56 55        24 23        8 7             7 6            6 5        0
  +------------+------------+-----------+---------------+--------------+----------+
  |  hostName  |  userName  |  appName  | agentOrClient | systemOrUser | reserved |
  +------------+------------+-----------+---------------+--------------+----------+

bit63~bit56:
hostName, 8bits, 0x00 is reserved, so selfnet supports 256 hosts. hostName is local
scoped. when generating packet, destination hostName is filled but source hostName
is empty(0x00); when packet is received by selfnetd daemon, destination hostName is
cleared and source hostName is filled. Hence, every host can identify 255 peers, so
the whole net can have 256 hosts.

bit55~bit24:
userName, 32bits. we use system user id to represent userName. All the modern
operating systems have 32bit user id.

bit23~bit8:
appName, 0x00~0x10 is reserved. appName is local scoped, but reversely.

bit7:
agentOrClient, 1=agent, 0=client.

bit6:
systemOrUser, 1=system, 0=user. for system application, userName is invalid, 
should be 0

"""

"""
Here we describe some implementation detail of self-net.

Design Graph:
             +----------------------------------------------------------------------------------------------------------------------------------------------+
             |selfnetd in Host1                                                                                                                             |
             |                                                                                                                                              |
             |  +---------------+      business data (to be forwarded)      +--------------+      business data (to be forwarded)       +----------------+  |
             |  |               |<----------------------------------------->|              |<------------------------------------------>|                |  |
  Plugin1 <---->|SnConnSocketApp|                                           |              |                                            |SnConnSocketPeer|<----> selfnetd in Host2
             |  |               | system data +--------------+              |              |              +---------------+ system data |                |  |
             |  |               |<----------->|              |              |              |              |               |<----------->|                |  |
             |  +---------------+             |              | routing info |              | routing info |               |             +----------------+  |
             |                                | SnAppManager |<------------>| SnConnRouter |<------------>| SnPeerManager |                                 |
             |  +---------------+ system data |              |              |              |              |               | system data +----------------+  |
             |  |               |<----------->|              |              |              |              |               |<----------->|                |  |
             |  |SnConnSocketApp|             +--------------+              |              |              +---------------+             |SnConnSocketPeer|  |
  Plugin2 <---->|               |                                           |              |                                            |                |<----> selfnetd in Host3
             |  |               |<----------------------------------------->|              |<------------------------------------------>|                |  |
             |  +---------------+      business data (to be forwarded)      +--------------+      business data (to be forwarded)       +----------------+  |
             |                                                                                                                                              |
             +----------------------------------------------------------------------------------------------------------------------------------------------+

sn_conn_router.py, sn_conn_peer.py, sn_conn_app.py are the core implementation
of self-net protocol.

sn_conn_router.py:
Provides addressing, routing, endpoint registering functions.

sn_conn_peer.py:
Provides socket for communicating with peers, the socket implementation adds
some new funtions: 1. asynchronous IO; 2. packet splitting
Provides both server socket and client socket, because selfnetd daemon can be
server or client when communicating with other selfnetd daemon.
This socket implementation is based on ssl_socket.

sn_conn_app.py:
Provides socket for communicating with applications, the socket implementation
adds the asynchronous IO and packet splitting functions either.
Provides only server side socket.

"""

class SnConnAddress:
	hostName = None			# str
	userName = None			# str
	appName = None			# str
	agentOrClient = None	# bool
	systemOrUser = None		# bool

class SnConnRouter:

	def __init__(self, param):
		self.param = param
		self.peerLabelDict = dict()
		self.peerSockDict = dict()
		self.appSockDict = dict()

	def addHostEntry(self, peerName, label, sock):
		"""label should in format 0xAB000000"""
	
		assert isinstance(label, int)
		assert peerName not in self.peerLabelDict

		self.peerLabelDict[peerName] = labelPartHost
		self.peerSockDict[label] = sock

	def removeHostEntry(self, peerName):
		del self.peerSockDict[self.peerLabelDict[peerName]]
		del self.peerLabelDict[peerName]

	def addAppEntry(self, label, sock):
		"""label should in format 0x00ABCDEF"""

		assert isinstance(label, int)
		assert label not in self.appSockDict

		self.appSockDict[label] = sock

	def removeAppEntry(self, label):
		del self.appSockDict[label]

	def forwardToPeer(self, packet):
		label = self._getDstLabel(packet)
		sock = self.peerSockDict.get(label & 0xFF000000)
		if sock is None:
			return

	def forwardToApp(self, packet):
		label = self._getDstLabel(packet)
		sock = self.appSockDict.get(label & 0x00FFFFFF)
		if sock is None:
			return

	def _getDstLabel(self, packet):
		return struct.unpack("!I", packet)

