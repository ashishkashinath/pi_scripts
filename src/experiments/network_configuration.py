__author__ = 'Rakesh Kumar'

import time
import os
import json
import httplib2
import fcntl
import struct
from socket import *

from collections import defaultdict
from functools import partial
from mininet.net import Mininet
from mininet.node import RemoteController
from mininet.node import OVSSwitch
from controller_man import ControllerMan
from model.network_graph import NetworkGraph
from model.match import Match

from experiments.topologies.ring_topo import RingTopo
from experiments.topologies.clos_topo import ClosTopo
from experiments.topologies.linear_topo import LinearTopo
from experiments.topologies.fat_tree import FatTree
from experiments.topologies.two_ring_topo import TwoRingTopo
from experiments.topologies.ring_line_topo import RingLineTopo
from experiments.topologies.clique_topo import CliqueTopo
from experiments.topologies.ameren_topo import AmerenTopo

from synthesis.dijkstra_synthesis import DijkstraSynthesis
from synthesis.aborescene_synthesis import AboresceneSynthesis
from synthesis.synthesize_qos import SynthesizeQoS
from synthesis.synthesis_lib import SynthesisLib


class NetworkConfiguration(object):

    def __init__(self, controller, 
                 topo_name,
                 topo_params,
                 conf_root,
                 synthesis_name,
                 synthesis_params):

        self.controller = controller
        self.topo_name = topo_name
        self.topo_params = topo_params
        self.topo_name = topo_name
        self.conf_root = conf_root
        self.synthesis_name = synthesis_name
        self.synthesis_params = synthesis_params

        self.controller_port = None
        self.topo = None
        self.nc_topo_str = None
        self.init_topo()
        self.init_synthesis()

        self.mininet_obj = None
        self.cm = None
        self.ng = None

        # Setup the directory for saving configs, check if one does not exist,
        # if not, assume that the controller, mininet and rule synthesis needs to be triggered.
        self.conf_path = self.conf_root + str(self) + "/"
        if not os.path.exists(self.conf_path):
            os.makedirs(self.conf_path)
            self.load_config = False
            self.save_config = True
        else:
            self.load_config = True
            self.save_config = False

        # Initialize things to talk to controller
        self.baseUrlRyu = "http://localhost:8080/"

        self.h = httplib2.Http(".cache")
        self.h.add_credentials('admin', 'admin')

    def __str__(self):
        return self.controller + "_" + str(self.synthesis) + "_" + str(self.topo)

    def __del__(self):
        self.cm.stop_controller()
        self.cleanup_mininet()

    def init_topo(self):
        if self.topo_name == "ring":
            self.topo = RingTopo(self.topo_params)
            self.nc_topo_str = "Ring topology with " + str(self.topo.total_switches) + " switches"
        elif self.topo_name == "clostopo":
            self.topo = ClosTopo(self.topo_params)
            self.nc_topo_str = "Clos topology with " + str(self.topo.total_switches) + " switches"
        elif self.topo_name == "linear":
            self.topo = LinearTopo(self.topo_params)
            self.nc_topo_str = "Linear topology with " + str(self.topo_params["num_switches"]) + " switches"
        else:
            raise NotImplementedError("Topology: %s" % self.topo_name)
            
    def init_synthesis(self):
        if self.synthesis_name == "DijkstraSynthesis":
            self.synthesis_params["master_switch"] = self.topo_name == "linear"
            self.synthesis = DijkstraSynthesis(self.synthesis_params)

        elif self.synthesis_name == "SynthesizeQoS":
            self.synthesis_params["same_output_queue"] = False
            self.synthesis = SynthesizeQoS(self.synthesis_params)

        elif self.synthesis_name == "AboresceneSynthesis":
            self.synthesis = AboresceneSynthesis(self.synthesis_params)

    def trigger_synthesis(self):
        if self.synthesis_name == "DijkstraSynthesis":
            self.synthesis.network_graph = self.ng
            self.synthesis.synthesis_lib = SynthesisLib("localhost", "8181", self.ng)
            self.synthesis.synthesize_all_node_pairs()

        elif self.synthesis_name == "SynthesizeQoS":
            self.synthesis.network_graph = self.ng
            self.synthesis.synthesis_lib = SynthesisLib("localhost", "8181", self.ng)
            self.synthesis.synthesize_all_node_pairs(50)

            self.measure_flow_rates(50)

        elif self.synthesis_name == "AboresceneSynthesis":
            self.synthesis.network_graph = self.ng
            self.synthesis.synthesis_lib = SynthesisLib("localhost", "8181", self.ng)
            flow_match = Match(is_wildcard=True)
            flow_match["ethernet_type"] = 0x0800
            self.synthesis.synthesize_all_switches(flow_match, 2)

        self.mininet_obj.pingAll()

        # is_bi_connected = self.is_bi_connected_manual_ping_test_all_hosts()

        # is_bi_connected = self.is_bi_connected_manual_ping_test([(self.mininet_obj.get('h11'), self.mininet_obj.get('h31'))])

        # is_bi_connected = self.is_bi_connected_manual_ping_test([(self.mininet_obj.get('h31'), self.mininet_obj.get('h41'))],
        #                                                            [('s1', 's2')])
        # print "is_bi_connected:", is_bi_connected

    def get_ryu_switches(self):
        ryu_switches = {}
        request_gap = 0

        # Get all the ryu_switches from the inventory API
        remaining_url = 'stats/switches'
        time.sleep(request_gap)
        resp, content = self.h.request(self.baseUrlRyu + remaining_url, "GET")

        ryu_switch_numbers = json.loads(content)

        for dpid in ryu_switch_numbers:

            this_ryu_switch = {}

            # Get the flows
            remaining_url = 'stats/flow' + "/" + str(dpid)
            resp, content = self.h.request(self.baseUrlRyu + remaining_url, "GET")
            time.sleep(request_gap)

            if resp["status"] == "200":
                switch_flows = json.loads(content)
                switch_flow_tables = defaultdict(list)
                for flow_rule in switch_flows[str(dpid)]:
                    switch_flow_tables[flow_rule["table_id"]].append(flow_rule)
                this_ryu_switch["flow_tables"] = switch_flow_tables
            else:
                print "Error pulling switch flows from RYU."

            # Get the ports
            remaining_url = 'stats/portdesc' + "/" + str(dpid)
            resp, content = self.h.request(self.baseUrlRyu + remaining_url, "GET")
            time.sleep(request_gap)

            if resp["status"] == "200":
                switch_ports = json.loads(content)
                this_ryu_switch["ports"] = switch_ports[str(dpid)]
            else:
                print "Error pulling switch ports from RYU."

            # Get the groups
            remaining_url = 'stats/groupdesc' + "/" + str(dpid)
            resp, content = self.h.request(self.baseUrlRyu + remaining_url, "GET")
            time.sleep(request_gap)

            if resp["status"] == "200":
                switch_groups = json.loads(content)
                this_ryu_switch["groups"] = switch_groups[str(dpid)]
            else:
                print "Error pulling switch ports from RYU."

            ryu_switches[dpid] = this_ryu_switch

        with open(self.conf_path + "ryu_switches.json", "w") as outfile:
            json.dump(ryu_switches, outfile)

    def get_host_nodes(self):

        mininet_host_nodes = {}

        for sw in self.topo.switches():
            mininet_host_nodes[sw] = []
            for h in self.get_all_switch_hosts(sw):
                mininet_host_dict = {"host_switch_id": "s" + sw[1:],
                                     "host_name": h.name,
                                     "host_IP": h.IP(),
                                     "host_MAC": h.MAC()}

                mininet_host_nodes[sw].append(mininet_host_dict)

        with open(self.conf_path + "mininet_host_nodes.json", "w") as outfile:
            json.dump(mininet_host_nodes, outfile)

        return mininet_host_nodes

    def get_links(self):

        mininet_port_links = {}

        with open(self.conf_path + "mininet_port_links.json", "w") as outfile:
            json.dump(self.topo.ports, outfile)

        return mininet_port_links

    def get_switches(self):
        # Now the output of synthesis is carted away
        if self.controller == "ryu":
            self.get_ryu_switches()
        else:
            raise NotImplemented

    def setup_network_graph(self, mininet_setup_gap=None, synthesis_setup_gap=None):

        if not self.load_config and self.save_config:
            self.cm = ControllerMan(controller=self.controller)
            self.controller_port = self.cm.start_controller()

            self.start_mininet()
            if mininet_setup_gap:
                time.sleep(mininet_setup_gap)

            # These things are needed by network graph...
            self.get_host_nodes()
            self.get_links()
            self.get_switches()

            self.ng = NetworkGraph(network_configuration=self)
            self.ng.parse_network_graph()

            # Now the synthesis...
            self.trigger_synthesis()
            if synthesis_setup_gap:
                time.sleep(synthesis_setup_gap)

            # Refresh just the switches in the network graph, post synthesis
            self.get_switches()
            self.ng.parse_switches()

        else:
            self.ng = NetworkGraph(network_configuration=self)
            self.ng.parse_network_graph()

        print "total_flow_rules:", self.ng.total_flow_rules

        return self.ng

    def start_mininet(self):

        self.cleanup_mininet()

        self.mininet_obj = Mininet(topo=self.topo,
                           cleanup=True,
                           autoStaticArp=True,
                           controller=lambda name: RemoteController(name, ip='127.0.0.1', port=self.controller_port),
                           switch=partial(OVSSwitch, protocols='OpenFlow14'))

        self.mininet_obj.start()

    def cleanup_mininet(self):

        if self.mininet_obj:
            print "Mininet cleanup..."
            self.mininet_obj.stop()

        os.system("sudo mn -c")

    def get_all_switch_hosts(self, switch_id):

        p = self.topo.ports

        for node in p:

            # Only look for this switch's hosts
            if node != switch_id:
                continue

            for switch_port in p[node]:
                dst_list = p[node][switch_port]
                dst_node = dst_list[0]
                if dst_node.startswith("h"):
                    yield self.mininet_obj.get(dst_node)

    def _get_experiment_host_pair(self):

        for src_switch in self.topo.get_switches_with_hosts():
            for dst_switch in self.topo.get_switches_with_hosts():
                if src_switch == dst_switch:
                    continue

                # Assume one host per switch
                src_host = "h" + src_switch[1:] + "1"
                dst_host = "h" + dst_switch[1:] + "1"

                src_host_node = self.mininet_obj.get(src_host)
                dst_host_node = self.mininet_obj.get(dst_host)

                yield (src_host_node, dst_host_node)

    def is_host_pair_pingable(self, src_host, dst_host):
        hosts = [src_host, dst_host]
        ping_loss_rate = self.mininet_obj.ping(hosts, '1')

        # If some packets get through, then declare pingable
        if ping_loss_rate < 100.0:
            return True
        else:
            # If not, do a double check:
            cmd_output = src_host.cmd("ping -c 3 " + dst_host.IP())
            print cmd_output
            if cmd_output.find("0 received") != -1:
                return False
            else:
                return True

    def are_all_hosts_pingable(self):
        ping_loss_rate = self.mininet_obj.pingAll('1')

        # If some packets get through, then declare pingable
        if ping_loss_rate < 100.0:
            return True
        else:
            return False

    def get_intf_status(self, ifname):

        # set some symbolic constants
        SIOCGIFFLAGS = 0x8913
        null256 = '\0'*256

        # create a socket so we have a handle to query
        s = socket(AF_INET, SOCK_DGRAM)

        # call ioctl() to get the flags for the given interface
        result = fcntl.ioctl(s.fileno(), SIOCGIFFLAGS, ifname + null256)

        # extract the interface's flags from the return value
        flags, = struct.unpack('H', result[16:18])

        # check "UP" bit and print a message
        up = flags & 1

        return ('down', 'up')[up]

    def wait_until_link_status(self, sw_i, sw_j, intended_status):

        num_seconds = 0

        for link in self.mininet_obj.links:
            if (sw_i in link.intf1.name and sw_j in link.intf2.name) or (sw_i in link.intf2.name and sw_j in link.intf1.name):

                while True:
                    status_i = self.get_intf_status(link.intf1.name)
                    status_j = self.get_intf_status(link.intf2.name)

                    if status_i == intended_status and status_j == intended_status:
                        break

                    time.sleep(1)
                    num_seconds +=1

        return num_seconds

    def is_bi_connected_manual_ping_test(self, experiment_host_pairs_to_check, edges_to_try=None):

        is_bi_connected= True

        if not edges_to_try:
            edges_to_try = self.topo.g.edges()

        for edge in edges_to_try:

            # Only try and break switch-switch edges
            if edge[0].startswith("h") or edge[1].startswith("h"):
                continue

            for (src_host, dst_host) in experiment_host_pairs_to_check:

                is_pingable_before_failure = self.is_host_pair_pingable(src_host, dst_host)

                if not is_pingable_before_failure:
                    print "src_host:", src_host, "dst_host:", dst_host, "are not connected."
                    is_bi_connected = False
                    break

                self.mininet_obj.configLinkStatus(edge[0], edge[1], 'down')
                self.wait_until_link_status(edge[0], edge[1], 'down')
                time.sleep(5)
                is_pingable_after_failure = self.is_host_pair_pingable(src_host, dst_host)
                self.mininet_obj.configLinkStatus(edge[0], edge[1], 'up')
                self.wait_until_link_status(edge[0], edge[1], 'up')

                time.sleep(5)
                is_pingable_after_restoration = self.is_host_pair_pingable(src_host, dst_host)

                if not is_pingable_after_failure == True:
                    is_bi_connected = False
                    print "Got a problem with edge:", edge, " for src_host:", src_host, "dst_host:", dst_host
                    break

        return is_bi_connected

    def is_bi_connected_manual_ping_test_all_hosts(self,  edges_to_try=None):

        is_bi_connected= True

        if not edges_to_try:
            edges_to_try = self.topo.g.edges()

        for edge in edges_to_try:

            # Only try and break switch-switch edges
            if edge[0].startswith("h") or edge[1].startswith("h"):
                continue

            is_pingable_before_failure = self.are_all_hosts_pingable()

            if not is_pingable_before_failure:
                is_bi_connected = False
                break

            self.mininet_obj.configLinkStatus(edge[0], edge[1], 'down')
            self.wait_until_link_status(edge[0], edge[1], 'down')
            time.sleep(5)
            is_pingable_after_failure = self.are_all_hosts_pingable()
            self.mininet_obj.configLinkStatus(edge[0], edge[1], 'up')
            self.wait_until_link_status(edge[0], edge[1], 'up')

            time.sleep(5)
            is_pingable_after_restoration = self.are_all_hosts_pingable()

            if not is_pingable_after_failure == True:
                is_bi_connected = False
                break

        return is_bi_connected

    def parse_iperf_output(self, iperf_output_string):
        data_lines =  iperf_output_string.split('\r\n')
        interesting_line_index = None
        for i in xrange(len(data_lines)):
            if data_lines[i].endswith('Server Report:'):
                interesting_line_index = i + 1
        data_tokens =  data_lines[interesting_line_index].split()
        print "Transferred Rate:", data_tokens[7]
        print "Jitter:", data_tokens[9]

    def parse_ping_output(self,ping_output_string):

        data_lines =  ping_output_string.split('\r\n')
        interesting_line_index = None
        for i in xrange(len(data_lines)):
            if data_lines[i].startswith('5 packets transmitted'):
                interesting_line_index = i + 1
        data_tokens =  data_lines[interesting_line_index].split()
        data_tokens =  data_tokens[3].split('/')
        print 'Min Delay:', data_tokens[0]
        print 'Avg Delay:', data_tokens[1]
        print 'Max Delay:', data_tokens[2]

    def parse_netperf_output(self,netperf_output_string):
        data_lines =  netperf_output_string.split('\r\n')

        output_line_tokens =  data_lines[2].split(',')
        print "Throughput:", output_line_tokens[0]
        print 'Mean Latency:', output_line_tokens[1]
        print 'Stddev Latency:', output_line_tokens[2]
        print '99th Latency:', output_line_tokens[3]
        print 'Min Latency:', output_line_tokens[4]
        print 'Max Latency:', output_line_tokens[5]

    def measure_flow_rates(self, last_hop_queue_rate):

        num_traffic_profiles = 10
        size_of_send = [1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024]

        number_of_sends_in_a_burst = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        inter_burst_times = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1]

        # Get all the nodes
        self.h1s1 = self.mininet_obj.getNodeByName("h1s1")
        self.h1s2 = self.mininet_obj.getNodeByName("h1s2")
        self.h2s1 = self.mininet_obj.getNodeByName("h2s1")
        self.h2s2 = self.mininet_obj.getNodeByName("h2s2")

        h1s1_output = self.h1s1.cmd("/usr/local/bin/netserver")
        print h1s1_output

        h2s1_output = self.h2s1.cmd("/usr/local/bin/netserver")
        print h2s1_output

        netperf_output_dict_h1s2 = {}
        netperf_output_dict_h2s2 = {}

        for i in range(num_traffic_profiles):

            netperf_output_dict_h1s2[i] = self.h1s2.cmd("/usr/local/bin/netperf -H " + self.h1s1.IP() +
                                                   " -w " + str(inter_burst_times[i]) +
                                                   " -b " + str(number_of_sends_in_a_burst[i]) +
                                                   " -l 10 " +
                                                   "-t omni -- -d send -o " +
                                                   "'THROUGHPUT, MEAN_LATENCY, STDDEV_LATENCY, P99_LATENCY, MIN_LATENCY, MAX_LATENCY'" +
                                                   " -T UDP_RR " +
                                                   "-m " + str(size_of_send[i]) + " &"
                                                   )

            netperf_output_dict_h2s2[i] = self.h2s2.cmd("/usr/local/bin/netperf -H " + self.h2s1.IP() +
                                                   " -w " + str(inter_burst_times[i]) +
                                                   " -b " + str(number_of_sends_in_a_burst[i]) +
                                                   " -l 10 " +
                                                   "-t omni -- -d send -o " +
                                                   "'THROUGHPUT, MEAN_LATENCY, STDDEV_LATENCY, P99_LATENCY, MIN_LATENCY, MAX_LATENCY'" +
                                                   " -T UDP_RR " +
                                                   "-m " + str(size_of_send[i]) + " &"
                                                   )
            time.sleep(15)

            netperf_output_dict_h1s2[i] = self.h1s2.read()
            netperf_output_dict_h2s2[i] = self.h2s2.read()

            print netperf_output_dict_h1s2[i]
            print netperf_output_dict_h2s2[i]

        # Parse the output for jitter and delay
        print "Last-Hop Queue Rate:", str(last_hop_queue_rate), "M"
        for i in range(num_traffic_profiles):

            print "--"
            print "Size of send (bytes):", size_of_send[i]
            print "Number of sends in a burst:", number_of_sends_in_a_burst[i]
            print "Inter-burst time (miliseconds):", inter_burst_times[i]

            rate = (size_of_send[i] * 8 * number_of_sends_in_a_burst[i]) / (inter_burst_times[i] * 1000.0)
            print "Sending Rate:", str(rate), 'Mbps'

            self.parse_netperf_output(netperf_output_dict_h1s2[i])
            print "--"
            self.parse_netperf_output(netperf_output_dict_h2s2[i])