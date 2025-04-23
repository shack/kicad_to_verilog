# TODO
# - unconnected pins
# - prefix for component name
# - wire declarations

#! /usr/bin/env python3

from decimal import Decimal

from collections import defaultdict

import re
import pathlib
import functools

import tinysexpr
import tyro

def get_of(l, syms):
    for e in l:
        name = str(e[0])
        if type(e) is list and name == syms:
            yield name, e[1:]

def get(l, sym):
    for _, e in get_of(l, sym):
        yield e

def get_one(l, sym):
    for e in get(l, sym):
        return e
    assert False, f"expected element '{sym}'"

def get_kv(l, sym):
    return car(get_one(l, sym))

def count(l, sym):
    return sum(1 for _ in get(l, sym))

def car(l):
    return l[0]

def cdr(l):
    return l[1:]

def get_atom_handler():
    r = re.compile(r'^(?P<int>-?\d+)|(?P<dec>-?\d+\.\d+)|"(?P<str>.*?)"$')
    handlers = {
        "int": int,
        "dec": Decimal,
        "str": str
    }
    def atom_handler(s):
        m = re.fullmatch(r, s)
        if m:
            for k, v in m.groupdict().items():
                if v is not None:
                    return handlers[k](v)
        return s
    return atom_handler

vcc = { 'VCC', 'VDD', '+5V', '+3.3V' }
gnd = { 'GND', 'VSS', '0V' }

def mangle(s):
    if s.isidentifier():
        return s
    else:
        s = s.replace(' ', '_')
        assert all(not c.isspace() for c in s)
        return rf'\{s} '

def get_buses(wires, bus_pattern):
    bus = re.compile(bus_pattern)
    buses = defaultdict(dict)
    for w in wires:
        if m := re.fullmatch(bus, w):
            name, num = m.groups()
            num = int(num)
            buses[name][num] = w
    return buses

def main(file: pathlib.Path,
         wires: bool = True,
         module: bool = True,
         pin_prefix: str = 'pin_',
         bus_pattern: str = r'([/_a-zA-Z]+)(\d+)'):
    """
    Convert a KiCad netlist to Verilog.

    Args:
        file: The path to the netlist file.
        wires: If True, print wire declarations.
        module: If True, print a module declaration if the file has an interface.
        pin_prefix: The prefix for pin names.
        bus_pattern: The regex pattern to match bus names and indices.
    """

    with open(file, "r") as f:
        netlist = tinysexpr.read(f, atom_handler=get_atom_handler())
        assert str(car(netlist)) == "export"

    interface = None

    # read the components
    components = {}
    for comps in get(netlist, 'components'):
        for c in get(comps, 'comp'):
            ref = get_kv(c, 'ref')
            components[ref] = get_kv(c, 'value')
            # check all properties of the component for kicad_to_verilog fields
            for p in get(c, 'property'):
                n = get_kv(p, 'name')
                v = get_kv(p, 'value')
                if module and n == 'kicad_to_verilog_interface':
                    interface = ref

    connections = { c: {} for c in components }
    nets = {}
    # read in the nets
    # and create a map that maps component pins to nets
    for nets_ in get(netlist, 'nets'):
        for net in get(nets_, 'net'):
            name = get_kv(net, 'name')
            if not name in (vcc | gnd):
                assert not name in nets
                nets[name] = set(get_kv(node, 'pintype') for node in get(net, 'node'))
            for node in get(net, 'node'):
                unit = get_kv(node, 'ref')
                pin  = get_kv(node, 'pin')
                ty   = get_kv(node, 'pintype')
                if not 'power' in ty:
                    # ignore power supply pins
                    connections[unit][pin] = name

    # if we print a module description, we will try to find buses
    # the following map maps signals to a pair of (bus, index)
    # of the bus signal and the according index
    signals_to_buses = {}
    cs = set()
    single_in_interface = set()
    # print module header if interface was found
    if interface:
        def get_net_io(ty):
            if any('no_connect' in s for s in ty):
                return None
            if 'tri_state' in ty:
                return 'inout'
            elif 'output' in ty:
                return 'output'
            elif 'input' in ty:
                assert not 'output' in ty
                return 'input'

        buses = get_buses(nets, bus_pattern)
        print(f'module {mangle(components[interface])} (')
        # get all the nets that connect to the interface
        cs = set(connections[interface].values()) - (vcc | gnd)
        # check if some of them are buses
        output = []
        for bus, pos_to_signal in buses.items():
            bus_signals = { s: i for i, s in pos_to_signal.items() }
            if bus_signals.keys() < cs:
                # if all the signals of the bus are in the interface, we can use the bus
                l, u = min(pos_to_signal), max(pos_to_signal)
                tys = functools.reduce(lambda a, b: a | b, (nets[n] for n in bus_signals))
                io = get_net_io(tys)
                assert io, 'bus has no io type'
                signals_to_buses |= { s: (bus, i) for s, i in bus_signals.items() }
                output += [ f'{io} [{u}:{l}] {mangle(bus)}' ]
        for c in sorted(cs):
            if not c in signals_to_buses:
                if io := get_net_io(nets[c]):
                    output += [ f'{io} {mangle(c)}' ]
                    single_in_interface.add(c)
        print('  ' + ',\n  '.join(output))
        print(');')

    # print wire declarations
    if wires:
        for w in sorted(nets):
            if w in signals_to_buses:
                bus, idx = signals_to_buses[w]
                init = f' = {mangle(bus)}[{idx}]'
                print(f'  wire {mangle(w)}{init};')
            elif not w in single_in_interface:
                init = ''
                print(f'  wire {mangle(w)}{init};')

    pulled_up = set()
    pulled_down = set()
    for c, pins in connections.items():
        if interface == c:
            # we don't want to print the interface itself
            continue
        val = components[c]
        # detect bypass caps
        if re.fullmatch(r'C\d+', c):
                assert len(pins) == 2
                assert set(pins.values()) <= (vcc | gnd), 'only bypass capacitors are supported'
                continue
        # detect pull-up/down resistors
        elif re.fullmatch(r'R\d+', c):
                assert len(pins) == 2
                nets = list(pins.values())
                for i, n in enumerate(nets):
                    other = nets[i ^ 1]
                    if n in vcc:
                        pulled_up.add(other)
                    elif n in gnd:
                        pulled_down.add(other)
                    else:
                        continue
                    assert not other in vcc | gnd, \
                        f'only pull-up/down resistors are supported, got {other}'
                    break
                else:
                    assert False, 'only pull-up/down resistors are supported, ' \
                        f'got resistor between {nets[0]} and {nets[1]}'
        else:
            print(f'  {mangle(val)} {mangle(c)} (')
            output = []
            for pin, net in pins.items():
                if net in vcc:
                    net = "1'b1"
                elif net in gnd:
                    net = "1'b0"
                else:
                    net = mangle(net)
                output  += [ f'.{pin_prefix}{(pin)}({net})' ]
            print('    ' + ',\n    '.join(output))
            print('  );')

    if interface:
        print('endmodule')

if __name__ == "__main__":
    tyro.cli(main)
