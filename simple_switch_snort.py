# Copyright (C) 2013 Nippon Telegraph and Telephone Corporation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import print_function

import array

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ipv4
from ryu.lib.packet import icmp
from ryu.lib import snortlib

import os
import time
import psutil
import signal
import threading
import sys

import socketio

@sio.event
def connect():
    print('connection established')

@sio.event
def my_message(data):
    print('message received with ', data)
    sio.emit('my response', {'response': 'my response'})

@sio.on('python-message')
def on_message(data):
    print('I received a message!'+data)    

@sio.event
def disconnect():
    print('disconnected from server')

def update_rule():
    copy_command = "cp /usr/local/" + file_name + " /etc/snort/rules/"
    os.popen(copy_command).readlines()
    rule_file = open("/etc/snort/snort.conf", "a")
    rule_file.write("include $RULE_PATH/" + file_name)
    rule_file.close
    PROCNAME = 'snort'
    for proc in psutil.process_iter():
        try:
            if proc.name() == PROCNAME:
                snort_process = psutil.Process(proc.pid)
                snort_process.send_signal(signal.SIGHUP)
        except:
            pass
    return "True",200

def signature_make():
    my_message("sending signature file name")
    


class SimpleSwitchSnort(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {'snortlib': snortlib.SnortLib}
    def __init__(self, *args, **kwargs):
        super(SimpleSwitchSnort, self).__init__(*args, **kwargs)
        self.snort = kwargs['snortlib']
        self.snort_port = 1
        self.main_switch = "172.17.206.2"
        self.mac_to_port = {}
        node_thread = threading.Thread(target=start_nodeServer)
        node_thread.start()
        node_thread.join()

        socket_config = {'unixsock': True}

        self.snort.set_config(socket_config)
        self.snort.start_socket_server()
        sio = socketio.Client()
        time.sleep(5)
        sio.connect('http://localhost:3000')
        sio.emit('python-message', {'foo': 'bar'})
        sio.wait()


    def start_nodeServer(self):
        node_start = "node server.js"
        os.popen(node_start).readlines()
    
    
    def packet_print(self, pkt):
        pkt = packet.Packet(array.array('B', pkt))

        eth = pkt.get_protocol(ethernet.ethernet)
        _ipv4 = pkt.get_protocol(ipv4.ipv4)
        _icmp = pkt.get_protocol(icmp.icmp)

        if _icmp:
            self.logger.info("%r", _icmp)

        if _ipv4:
            self.logger.info("%r", _ipv4)

        if eth:
            self.logger.info("%r", eth)

        # for p in pkt.protocols:
        #     if hasattr(p, 'protocol_name') is False:
        #         break
        #     print('p: %s' % p.protocol_name)

    @set_ev_cls(snortlib.EventAlert, MAIN_DISPATCHER)
    def _dump_alert(self, ev):
        msg = ev.msg

        #print('alertmsg: %s' % ''.join(msg.alertmsg))
        print(msg.alertmsg)
        self.packet_print(msg.pkt)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # install table-miss flow entry
        #
        # We specify NO BUFFER to max_len of the output action due to
        # OVS bug. At this moment, if we specify a lesser number, e.g.,
        # 128, OVS will send Packet-In with invalid buffer_id and
        # truncated packet data. In that case, we cannot output packets
        # correctly.
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, datapath, priority, match, actions):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]

        mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                match=match, instructions=inst)
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        dst = eth.dst
        src = eth.src

        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})

        # self.logger.info("packet in %s %s %s %s", dpid, src, dst, in_port)

        # learn a mac address to avoid FLOOD next time.
        self.mac_to_port[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD        
        
        if str(msg.datapath.address[0]) == self.main_switch:
            actions = [parser.OFPActionOutput(out_port),
                   parser.OFPActionOutput(self.snort_port)]
            
        else:
            actions = [parser.OFPActionOutput(out_port)]

        # install a flow to avoid packet_in next time
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst)
            self.add_flow(datapath, 1, match, actions)

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)
