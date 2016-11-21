#!/usr/local/bin/python
# -*- coding: utf-8 -*-


import pytest
# skip these tests if numpy is not installed
pytest.importorskip("numpy")

import numpy as np
from micropsi_core.world.worldadapter import ArrayWorldAdapter


class SimpleArrayWA(ArrayWorldAdapter):
    def __init__(self, world):
        super().__init__(world)
        self.add_datasources(['a', 'b', 'c', 'd', 'e'])
        self.add_datatargets(['a', 'b', 'c', 'd', 'e'])
        self.update_data_sources_and_targets()

    def update_data_sources_and_targets(self):
        self.datatarget_feedback_values = np.copy(self.datatarget_values)
        self.datasources = np.random.rand(len(self.datasources))


def prepare(runtime, test_nodenet, default_world, resourcepath):
    """ Create a bunch of available flowmodules for the following tests """
    import os
    with open(os.path.join(resourcepath, 'nodetypes.json'), 'w') as fp:
        fp.write("""
    {"Double": {
        "flow_module": true,
        "implementation": "theano",
        "name": "Double",
        "build_function_name": "double",
        "init_function_name": "double_init",
        "inputs": ["inputs"],
        "outputs": ["outputs"],
        "inputdims": [1]
    },
    "Add": {
        "flow_module": true,
        "implementation": "theano",
        "name": "Add",
        "build_function_name": "add",
        "inputs": ["input1", "input2"],
        "outputs": ["outputs"],
        "inputdims": [1, 1]
    },
    "Bisect": {
        "flow_module": true,
        "implementation": "theano",
        "name": "Bisect",
        "build_function_name": "bisect",
        "inputs": ["inputs"],
        "outputs": ["outputs"],
        "inputdims": [1]
    },
    "Numpy": {
        "flow_module": true,
        "implementation": "python",
        "name": "Numpy",
        "init_function_name": "numpyfunc_init",
        "run_function_name": "numpyfunc",
        "inputs": ["inputs"],
        "outputs": ["outputs"],
        "inputdims": [1]
    },
    "SharedVars": {
        "flow_module": true,
        "implementation": "theano",
        "name": "SharedVars",
        "init_function_name": "sharedvars_init",
        "build_function_name": "sharedvars",
        "parameters": ["weights_shape", "use_weights"],
        "inputs": ["X"],
        "outputs": ["Y"],
        "inputdims": [1]
    },
    "TwoOutputs":{
        "flow_module": true,
        "implementation": "theano",
        "name": "TwoOutputs",
        "build_function_name": "two_outputs",
        "inputs": ["X"],
        "outputs": ["A", "B"],
        "inputdims": [1]
    },
    "TRPOOut":{
        "flow_module": true,
        "implementation": "theano",
        "name": "TRPOOut",
        "build_function_name": "trpoout",
        "inputs": ["X"],
        "outputs": ["Y", "Z"],
        "inputdims": [1]
    },
    "TRPOIn":{
        "flow_module": true,
        "implementation": "theano",
        "name": "TRPOIn",
        "build_function_name": "trpoin",
        "inputs": ["Y", "Z"],
        "outputs": ["A"],
        "inputdims": ["list", 1]
    },
    "TRPOInPython":{
        "flow_module": true,
        "implementation": "python",
        "name": "TRPOIn",
        "run_function_name": "trpoinpython",
        "inputs": ["Y", "Z"],
        "outputs": ["A"],
        "inputdims": ["list", 1]
    }}""")
    with open(os.path.join(resourcepath, 'nodefunctions.py'), 'w') as fp:
        fp.write("""
def double_init(netapi, node, parameters):
    node.initfunction_ran = True

def double(inputs, netapi, node, parameters):
    return inputs * 2

def add(input1, input2, netapi, node, parameters):
    return input1 + input2

def bisect(inputs, netapi, node, parameters):
    return inputs / 2

def numpyfunc_init(netapi, node, parameters):
    node.initfunction_ran = True

def numpyfunc(inputs, netapi, node, parameters):
    import numpy as np
    ones = np.zeros_like(inputs)
    ones[:] = 1.0
    netapi.notify_user(node, "numpyfunc ran")
    return inputs + ones

def sharedvars_init(netapi, node, parameters):
    import numpy as np
    w_array = np.random.rand(parameters['weights_shape']).astype(netapi.floatX)
    b_array = np.ones(parameters['weights_shape']).astype(netapi.floatX)
    node.set_shared_variable('weights', w_array)
    node.set_shared_variable('bias', b_array)

def sharedvars(X, netapi, node, parameters):
    if parameters.get('use_weights'):
        return X * node.get_shared_variable('weights') + node.get_shared_variable('bias')
    else:
        return X

def two_outputs(X, netapi, node, parameters):
    return X, X+1

def trpoout(X, netapi, node, parameters):
    from theano import tensor as T
    return [X, X+1, X*2], T.exp(X)

def trpoin(X, Y, netapi, node, parameters):
    for thing in X:
        Y += thing
    return Y

def trpoinpython(X, Y, netapi, node, parameters):
    for thing in X:
        Y += thing
    return Y
""")

    nodenet = runtime.nodenets[test_nodenet]
    netapi = nodenet.netapi
    worldadapter = SimpleArrayWA(runtime.worlds[default_world])
    nodenet.worldadapter_instance = worldadapter
    runtime.reload_native_modules()
    return nodenet, netapi, worldadapter


