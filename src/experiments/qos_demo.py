__author__ = 'Rakesh Kumar'

import sys
import time
from collections import defaultdict

sys.path.append("./")

from controller_man import ControllerMan
from experiment import Experiment
from network_configuration import NetworkConfiguration
from flow_specification import FlowSpecification
from model.match import Match


class QosDemo(Experiment):

    def __init__(self,
                 num_iterations,
                 flow_specs,
                 network_configurations):

        super(QosDemo, self).__init__("number_of_hosts", num_iterations)
        self.flow_specs = flow_specs
        self.network_configurations = network_configurations

        self.cm = ControllerMan(controller="ryu")
        self.cm.stop_controller()
        time.sleep(5)
        self.controller_port = self.cm.start_controller()

        self.data = {
            "Throughput": defaultdict(defaultdict),
            "99th Percentile Latency": defaultdict(defaultdict),
            "Maximum Latency": defaultdict(defaultdict)
        }

    def populate_data(self):
        for nc in self.network_configurations:
            print "network_configuration:", nc

            for i in range(len(self.flow_rates)):

                self.data["Throughput"][nc.topo_params["num_hosts_per_switch"]][self.flow_rates[i]] = []
                self.data["99th Percentile Latency"][nc.topo_params["num_hosts_per_switch"]][self.flow_rates[i]] = []
                self.data["Maximum Latency"][nc.topo_params["num_hosts_per_switch"]][self.flow_rates[i]] = []

        print self.data

    def plot_data(self):
        pass

    def trigger(self):

        for i in range(self.num_iterations):

            print "iteration:", i + 1

            for nc in self.network_configurations:
                print "network_configuration:", nc

                nc.setup_network_graph(mininet_setup_gap=1, synthesis_setup_gap=1)

                nc.init_flow_specs(self.flow_specs)

                nc.synthesis.synthesize_flow_specifications(self.flow_specs)
                self.measure_flow_rates(nc)

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

        data_lines = ping_output_string.split('\r\n')
        interesting_line_index = None
        for i in xrange(len(data_lines)):
            if data_lines[i].startswith('5 packets transmitted'):
                interesting_line_index = i + 1
        data_tokens =  data_lines[interesting_line_index].split()
        data_tokens =  data_tokens[3].split('/')
        print 'Min Delay:', data_tokens[0]
        print 'Avg Delay:', data_tokens[1]
        print 'Max Delay:', data_tokens[2]

    def measure_flow_rates(self, nc):

        fs = None

        for fs in self.flow_specs:
            fs.mn_dst_host.cmd("/usr/local/bin/netserver")
            time.sleep(5)
            fs.mn_src_host.cmd(fs.construct_netperf_cmd_str())

            time.sleep(fs.tests_duration + 5)
            fs.store_measurements(fs.mn_src_host.read())

        # Sleep for 5 seconds more than flow duration to make sure netperf has finished.
        time.sleep(fs.tests_duration + 5)

        for fs in self.flow_specs:
            fs.store_measurements(fs.mn_src_host.read())

        print "here"


def prepare_network_configurations(num_hosts_per_switch_list, same_output_queue_list):
    nc_list = []

    for same_output_queue in same_output_queue_list:

        for hps in num_hosts_per_switch_list:

            nc = NetworkConfiguration("ryu",
                                      "linear",
                                      {"num_switches": 2,
                                       "num_hosts_per_switch": hps},
                                      conf_root="configurations/",
                                      synthesis_name="SynthesizeQoS",
                                      synthesis_params={"same_output_queue": same_output_queue})

            nc_list.append(nc)

    return nc_list


def prepare_flow_specifications(measurement_rates, tests_duration):

    flow_specs = []

    flow_match = Match(is_wildcard=True)
    flow_match["ethernet_type"] = 0x0800

    h1s2_to_h1s1_flow_measurement = FlowSpecification("h1s2", "h1s1", 50, flow_match, measurement_rates, tests_duration)
    h2s2_to_h2s1_flow_measurement = FlowSpecification("h2s2", "h2s1", 50, flow_match, measurement_rates, tests_duration)

    flow_specs.append(h1s2_to_h1s1_flow_measurement)
    flow_specs.append(h2s2_to_h2s1_flow_measurement)

    return flow_specs


def main():

    num_iterations = 2

    tests_duration = 5
    measurement_rates = [40, 45, 50]
    flow_specs = prepare_flow_specifications(measurement_rates, tests_duration)

    num_hosts_per_switch_list = [2]
    same_output_queue_list = [False, True]
    network_configurations = prepare_network_configurations(num_hosts_per_switch_list, same_output_queue_list)

    exp = QosDemo(num_iterations, flow_specs, network_configurations)

    exp.trigger()
    exp.populate_data()
    exp.plot_data()

if __name__ == "__main__":
    main()