__author__ = 'Rakesh Kumar'

import networkx as nx

from collections import defaultdict
from copy import deepcopy

from synthesis.synthesis_lib import SynthesisLib
from model.intent import Intent
from model.match import Match

class IntentSynthesisLB():

    def __init__(self, network_graph, master_switch=False):

        self.network_graph = network_graph
        self.master_switch = master_switch

        self.synthesis_lib = SynthesisLib("localhost", "8181", self.network_graph)

        # s represents the set of all switches that are
        # affected as a result of flow synthesis
        self.s = set()

        self.primary_path_edges = []
        self.primary_path_edge_dict = {}

        self.apply_tag_intents_immediately = True
        self.apply_other_intents_immediately = False

        # Table contains the rules that drop packets destined to the same MAC address as host of origin
        self.local_host_rule_table = 0

        # Table contains the reverse rules (they should be examined first)
        self.reverse_rules_table_id = 1

        # Table contains any rules associated with forwarding host traffic
        self.mac_forwarding_table_id = 2

        # Table contains the actual forwarding rules
        self.ip_forwarding_table_id = 3

        self.next_path_index = {}
        self.all_switch_paths = {}

    def get_intents(self, dst_intents, intent_type):

        return_intent = []

        for intent in dst_intents:
            if intent.intent_type == intent_type:
                return_intent.append(intent)

        return return_intent

    def _identify_reverse_and_balking_intents(self):

        for sw in self.s:

            intents = self.network_graph.graph.node[sw]["sw"].intents

            for dst in intents:
                dst_intents = intents[dst]

                h41 = self.network_graph.get_node_object('h41')
                h21 = self.network_graph.get_node_object('h21')

                primary_intents = self.get_intents(dst_intents, "primary")

                for intent in dst_intents:

                    #  Nothing needs to be done for primary intent
                    if intent in primary_intents:
                        continue

                    # A balking intent happens on the switch where reversal begins,
                    # it is characterized by the fact that the traffic exits the same port where it came from
                    if intent.in_port == intent.out_port:

                        # Add a new intent with modified key
                        intent.intent_type = "balking"
                        continue

                # Identifying reverse intents separately out of remaining failover intents
                reverse_candidate_intents = self.get_intents(dst_intents, "failover")

                for primary_intent in primary_intents:
                    for reverse_candidate_intent in reverse_candidate_intents:

                        #  If this intent is at a reverse flow carrier switch

                        #  There are two ways to identify reverse intents
                        #  1. at the source switch, with intent's source port equal to destination port of the primary intent
                        if reverse_candidate_intent.in_port == primary_intent.out_port:
                            reverse_candidate_intent.intent_type = "reverse"
                            continue

                        #  2. At any other switch
                        # with intent's destination port equal to source port of primary intent
                        if reverse_candidate_intent.out_port == primary_intent.in_port:
                            reverse_candidate_intent.intent_type = "reverse"
                            continue

    def _add_intent(self, switch_id, key, intent):

        self.s.add(switch_id)
        intents = self.network_graph.graph.node[switch_id]["sw"].intents

        if key in intents:
            intents[key][intent] += 1
        else:
            intents[key] = defaultdict(int)
            intents[key][intent] = 1

    def _compute_destination_host_mac_intents(self, h_obj, flow_match, matching_tag):

        edge_ports_dict = self.network_graph.get_link_ports_dict(h_obj.switch_id, h_obj.node_id)
        out_port = edge_ports_dict[h_obj.switch_id]

        host_mac_match = deepcopy(flow_match)
        mac_int = int(h_obj.mac_addr.replace(":", ""), 16)
        host_mac_match["ethernet_destination"] = int(mac_int)

        host_mac_intent = Intent("mac", host_mac_match, "all", out_port, apply_immediately=False)

        # Avoiding addition of multiple mac forwarding intents for the same host 
        # by using its mac address as the key
        self._add_intent(h_obj.switch_id, h_obj.mac_addr, host_mac_intent)

    def _compute_path_intents(self, p, intent_type, flow_match, first_in_port, src_host_mac, dst_host_mac):

        edge_ports_dict = self.network_graph.get_link_ports_dict(p[0], p[1])

        in_port = first_in_port
        out_port = edge_ports_dict[p[0]]

        # This loop always starts at a switch
        for i in xrange(len(p) - 1):

            fwd_flow_match = deepcopy(flow_match)
            src_mac_int = int(src_host_mac.replace(":", ""), 16)
            fwd_flow_match["ethernet_source"] = src_mac_int
            dst_mac_int = int(dst_host_mac.replace(":", ""), 16)
            fwd_flow_match["ethernet_destination"] = dst_mac_int

            intent = Intent(intent_type, fwd_flow_match, in_port, out_port)

            # Using dst_host_mac as key here to
            # avoid adding multiple intents for the same destination

            self._add_intent(p[i], (src_host_mac, dst_host_mac), intent)

            # Prep for next switch
            if i < len(p) - 2:
                edge_ports_dict = self.network_graph.get_link_ports_dict(p[i], p[i + 1])
                in_port = edge_ports_dict[p[i+1]]

                edge_ports_dict = self.network_graph.get_link_ports_dict(p[i + 1], p[i + 2])
                out_port = edge_ports_dict[p[i+1]]

    def synthesize_flow(self, src_host, dst_host, flow_match, primary_path):

        print "Primary Path:", primary_path

        # Handy info
        edge_ports_dict = self.network_graph.get_link_ports_dict(src_host.node_id, src_host.switch_id)
        in_port = edge_ports_dict[src_host.switch_id]

        # Add a MAC based forwarding rule for the destination host at the last hop
        self._compute_destination_host_mac_intents(dst_host, flow_match, dst_host.mac_addr)

        self.primary_path_edge_dict[(src_host.node_id, dst_host.node_id)] = []

        for i in xrange(len(primary_path)-1):

            if (primary_path[i], primary_path[i+1]) not in self.primary_path_edges and (primary_path[i+1], primary_path[i]) not in self.primary_path_edges:
                self.primary_path_edges.append((primary_path[i], primary_path[i+1]))

            self.primary_path_edge_dict[(src_host.node_id, dst_host.node_id)].append((primary_path[i], primary_path[i+1]))

        #  Compute all forwarding intents as a result of primary path
        self._compute_path_intents(primary_path, "primary", flow_match, in_port, src_host.mac_addr, dst_host.mac_addr)

        #  Along the shortest path, break a link one-by-one
        #  and accumulate desired action buckets in the resulting path

        #  Go through the path, one edge at a time
        for i in xrange(len(primary_path) - 1):

            # Keep a copy of this handy
            edge_ports_dict = self.network_graph.get_link_ports_dict(primary_path[i], primary_path[i + 1])

            # Delete the edge
            self.network_graph.graph.remove_edge(primary_path[i], primary_path[i + 1])

            # Find the shortest path that results when the link breaks
            # and compute forwarding intents for that
            try:
                backup_path = nx.shortest_path(self.network_graph.graph,
                                               source=primary_path[i],
                                               target=dst_host.switch_id)

                print "Backup Path:", backup_path

                self._compute_path_intents(backup_path, "failover", flow_match, in_port, src_host.mac_addr, dst_host.mac_addr)

            except nx.exception.NetworkXNoPath:
                print "No backup path between:", primary_path[i], "to:", dst_host.switch_id

            # Add the edge back and the data that goes along with it
            self.network_graph.graph.add_link(primary_path[i],
                                              primary_path[i + 1],
                                              edge_ports_dict=edge_ports_dict)

            in_port = edge_ports_dict[primary_path[i+1]]

    def _push_balking_intents(self, sw, primary_intents, balking_intents):

        all_primary_intents = set(primary_intents)
        used_primary_intents = set()
        remaining_primary_intents = set()

        for balking_intent in balking_intents:
            corresponding_primary_intent = None
            for primary_intent in primary_intents:

                if balking_intent.in_port == primary_intent.in_port:
                    corresponding_primary_intent = primary_intent
                    break

            if corresponding_primary_intent:

                used_primary_intents.add(corresponding_primary_intent)

                group_id = self.synthesis_lib.push_fast_failover_group(sw,
                                                                       corresponding_primary_intent,
                                                                       balking_intent)

                corresponding_primary_intent.flow_match["in_port"] = int(corresponding_primary_intent.in_port)
                flow = self.synthesis_lib.push_match_per_in_port_destination_instruct_group_flow(
                    sw,
                    self.ip_forwarding_table_id,
                    group_id,
                    1,
                    corresponding_primary_intent.flow_match,
                    corresponding_primary_intent.apply_immediately)

            else:
                group_id = self.synthesis_lib.push_select_all_group(sw, [balking_intent])
                balking_intent.flow_match["in_port"] = int(balking_intent.in_port)

                flow = self.synthesis_lib.push_match_per_in_port_destination_instruct_group_flow(
                    sw,
                    self.ip_forwarding_table_id,
                    group_id,
                    1,
                    balking_intent.flow_match,
                    balking_intent.apply_immediately)

        remaining_primary_intents = all_primary_intents.difference(used_primary_intents)
        return list(remaining_primary_intents)

    def push_switch_changes(self):

        for sw in self.s:

            print "-- Pushing at Switch:", sw

            # Push table miss entries at all Tables
            self.synthesis_lib.push_table_miss_goto_next_table_flow(sw, 0)
            self.synthesis_lib.push_table_miss_goto_next_table_flow(sw, 1)
            self.synthesis_lib.push_table_miss_goto_next_table_flow(sw, 2)

            intents = self.network_graph.graph.node[sw]["sw"].intents

            self.network_graph.graph.node[sw]["sw"].intents = defaultdict(dict)

            for dst in intents:

                dst_intents = intents[dst]

                # Take care of mac intents for this destination
                self.synthesis_lib.push_destination_host_mac_intents(sw, dst_intents,
                                                                     self.get_intents(dst_intents, "mac"),
                                                                     self.mac_forwarding_table_id,
                                                                     pop_vlan=False)

                primary_intents = self.get_intents(dst_intents, "primary")
                reverse_intents = self.get_intents(dst_intents, "reverse")
                balking_intents = self.get_intents(dst_intents, "balking")
                failover_intents = self.get_intents(dst_intents, "failover")

                #  Handle the case when the switch does not have to carry any failover traffic
                if primary_intents:

                    remaining_primary_intents = primary_intents
                    if balking_intents:
                        remaining_primary_intents = self._push_balking_intents(sw, primary_intents, balking_intents)

                    if not failover_intents:
                        in_ports_covered = []
                        for pi in remaining_primary_intents:
                            if pi.in_port not in in_ports_covered:
                                in_ports_covered.append(pi.in_port)

                                group_id = self.synthesis_lib.push_select_all_group(sw, [pi])

                                if not self.master_switch:
                                    pi.flow_match["in_port"] = int(pi.in_port)

                                flow = self.synthesis_lib.push_match_per_in_port_destination_instruct_group_flow(
                                    sw,
                                    self.ip_forwarding_table_id,
                                    group_id,
                                    1,
                                    pi.flow_match,
                                    pi.apply_immediately)

                if primary_intents and failover_intents:

                    # TODO: This leaves out the case when there is a primary intent for which failover
                    # intent cannot be found and might need to be handled separately

                    # Find intents to consolidate, they should have same in_port and different out_port
                    consolidated_failover_intents = []
                    handled_separately_intents = []

                    for failover_intent in failover_intents:
                        consolidation_found = False

                        for primary_intent in primary_intents:
                            if (primary_intent.in_port == failover_intent.in_port and
                                        primary_intent.out_port != failover_intent.out_port):
                                consolidation_found = True

                        if consolidation_found:
                            already_exists = [(x,y) for x, y in consolidated_failover_intents
                                              if x.in_port == primary_intent.in_port
                                              and x.out_port == primary_intent.out_port
                                              and y.out_port == failover_intent.out_port
                                              and y.out_port == failover_intent.out_port]
                            if not already_exists:
                                consolidated_failover_intents.append((primary_intent, failover_intent))
                        else:
                            handled_separately_intents.append(failover_intent)

                    for primary_intent, failover_intent in consolidated_failover_intents:
                        group_id = self.synthesis_lib.push_fast_failover_group(sw, primary_intent, failover_intent)

                        flow = self.synthesis_lib.push_match_per_in_port_destination_instruct_group_flow(
                            sw,
                            self.ip_forwarding_table_id,
                            group_id,
                            1,
                            primary_intent.flow_match,
                            primary_intent.apply_immediately)

                    for separate_intent in handled_separately_intents:
                        group_id = self.synthesis_lib.push_select_all_group(sw, [separate_intent])

                        separate_intent.flow_match["in_port"] = int(separate_intent.in_port)

                        flow = self.synthesis_lib.push_match_per_in_port_destination_instruct_group_flow(
                            sw,
                            self.ip_forwarding_table_id,
                            group_id,
                            1,
                            separate_intent.flow_match,
                            separate_intent.apply_immediately)

                #  Handle the case when switch only participates in carrying the failover traffic in-transit
                if not primary_intents and failover_intents:

                    for failover_intent in failover_intents:

                        group_id = self.synthesis_lib.push_select_all_group(sw, [failover_intent])
                        failover_intent.flow_match["in_port"] = int(failover_intent.in_port)
                        flow = self.synthesis_lib.push_match_per_in_port_destination_instruct_group_flow(
                            sw,
                            self.ip_forwarding_table_id,
                            group_id,
                            1,
                            failover_intent.flow_match,
                            failover_intent.apply_immediately)

                if reverse_intents:

                    group_id = self.synthesis_lib.push_select_all_group(sw, [reverse_intents[0]])
                    reverse_intents[0].flow_match["in_port"] = int(reverse_intents[0].in_port)

                    flow = self.synthesis_lib.push_match_per_in_port_destination_instruct_group_flow(
                        sw,
                        self.reverse_rules_table_id,
                        group_id,
                        1,
                        reverse_intents[0].flow_match,
                        reverse_intents[0].apply_immediately)

    def _get_path(self, src_host, dst_host):

        if (src_host.switch_id, dst_host.switch_id) in self.next_path_index:
            self.next_path_index[(src_host.switch_id, dst_host.switch_id)] += 1
        else:
            self.all_switch_paths[(src_host.switch_id, dst_host.switch_id)] = \
                list(nx.all_simple_paths(self.network_graph.graph,
                                         source=src_host.switch_id,
                                         target=dst_host.switch_id))

            self.next_path_index[(src_host.switch_id, dst_host.switch_id)] = 0

        switch_paths = self.all_switch_paths[(src_host.switch_id, dst_host.switch_id)]
        return switch_paths[(self.next_path_index[(src_host.switch_id, dst_host.switch_id)]) % len(switch_paths)]

    def _synthesize_all_node_pairs(self, dst_port=None):

        print "Synthesizing backup paths between all possible host pairs..."

        for src in self.network_graph.host_ids:
            for dst in self.network_graph.host_ids:

                # Ignore paths with same src/dst
                if src == dst:
                    continue

                src_host = self.network_graph.get_node_object(src)
                dst_host = self.network_graph.get_node_object(dst)

                # Ignore installation of paths between switches on the same switch
                if src_host.switch_id == dst_host.switch_id:
                    continue

                print "-----------------------------------------------------------------------------------------------"
                print 'Synthesizing primary and backup paths from', src, 'to', dst
                print "-----------------------------------------------------------------------------------------------"

                flow_match = Match(is_wildcard=True)
                flow_match["ethernet_type"] = 0x0800

                if dst_port:
                    flow_match["ip_protocol"] = 6
                    flow_match["tcp_destination_port"] = dst_port

                self.synthesize_flow(src_host, dst_host, flow_match, self._get_path(src_host, dst_host))
                print "-----------------------------------------------------------------------------------------------"

        self._identify_reverse_and_balking_intents()
        self.push_switch_changes()

    def synthesize_all_node_pairs(self, dst_ports_to_synthesize=None):

        if not dst_ports_to_synthesize:
            self._synthesize_all_node_pairs()
        else:
            for dst_port in dst_ports_to_synthesize:
                self._synthesize_all_node_pairs(dst_port)