@pytest.mark.engine("theano_engine")
def test_flowmodule_definition(runtime, test_nodenet, default_world, resourcepath):
    nodenet, netapi, worldadapter = prepare(runtime, test_nodenet, default_world, resourcepath)

    metadata = runtime.get_nodenet_metadata(test_nodenet)
    assert 'Double' not in metadata['native_modules']
    assert metadata['flow_modules']['Double']['inputs'] == ["inputs"]
    assert metadata['flow_modules']['Double']['outputs'] == ["outputs"]

    flowmodule = netapi.create_node("Double", None, "Double")
    assert not hasattr(flowmodule, 'initfunction_ran')

    nodenet.connect_flow_module_to_worldadapter(flowmodule.uid, "inputs")
    nodenet.connect_flow_module_to_worldadapter(flowmodule.uid, "outputs")

    sources = np.zeros((5), dtype=nodenet.numpyfloatX)
    sources[:] = np.random.randn(*sources.shape)

    worldadapter.datasource_values = sources

    # step & assert that nothing happened without sub-activation
    nodenet.step()
    assert np.all(worldadapter.datatarget_values == np.zeros(5, dtype=nodenet.numpyfloatX))

    # create activation source:
    source = netapi.create_node("Neuron", None)
    netapi.link(source, 'gen', source, 'gen')
    netapi.link(source, 'gen', flowmodule, 'sub')
    source.activation = 1

    # # step & assert that the initfunction and flowfunction ran
    nodenet.step()
    assert np.all(worldadapter.datatarget_values == sources * 2)
    assert hasattr(flowmodule, 'initfunction_ran')


@pytest.mark.engine("theano_engine")
def test_multiple_flowgraphs(runtime, test_nodenet, default_world, resourcepath):
    nodenet, netapi, worldadapter = prepare(runtime, test_nodenet, default_world, resourcepath)

    double = netapi.create_node("Double", None, "Double")
    add = netapi.create_node("Add", None, "Add")
    bisect = netapi.create_node("Bisect", None, "Bisect")

    # create a first graph
    # link datasources to double & add
    nodenet.connect_flow_module_to_worldadapter(double.uid, "inputs")
    nodenet.connect_flow_module_to_worldadapter(add.uid, "input2")
    # link double to add:
    nodenet.connect_flow_modules(double.uid, "outputs", add.uid, "input1")

    # link add to datatargets
    nodenet.connect_flow_module_to_worldadapter(add.uid, "outputs")

    assert len(nodenet.flowfuncs) == 1

    # create a second graph
    nodenet.connect_flow_module_to_worldadapter(bisect.uid, "inputs")
    nodenet.connect_flow_module_to_worldadapter(bisect.uid, "outputs")

    assert len(nodenet.flowfuncs) == 2

    sources = np.zeros((5), dtype=nodenet.numpyfloatX)
    sources[:] = np.random.randn(*sources.shape)

    worldadapter.datasource_values = sources

    # create activation source
    source = netapi.create_node("Neuron", None)
    netapi.link(source, 'gen', source, 'gen')
    source.activation = 1

    # link to first graph:
    netapi.link(source, 'gen', add, 'sub')

    # step & assert that only the first graph ran
    nodenet.step()
    assert np.all(worldadapter.datatarget_values == sources * 3)

    # link source to second graph:
    worldadapter.datatarget_values = np.zeros(len(worldadapter.datatarget_values), dtype=nodenet.numpyfloatX)
    netapi.link(source, 'gen', bisect, 'sub')
    nodenet.step()
    datatargets = np.around(worldadapter.datatarget_values, decimals=4)
    sources = np.around(sources * 3.5, decimals=4)
    assert np.all(datatargets == sources)


