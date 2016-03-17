__author__ = 'Rakesh Kumar'

class Port():

    def __init__(self, sw, port_json):

        self.sw = sw
        self.port_id = None
        self.curr_speed = None
        self.max_speed = None

        self.mac_address = None
        self.port_number = None
        self.state = None

        if self.sw.network_graph.controller == "odl":
            self.parse_odl_port_json(port_json)

        elif self.sw.network_graph.controller == "ryu":
            self.parse_ryu_port_json(port_json)

        elif self.sw.network_graph.controller == "sel":
            self.parse_sel_port_json(port_json)

    def parse_odl_port_json(self, port_json):

        self.port_id = str(self.sw.node_id) + ":" + str(port_json["flow-node-inventory:port-number"])
        self.port_number = port_json["flow-node-inventory:port-number"]
        self.mac_address = port_json["flow-node-inventory:hardware-address"]
        self.curr_speed = int(port_json["flow-node-inventory:current-speed"])
        self.max_speed = int(port_json["flow-node-inventory:maximum-speed"])

        if port_json["flow-node-inventory:state"]["link-down"]:
            self.state = "down"
        else:
            self.state = "up"

    def parse_ryu_port_json(self, port_json):

        self.port_id = str(self.sw.node_id) + ":" + str(port_json["port_no"])
        self.port_number = port_json["port_no"]
        self.mac_address = port_json["hw_addr"]

        if "curr_speed" in port_json:
            self.curr_speed = int(port_json["curr_speed"])
        if "max_speed" in port_json:
            self.max_speed = int(port_json["max_speed"])

        #TODO: Peep into port_json["state"]
        self.state = "up"

    def parse_sel_port_json(self, port_json):
        self.port_id = str(self.sw.node_id) + ":" + str(port_json["portId"])
        self.port_number = port_json["portId"]
        self.mac_address = port_json["hardwareAddress"]
        self.curr_speed = port_json["currentSpeed"]
        self.max_speed = port_json["maxSpeed"]
        self.state = "up"

    def __str__(self):

        return str(self.port_id)
