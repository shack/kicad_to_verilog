# KiCad to Verilog Converter

This small program converts a KiCad netlist into a verilog description.
The units of the schematics are mapped to verilog modules.
The parameters of the modules correspond to the pin numbers of the unit.
Vcc is mapped to `1'b1` and GND to `1'b0`.

To generate a netlist, open the schematic and choose

    File > Export > Netlist ...

Invoke this script on the netlist that you saved.