@pytest.mark.engine("theano_engine")
def test_disconnect_flowmodules(runtime, test_nodenet, default_world, resourcepath):
    nodenet, netapi, worldadapter = prepare(runtime, test_nodenet, default_world, resourcepath)

    double = netapi.create_node("Double", None, "Double")
    add = netapi.create_node("Add", None, "Add")

    # link datasources to double & add
    nodenet.connect_flow_module_to_worldadapter(double.uid, "inputs")
    nodenet.connect_flow_module_to_worldadapter(add.uid, "input2")
    # link double to add:
    nodenet.connect_flow_modules(double.uid, "outputs", add.uid, "input1")
    # link add to datatargets
    nodenet.connect_flow_module_to_worldadapter(add.uid, "outputs")

    # have one connected graph
    assert len(nodenet.flowfuncs) == 1

    # unlink double from add
    nodenet.disconnect_flow_modules(double.uid, "outputs", add.uid, "input1")

    # assert dependencies cleaned
    assert double.uid not in nodenet.flow_module_instances[add.uid].dependencies

    # unlink add from datatargets
    nodenet.disconnect_flow_module_from_worldadapter(add.uid, "outputs")

    assert len(nodenet.flowfuncs) == 0

    sources = np.zeros((5), dtype=nodenet.numpyfloatX)
    sources[:] = np.random.randn(*sources.shape)
    worldadapter.datasource_values = sources

    nodenet.step()
    assert np.all(worldadapter.datatarget_values == np.zeros(5))


@pytest.mark.engine("theano_engine")
def test_diverging_flowgraph(runtime, test_nodenet, default_world, resourcepath):
    nodenet, netapi, worldadapter = prepare(runtime, test_nodenet, default_world, resourcepath)

    double = netapi.create_node("Double", None, "Double")
    add = netapi.create_node("Add", None, "Add")
    bisect = netapi.create_node("Bisect", None, "Bisect")

    # link sources to bisect
    nodenet.connect_flow_module_to_worldadapter(bisect.uid, "inputs")
    # link bisect to double:
    nodenet.connect_flow_modules(bisect.uid, "outputs", double.uid, "inputs")
    # link bisect to add:
    nodenet.connect_flow_modules(bisect.uid, "outputs", add.uid, "input1")
    # link sources to add:
    nodenet.connect_flow_module_to_worldadapter(add.uid, "input2")

    # link double and add to targets:
    nodenet.connect_flow_module_to_worldadapter(double.uid, "outputs")
    nodenet.connect_flow_module_to_worldadapter(add.uid, "outputs")

    assert len(nodenet.flowfuncs) == 2

    sources = np.zeros((5), dtype=nodenet.numpyfloatX)
    sources[:] = np.random.randn(*sources.shape)
    worldadapter.datasource_values = sources

    # create activation source
    source = netapi.create_node("Neuron", None)
    netapi.link(source, 'gen', source, 'gen')
    source.activation = 1

    # link activation source to double
    netapi.link(source, 'gen', double, 'sub')
    nodenet.step()
    assert np.all(worldadapter.datatarget_values == sources)

    # unlink double, link add:
    netapi.unlink(source, 'gen', double, 'sub')
    netapi.link(source, 'gen', add, 'sub')
    worldadapter.datatarget_values = np.zeros(len(worldadapter.datatarget_values), dtype=nodenet.numpyfloatX)
    nodenet.step()
    assert np.all(worldadapter.datatarget_values == sources * 1.5)


@pytest.mark.engine("theano_engine")
def test_converging_flowgraphs(runtime, test_nodenet, default_world, resourcepath):
    nodenet, netapi, worldadapter = prepare(runtime, test_nodenet, default_world, resourcepath)

    double1 = netapi.create_node("Double", None, "Double")
    double2 = netapi.create_node("Double", None, "Double")
    add = netapi.create_node("Add", None, "Add")

    # link sources
    nodenet.connect_flow_module_to_worldadapter(double1.uid, "inputs")
    nodenet.connect_flow_module_to_worldadapter(double2.uid, "inputs")

    # link both doubles to add
    nodenet.connect_flow_modules(double1.uid, "outputs", add.uid, "input1")
    nodenet.connect_flow_modules(double2.uid, "outputs", add.uid, "input2")

    # link add to targets.
    nodenet.connect_flow_module_to_worldadapter(add.uid, "outputs")

    sources = np.zeros((5), dtype=nodenet.numpyfloatX)
    sources[:] = np.random.randn(*sources.shape)
    worldadapter.datasource_values = sources

    # create activation source
    source = netapi.create_node("Neuron", None)
    netapi.link(source, 'gen', source, 'gen')
    source.activation = 1

    # link activation source to double
    netapi.link(source, 'gen', add, 'sub')
    nodenet.step()
    assert np.all(worldadapter.datatarget_values == sources * 4)


