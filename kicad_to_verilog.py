#! /usr/bin/env python3

from decimal import Decimal

import sys
import re

import tinysexpr

def get_of(l, syms):
    for e in l:
        name = str(e[0])
        if type(e) is list and name in syms:
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
        assert all(not c.isspace() for c in s)
        return rf'\{s} '

if __name__ == "__main__":
    with open(sys.argv[1], "r") as f:
        netlist = tinysexpr.read(f, atom_handler=get_atom_handler())
        assert str(car(netlist)) == "export"

    # read the components
    components = {}
    for comps in get(netlist, 'components'):
        for c in get(comps, 'comp'):
            ref = get_kv(c, 'ref')
            components[ref] = get_kv(c, 'value')

    connections = { c: {} for c in components }
    # read in the nets
    for nets in get(netlist, 'nets'):
        for net in get(nets, 'net'):
            name = get_kv(net, 'name')
            for node in get(net, 'node'):
                unit = get_kv(node, 'ref')
                pin  = get_kv(node, 'pin')
                connections[unit][pin] = name

    pulled_up = set()
    pulled_down = set()
    for c, pins in connections.items():
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
            print(f'{mangle(val)} {mangle(c)} (')
            for pin, net in pins.items():
                if net in vcc:
                    net = "1'b1"
                elif net in gnd:
                    net = "1'b0"
                else:
                    net = mangle(net)
                print(f'  ._{(pin)}({net})')
            print(')')
