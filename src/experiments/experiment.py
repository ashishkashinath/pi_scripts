import json
import time
import random
import math
import numpy as np
import scipy.stats as ss
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
from pprint import pprint
from timer import Timer

__author__ = 'Rakesh Kumar'


class Experiment(object):

    def __init__(self,
                 experiment_name,
                 num_iterations):

        self.experiment_tag = experiment_name + "_" + str(num_iterations) + "_iterations_" + time.strftime("%Y%m%d_%H%M%S")
        self.num_iterations = num_iterations

        self.data = {}

    def perform_incremental_times_experiment(self, fv, link_fraction_to_sample):

        all_links = list(fv.network_graph.get_switch_link_data())
        num_links_to_sample = int(math.ceil(len(all_links) * link_fraction_to_sample))

        incremental_times = []

        for i in range(num_links_to_sample):

            sampled_ld = random.choice(all_links)

            print "Failing:", sampled_ld
            with Timer(verbose=True) as t:
                fv.port_graph.remove_node_graph_link(sampled_ld.forward_link[0], sampled_ld.forward_link[1])
            incremental_times.append(t.secs)
            print incremental_times

            print "Restoring:", sampled_ld
            with Timer(verbose=True) as t:
                fv.port_graph.add_node_graph_link(sampled_ld.forward_link[0], sampled_ld.forward_link[1], updating=True)
            incremental_times.append(t.secs)
            print incremental_times

        return np.mean(incremental_times)

    def perform_policy_validation_experiment(self, fv):

        src_zone = [fv.network_graph.get_node_object(h_id).switch_port for h_id in fv.network_graph.host_ids]
        dst_zone = [fv.network_graph.get_node_object(h_id).switch_port for h_id in fv.network_graph.host_ids]

        traffic = Traffic(init_wildcard=True)
        traffic.set_field("ethernet_type", 0x0800)
        k = 1
        l = 12
        el = [random.choice(list(fv.network_graph.get_switch_link_data()))]

        with Timer(verbose=True) as t:
            validation_result = fv.validate_zone_pair_connectivity_path_length_link_exclusivity(src_zone,
                                                                                                dst_zone,
                                                                                                traffic,
                                                                                                l, el, k)
        # Return overall validation time, and incremental times [3] in validation results
        return t.secs, validation_result

    def dump_data(self):
        print "Dumping data:"
        pprint(self.data)
        filename = "data/" + self.experiment_tag + ".json"
        print "Writing to file:", filename

        with open(filename, "w") as outfile:
            json.dump(self.data, outfile)

    def load_data(self, filename):

        print "Reading file:", filename

        with open(filename, "r") as infile:
            self.data = json.load(infile)

        pprint(self.data)

        return self.data

    def prepare_matplotlib_data(self, data_dict):

        x = sorted(data_dict.keys(), key=int)

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

    def plot_lines_with_error_bars(self,
                                   ax,
                                   data_key,
                                   x_label,
                                   y_label,
                                   subplot_title,
                                   y_scale,
                                   x_min_factor=1.0,
                                   x_max_factor=1.05,
                                   y_min_factor=0.1,
                                   y_max_factor=1.5,
                                   xticks=None,
                                   xtick_labels=None,
                                   yticks=None,
                                   ytick_labels=None):

        ax.set_xlabel(x_label, fontsize=10, labelpad=-0)
        ax.set_ylabel(y_label, fontsize=10, labelpad=0)
        ax.set_title(subplot_title, fontsize=10)

        markers = ['.', '*', 'o', 'v', '.', 'd', '+', '^', '+', ',', 's', 'o', 'h', '*']
        marker_i = 0

        for line_data_key in self.data[data_key]:

            data_vals = self.data[data_key][line_data_key]

            x, mean, sem = self.prepare_matplotlib_data(data_vals)

            ax.errorbar(x, mean, sem, color="black", marker=markers[marker_i], markersize=6.0, label=line_data_key, ls='none')

            marker_i += 1

        ax.tick_params(axis='x', labelsize=8)
        ax.tick_params(axis='y', labelsize=8)

        low_xlim, high_xlim = ax.get_xlim()
        ax.set_xlim(xmax=(high_xlim) * x_max_factor)
        ax.set_xlim(xmin=(low_xlim) * x_min_factor)

        if y_scale == "linear":
            low_ylim, high_ylim = ax.get_ylim()
            ax.set_ylim(ymin=low_ylim*y_min_factor)
            ax.set_ylim(ymax=high_ylim*y_max_factor)
        elif y_scale == "log":
            ax.set_ylim(ymin=1)
            ax.set_ylim(ymax=100000)

        ax.set_yscale(y_scale)

        xa = ax.get_xaxis()
        xa.set_major_locator(MaxNLocator(integer=True))

        if xticks:
            ax.set_xticks(xticks)

        if xtick_labels:
            ax.set_xticklabels(xtick_labels)

        if yticks:
            ax.set_yticks(yticks)

        if ytick_labels:
            ax.set_yticklabels(ytick_labels)