@pytest.mark.engine("theano_engine")
def test_flowmodule_persistency(runtime, test_nodenet, default_world, resourcepath):
    nodenet, netapi, worldadapter = prepare(runtime, test_nodenet, default_world, resourcepath)

    flowmodule = netapi.create_node("Double", None, "Double")
    nodenet.connect_flow_module_to_worldadapter(flowmodule.uid, "inputs")
    nodenet.connect_flow_module_to_worldadapter(flowmodule.uid, "outputs")
    source = netapi.create_node("Neuron", None)
    netapi.link(source, 'gen', source, 'gen')
    netapi.link(source, 'gen', flowmodule, 'sub')
    source.activation = 1

    runtime.save_nodenet(test_nodenet)
    runtime.revert_nodenet(test_nodenet)

    nodenet = runtime.nodenets[test_nodenet]
    flowmodule = nodenet.get_node(flowmodule.uid)
    netapi = nodenet.netapi
    nodenet.worldadapter_instance = worldadapter

    sources = np.zeros((5), dtype=nodenet.numpyfloatX)
    sources[:] = np.random.randn(*sources.shape)

    worldadapter.datasource_values = sources

    nodenet.step()
    assert np.all(worldadapter.datatarget_values == sources * 2)


@pytest.mark.engine("theano_engine")
def test_delete_flowmodule(runtime, test_nodenet, default_world, resourcepath):
    nodenet, netapi, worldadapter = prepare(runtime, test_nodenet, default_world, resourcepath)

    double1 = netapi.create_node("Double", None, "Double")
    double2 = netapi.create_node("Double", None, "Double")
    add = netapi.create_node("Add", None, "Add")
    bisect = netapi.create_node("Bisect", None, "Bisect")

    # build graph:
    netapi.connect_flow_modules(bisect, "outputs", add, "input1")
    netapi.connect_flow_modules(add, "outputs", double1, "inputs")
    netapi.connect_flow_modules(add, "outputs", double2, "inputs")
    netapi.connect_flow_module_to_worldadapter(bisect, "inputs")
    netapi.connect_flow_module_to_worldadapter(add, "input2")
    netapi.connect_flow_module_to_worldadapter(double1, "outputs")
    netapi.connect_flow_module_to_worldadapter(double2, "outputs")

    assert len(nodenet.flowfuncs) == 2

    netapi.delete_node(add)

    assert len(nodenet.flowfuncs) == 0

    assert not nodenet.flow_module_instances[bisect.uid].is_output_connected()
    for node in nodenet.flow_module_instances.values():
        assert add.uid not in node.dependencies

    sources = np.zeros((5), dtype=nodenet.numpyfloatX)
    sources[:] = np.random.randn(*sources.shape)
    worldadapter.datasource_values = sources

    nodenet.step()
    assert np.all(worldadapter.datatarget_values == np.zeros(5))


@pytest.mark.engine("theano_engine")
def test_link_large_graph(runtime, test_nodenet, default_world, resourcepath):
    nodenet, netapi, worldadapter = prepare(runtime, test_nodenet, default_world, resourcepath)

    double = netapi.create_node("Double", None, "Double")
    bisect = netapi.create_node("Bisect", None, "Bisect")
    add = netapi.create_node("Add", None, "Add")

    # create activation source:
    source = netapi.create_node("Neuron", None)
    source.activation = 1

    nodenet.connect_flow_module_to_worldadapter(bisect.uid, "inputs")
    nodenet.connect_flow_modules(bisect.uid, "outputs", double.uid, "inputs")

    nodenet.connect_flow_module_to_worldadapter(add.uid, "input1")
    nodenet.connect_flow_module_to_worldadapter(add.uid, "outputs")

    nodenet.connect_flow_modules(double.uid, "outputs", add.uid, "input2")

    netapi.link(source, 'gen', add, 'sub')
    assert len(nodenet.flowfuncs) == 1

    sources = np.zeros((5), dtype=nodenet.numpyfloatX)
    sources[:] = np.random.randn(*sources.shape)
    worldadapter.datasource_values = sources

    nodenet.step()
    assert np.all(worldadapter.datatarget_values == sources * 2)


