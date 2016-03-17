__author__ = 'Rakesh Kumar'


import json
import time
import numpy as np
import scipy.stats as ss
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

from pprint import pprint
from controller_man import ControllerMan
from mininet_man import MininetMan
from model.network_graph import NetworkGraph

from synthesis.intent_synthesis import IntentSynthesis
from synthesis.intent_synthesis_ldst import IntentSynthesisLDST
from synthesis.intent_synthesis_load_balance import IntentSynthesisLB

class Experiment(object):

    def __init__(self,
                 experiment_name,
                 num_iterations,
                 load_config,
                 save_config,
                 controller,
                 num_controller_instances):

        self.experiment_tag = experiment_name + "_" + str(num_iterations) + "_iterations_" +time.strftime("%Y%m%d_%H%M%S")

        self.num_iterations = num_iterations
        self.load_config = load_config
        self.save_config = save_config
        self.controller = controller
        self.num_controller_instances = num_controller_instances

        self.data = {}

        self.controller_port = 6633
        self.cm = None
        self.mm = None
        self.ng = None

        if not self.load_config and self.save_config:
            self.cm = ControllerMan(self.num_controller_instances, controller=controller)

    def setup_network_graph(self,
                            topo_description,
                            mininet_setup_gap=None,
                            dst_ports_to_synthesize=None,
                            synthesis_setup_gap=None,
                            synthesis_scheme=None):

        if not self.load_config and self.save_config:
            self.controller_port = self.cm.get_next()

        self.mm = MininetMan(synthesis_scheme, self.controller_port, *topo_description)

        if not self.load_config and self.save_config:
            self.mm.start_mininet()

            if mininet_setup_gap:
                time.sleep(mininet_setup_gap)

        # Get a flow validator instance
        self.ng = NetworkGraph(mm=self.mm,
                          controller=self.controller,
                          load_config=self.load_config,
                          save_config=self.save_config)

        if not self.load_config and self.save_config:
            if self.controller == "odl":
                self.mm.setup_mininet_with_odl(self.ng)
            elif self.controller == "ryu":
                if synthesis_scheme == "IntentSynthesis":
                    self.synthesis = IntentSynthesis(self.ng, master_switch=topo_description[0] == "linear",
                                                     synthesized_paths_save_directory=self.ng.config_path_prefix)

                    self.synthesis.synthesize_all_node_pairs(dst_ports_to_synthesize)

                elif synthesis_scheme == "IntentSynthesisLDST":
                    self.synthesis = IntentSynthesisLDST(self.ng, master_switch=topo_description[0] == "linear")
                    self.synthesis.synthesize_all_node_pairs(dst_ports_to_synthesize)

                elif synthesis_scheme == "IntentSynthesisLB":
                    self.synthesis = IntentSynthesisLB(self.ng, master_switch=topo_description[0] == "linear")
                    self.synthesis.synthesize_all_node_pairs(dst_ports_to_synthesize)

                elif synthesis_scheme == "QoS_Synthesis":
                    #self.mm.qos_setup_single_flow_test(ng)

                    self.mm.qos_setup_two_flows_on_separate_queues_to_two_different_hosts(self.ng,
                                                                                          same_output_queue=False)
                    #self.mm.qos_setup_two_flows_on_separate_queues_to_same_host(self.ng)



                self.mm.net.pingAll()
                #is_bi_connected = self.mm.is_bi_connected_manual_ping_test()

                # is_bi_connected = self.mm.is_bi_connected_manual_ping_test([(self.mm.net.get('h31'),
                #                                                             self.mm.net.get('h21'))],
                #                                                            [('s3', 's2')])

                #print "is_bi_connected:", is_bi_connected

                if synthesis_setup_gap:
                    time.sleep(synthesis_setup_gap)

        # Refresh the network_graph
        self.ng.parse_switches()

        # import sys
        # sys.exit()

        return self.ng

    def compare_paths(self, src_host, dst_host, analyzed_path, synthesized_path, synthesized_path_vuln_rank, verbose):

        analyzed_path_vuln_rank = analyzed_path.max_vuln_rank
        path_matches = True

        if analyzed_path.get_len() == len(synthesized_path):
            i = 0
            for path_node in analyzed_path:
                if path_node.node_id != synthesized_path[i]:
                    path_matches = False
                    break
                i += 1
        else:
            path_matches = False

        if path_matches:

            if analyzed_path_vuln_rank != synthesized_path_vuln_rank:
                path_matches = False

                print "Path vulnerability ranks do not match. src_host:", src_host, "dst_host:", dst_host, \
                    "analyzed_path_vuln_rank:", analyzed_path_vuln_rank, \
                    "synthesized_path_vuln_rank:", synthesized_path_vuln_rank

        return path_matches

    def compare_host_pair_paths_with_synthesis(self, analyzed_host_pairs_traffic_paths, failed_edge=None, verbose=False):

        all_paths_match = True

        synthesized_primary_paths = None

        if not self.load_config and self.save_config:
            synthesized_primary_paths = self.synthesis.synthesis_lib.synthesized_primary_paths
            synthesized_failover_paths = self.synthesis.synthesis_lib.synthesized_failover_paths
        else:
            with open(self.ng.config_path_prefix + "synthesized_primary_paths.json", "r") as in_file:
                synthesized_primary_paths = json.loads(in_file.read())

            with open(self.ng.config_path_prefix + "synthesized_failover_paths.json", "r") as in_file:
                synthesized_failover_paths = json.loads(in_file.read())

        for src_host in analyzed_host_pairs_traffic_paths:
            for dst_host in analyzed_host_pairs_traffic_paths[src_host]:

                synthesized_path = None
                synthesized_path_vuln_rank = None

                # If an edge has not been failed, then refer to synthesized paths.
                # If an edge has been failed, first check both permutation of edge switches, if neither is found,
                # then refer to primary path by assuming that the given edge did not participate in the failover of
                # the given host pair.

                if failed_edge:
                    try:
                        synthesized_path = synthesized_failover_paths[src_host][dst_host][failed_edge[0]][failed_edge[1]]
                        synthesized_path_vuln_rank = 1
                    except:
                        try:
                            synthesized_path = synthesized_failover_paths[src_host][dst_host][failed_edge[1]][failed_edge[0]]
                            synthesized_path_vuln_rank = 1
                        except:
                            synthesized_path = synthesized_primary_paths[src_host][dst_host]
                            synthesized_path_vuln_rank = 0
                else:
                     synthesized_path = synthesized_primary_paths[src_host][dst_host]
                     synthesized_path_vuln_rank = 0

                # Need to find at least one matching path
                for analyzed_path in analyzed_host_pairs_traffic_paths[src_host][dst_host]:
                    path_matches = self.compare_paths(src_host, dst_host, analyzed_path, synthesized_path, synthesized_path_vuln_rank, verbose)

                    if path_matches:
                        break

                if not path_matches:
                    print "No analyzed path matched for:", synthesized_path
                    all_paths_match = False

        return all_paths_match

    def compare_failover_host_pair_paths_with_synthesis(self, fv, edges_to_try=None, verbose=False):

        all_paths_match = False

        if not edges_to_try:
            edges_to_try = fv.network_graph.graph.edges()

        for edge in edges_to_try:

            # Ignore host edges
            if edge[0].startswith("h") or edge[1].startswith("h"):
                continue

            print "Breaking edge:", edge

            fv.port_graph.remove_node_graph_link(edge[0], edge[1])

            analyzed_host_pairs_path_info = fv.get_all_host_pairs_traffic_paths()

            all_paths_match = self.compare_host_pair_paths_with_synthesis(analyzed_host_pairs_path_info,
                                                                          verbose=verbose,
                                                                          failed_edge=edge)

            if not all_paths_match:
                break

            print "Restoring edge:", edge

            fv.port_graph.add_node_graph_link(edge[0], edge[1], updating=True)

        return all_paths_match

    def dump_data(self):
        pprint(self.data)
        filename = "data/" + self.experiment_tag + ".json"
        print "Writing to file:", filename

        with open(filename, "w") as outfile:
            json.dump(self.data, outfile)

    def load_data(self, filename):

        print "Reading file:", filename

        with open(filename, "r") as infile:
            self.data = json.load(infile)

    def prepare_matplotlib_data(self, data_dict):

        x = sorted(data_dict.keys())

        data_means = []
        data_sems = []

        for p in x:
            mean = np.mean(data_dict[p])
            sem = ss.sem(data_dict[p])
            data_means.append(mean)
            data_sems.append(sem)

        return x, data_means, data_sems

    def get_data_min_max(self, data_dict):

        data_min = None
        data_max = None

        for p in data_dict:
            p_min = min(data_dict[p])

            if data_min:
                if p_min < data_min:
                    data_min = p_min
            else:
                data_min = p_min

            p_max = max(data_dict[p])
            if data_max:
                if p_max > data_max:
                    data_max = p_max
            else:
                data_max = p_max

        return data_min, data_max

    def plot_line_error_bars(self, data_key, x_label, y_label, y_scale='log', line_label="Ports Synthesized: ",
                             xmax_factor=1.05, xmin_factor=1.0, y_max_factor = 1.2, legend_loc='upper left',
                             xticks=None, xtick_labels=None, line_label_suffixes=None):

        markers = ['o', 'v', '^', '*', 'd']
        marker_i = 0

        x_min = None
        x_max = None

        y_min = None
        y_max = None

        data_vals = self.data[data_key]

        for number_of_ports_to_synthesize in data_vals:

            per_num_host_data = self.data[data_key][number_of_ports_to_synthesize]
            per_num_host_data = d = {int(k):v for k,v in per_num_host_data.items()}

            d_min, d_max =  self.get_data_min_max(per_num_host_data)
            if y_min:
                if d_min < y_min:
                    y_min = d_min
            else:
                y_min = d_min

            if y_max:
                if d_max > y_max:
                    y_max = d_max
            else:
                y_max = d_max

            x, mean, sem = self.prepare_matplotlib_data(per_num_host_data)

            d_min, d_max = min(map(int, x)), max(map(int, x))

            if x_min:
                if d_min < x_min:
                    x_min = d_min
            else:
                x_min = d_min

            if x_max:
                if d_max > x_max:
                    x_max = d_max
            else:
                x_max = d_max

            if line_label_suffixes:
                l = plt.errorbar(x, mean, sem, color="black", marker=markers[marker_i], markersize=8.0,
                                 label=line_label + line_label_suffixes[marker_i])
            else:
                l = plt.errorbar(x, mean, sem, color="black", marker=markers[marker_i], markersize=8.0,
                                 label=line_label + str(number_of_ports_to_synthesize))

            marker_i += 1

        low_xlim, high_xlim = plt.xlim()
        plt.xlim(xmax=(high_xlim) * xmax_factor)
        plt.xlim(xmin=(low_xlim) * xmin_factor)

        if y_scale == "linear":
            low_ylim, high_ylim = plt.ylim()
            plt.ylim(ymax=(high_ylim) * y_max_factor)

        plt.yscale(y_scale)
        plt.xlabel(x_label, fontsize=18)
        plt.ylabel(y_label, fontsize=18)

        ax = plt.axes()
        xa = ax.get_xaxis()
        xa.set_major_locator(MaxNLocator(integer=True))

        if xticks:
            ax.set_xticks(xticks)

        if xtick_labels:
            ax.set_xticklabels(xtick_labels)

        legend = plt.legend(loc=legend_loc, shadow=True, fontsize=12)

        plt.savefig("plots/" + self.experiment_tag + "_" + data_key + ".png")
        plt.show()

    def plot_bar_error_bars(self, data_key, x_label, y_label):

        x, edges_broken_mean, edges_broken_sem = self.prepare_matplotlib_data(self.data[data_key])
        ind = np.arange(len(x))
        width = 0.3

        plt.bar(ind + width, edges_broken_mean, yerr=edges_broken_sem, color="0.90", align='center',
                error_kw=dict(ecolor='gray', lw=2, capsize=5, capthick=2))

        plt.xticks(ind + width, tuple(x))
        plt.xlabel(x_label, fontsize=18)
        plt.ylabel(y_label, fontsize=18)
        plt.savefig("plots/" + self.experiment_tag + "_" + data_key + ".png")
        plt.show()