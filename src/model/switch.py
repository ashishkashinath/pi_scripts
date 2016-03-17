__author__ = 'Rakesh Kumar'

import networkx as nx

from collections import defaultdict

class Switch():

    def __init__(self, sw_id, network_graph):

        self.g = nx.DiGraph()
        self.node_id = sw_id
        self.network_graph = network_graph
        self.flow_tables = []
        self.group_table = None
        self.ports = None
        self.host_ports = []

        # Synthesis stuff
        self.intents = defaultdict(dict)
        try:
            self.synthesis_tag = int(self.node_id[1:])
        except ValueError:
            self.synthesis_tag = self.node_id