@pytest.mark.engine("theano_engine")
def test_python_flowmodules(runtime, test_nodenet, default_world, resourcepath):
    nodenet, netapi, worldadapter = prepare(runtime, test_nodenet, default_world, resourcepath)

    double = netapi.create_node("Double", None, "Double")
    py = netapi.create_node("Numpy", None, "Numpy")
    bisect = netapi.create_node("Bisect", None, "Bisect")

    source = netapi.create_node("Neuron", None)
    netapi.link(source, 'gen', source, 'gen')
    source.activation = 1

    assert not hasattr(py, 'initfunction_ran')

    netapi.connect_flow_module_to_worldadapter(double, "inputs")
    netapi.connect_flow_modules(double, "outputs", py, "inputs")
    netapi.connect_flow_modules(py, "outputs", bisect, "inputs")
    netapi.connect_flow_module_to_worldadapter(bisect, "outputs")

    sources = np.zeros((5), dtype=nodenet.numpyfloatX)
    sources[:] = np.random.randn(*sources.shape)
    worldadapter.datasource_values = sources

    nodenet.step()
    assert np.all(worldadapter.datatarget_values == 0)

    # netapi.link(source, 'gen', bisect, 'sub')

    nodenet.step()
    assert np.all(worldadapter.datatarget_values == 0)

    netapi.link(source, 'gen', bisect, 'sub')

    nodenet.step()
    # ((x * 2) + 1) / 2 == x + .5
    assert np.all(worldadapter.datatarget_values == sources + 0.5)
    assert py.initfunction_ran


@pytest.mark.engine("theano_engine")
def test_compile_flow_subgraph(runtime, test_nodenet, default_world, resourcepath):
    nodenet, netapi, worldadapter = prepare(runtime, test_nodenet, default_world, resourcepath)

    double = netapi.create_node("Double", None, "Double")
    bisect = netapi.create_node("Bisect", None, "Bisect")

    netapi.connect_flow_modules(double, "outputs", bisect, "inputs")

    func, ins, outs = nodenet.compile_flow_subgraph([double.uid, bisect.uid], partial=True)

    assert np.all(func(inputs=[1, 2, 3, 4]) == np.asarray([1, 2, 3, 4], dtype=nodenet.numpyfloatX))


@pytest.mark.engine("theano_engine")
def test_compile_flow_subgraph_bridges_numpy_gaps(runtime, test_nodenet, default_world, resourcepath):
    nodenet, netapi, worldadapter = prepare(runtime, test_nodenet, default_world, resourcepath)

    double = netapi.create_node("Double", None, "Double")
    py = netapi.create_node("Numpy", None, "Numpy")
    bisect = netapi.create_node("Bisect", None, "Bisect")

    netapi.connect_flow_modules(double, "outputs", py, "inputs")
    netapi.connect_flow_modules(py, "outputs", bisect, "inputs")

    func = netapi.compile_flow_subgraph([bisect, double, py])

    assert np.all(func(inputs=[1, 2, 3, 4]) == np.asarray([1.5, 2.5, 3.5, 4.5], dtype=nodenet.numpyfloatX))


@pytest.mark.engine("theano_engine")
def test_shared_variables(runtime, test_nodenet, default_world, resourcepath):
    nodenet, netapi, worldadapter = prepare(runtime, test_nodenet, default_world, resourcepath)

    module = netapi.create_node("SharedVars", None, "module")
    module.set_parameter('use_weights', True)
    module.set_parameter('weights_shape', 5)

    netapi.connect_flow_module_to_worldadapter(module, "X")
    netapi.connect_flow_module_to_worldadapter(module, "Y")

    sources = np.zeros((5), dtype=nodenet.numpyfloatX)
    sources[:] = np.random.randn(*sources.shape)
    worldadapter.datasource_values = sources

    source = netapi.create_node("Neuron", None)
    netapi.link(source, 'gen', source, 'gen')
    source.activation = 1
    netapi.link(source, 'gen', module, 'sub')

    nodenet.step()

    result = sources * module.get_shared_variable('weights').get_value() + module.get_shared_variable('bias').get_value()
    assert np.all(worldadapter.datatarget_values == result)

    func = netapi.compile_flow_subgraph([module], with_shared_variables=True)

    x = np.ones(5).astype(netapi.floatX)
    weights = np.random.rand(5).astype(netapi.floatX)
    bias = np.ones(5).astype(netapi.floatX)

    result = func(shared_variables=[bias, weights], X=x)

    assert np.all(result == x * weights + bias)


