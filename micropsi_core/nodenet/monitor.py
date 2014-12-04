# -*- coding: utf-8 -*-

"""
Monitor definition
"""

import micropsi_core.tools

__author__ = 'joscha'
__date__ = '09.05.12'


class Monitor(object):
    """A gate or slot monitor watching the activation of the given slot or gate over time

    Attributes:
        nodenet: the parent Nodenet
        node: the parent Node
        type: either "slot" or "gate"
        target: the name of the observerd Slot or Gate
    """

    @property
    def data(self):
        data = {
            "uid": self.uid,
            "values": self.values,
            "node_uid": self.node_uid,
            "node_name": self.node_name,
            "type": self.type,
            "target": self.target
        }
        return data

    def __init__(self, nodenet, node_uid, type, target, node_name='', uid=None, **_):
        self.uid = uid or micropsi_core.tools.generate_uid()
        self.nodenet = nodenet
        self.values = {}
        self.node_uid = node_uid
        self.node_name = node_name
        self.type = type
        self.target = target
        nodenet._register_monitor(self)

    def step(self, step):
        if self.nodenet.is_node(self.node_uid):
            if self.type == 'gate' and self.target in self.nodenet.get_node(self.node_uid).get_gate_types():
                self.values[step] = self.nodenet.get_node(self.node_uid).get_gate(self.target).activations['default']
            if self.type == 'slot' and self.target in self.nodenet.get_node(self.node_uid).get_slot_types():
                self.values[step] = self.nodenet.get_node(self.node_uid).get_slot(self.target).activations['default']

    def clear(self):
        self.values = {}