@pytest.mark.engine("theano_engine")
def test_flow_edgecase(runtime, test_nodenet, default_world, resourcepath):
    nodenet, netapi, worldadapter = prepare(runtime, test_nodenet, default_world, resourcepath)

    twoout = netapi.create_node("TwoOutputs", None, "twoout")
    double = netapi.create_node("Double", None, "double")
    numpy = netapi.create_node("Numpy", None, "numpy")
    add = netapi.create_node("Add", None, "add")

    netapi.connect_flow_modules(twoout, "A", double, "inputs")
    netapi.connect_flow_modules(twoout, "B", numpy, "inputs")
    netapi.connect_flow_modules(double, "outputs", add, "input1")
    netapi.connect_flow_modules(numpy, "outputs", add, "input2")

    function = netapi.compile_flow_subgraph([twoout, double, numpy, add])

    x = np.array([1, 2, 3], dtype=netapi.floatX)
    result = np.array([5, 8, 11], dtype=netapi.floatX)
    assert np.all(function(X=x) == result)


@pytest.mark.engine("theano_engine")
def test_flow_trpo_modules(runtime, test_nodenet, default_world, resourcepath):
    nodenet, netapi, worldadapter = prepare(runtime, test_nodenet, default_world, resourcepath)

    trpoout = netapi.create_node("TRPOOut", None, "TRPOOut")
    trpoin = netapi.create_node("TRPOIn", None, "TRPOIn")

    netapi.connect_flow_modules(trpoout, "Y", trpoin, "Y")
    netapi.connect_flow_modules(trpoout, "Z", trpoin, "Z")

    function = netapi.compile_flow_subgraph([trpoin, trpoout])

    x = np.array([1, 2, 3], dtype=netapi.floatX)
    result = sum([np.exp(x), x, x*2, x+1])
    assert np.all(function(X=x) == result)

    netapi.delete_node(trpoin)
    trpoinpy = netapi.create_node("TRPOInPython", None, "TRPOInPython")

    netapi.connect_flow_modules(trpoout, "Y", trpoinpy, "Y")
    netapi.connect_flow_modules(trpoout, "Z", trpoinpy, "Z")

    function = netapi.compile_flow_subgraph([trpoinpy, trpoout])
    assert np.all(function(X=x) == result)


@pytest.mark.engine("theano_engine")
def test_flowmodules_shallowcopy(runtime, test_nodenet, default_world, resourcepath):
    nodenet, netapi, worldadapter = prepare(runtime, test_nodenet, default_world, resourcepath)

    node1 = netapi.create_node("SharedVars", None, "node1")
    node1.set_parameter('use_weights', True)
    node1.set_parameter('weights_shape', 5)
    node2 = netapi.create_node("SharedVars", None, "node2")
    node2.set_parameter('use_weights', False)
    node2.set_parameter('weights_shape', 5)

    netapi.connect_flow_modules(node1, "Y", node2, "X")

    function = netapi.compile_flow_subgraph([node1, node2])

    x = np.array([1, 2, 3, 4, 5], dtype=netapi.floatX)
    result = function(X=x)[0]

    copies = netapi.create_flow_subgraph_copy([node1, node2])

    copyfunction = netapi.compile_flow_subgraph([copies[0], copies[1]])
    assert np.all(copyfunction(X=x) == result)

    # change original
    node2.set_parameter('use_weights', True)

    # recompile, assert change took effect
    assert copies[1].get_parameter('use_weights')
    function = netapi.compile_flow_subgraph([node1, node2])
    result2 = function(X=x)[0]
    assert np.all(result2 != result)

    # recompile copy, assert change took effect here as well.
    copyfunc = netapi.compile_flow_subgraph([copies[0], copies[1]])
    assert np.all(copyfunc(X=x) == result2)

    # change back, save and reload and assert the copy
    # still returs the original's value
    node2.set_parameter('use_weights', False)
    runtime.save_nodenet(test_nodenet)
    runtime.revert_nodenet(test_nodenet)
    nodenet = runtime.nodenets[test_nodenet]
    netapi = nodenet.netapi
    copies = [netapi.get_node(copies[0].uid), netapi.get_node(copies[1].uid)]
    assert not copies[1].get_parameter('use_weights')
