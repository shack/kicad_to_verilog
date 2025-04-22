# KiCad to Verilog Converter

This small program converts a KiCad netlist into a verilog description.
The units of the schematics are mapped to verilog modules.
The parameters of the modules correspond to the pin numbers of the unit.
Vcc is mapped to `1'b1` and GND to `1'b0`.

To generate a netlist, open the schematic and choose

    File > Export > Netlist ...

Invoke this script on the netlist that you saved.

This program can also generate a Verilog module declaration for the
schematics sheet. To this end, it expects an interface symbol in the sheet.
The nets that are connected to the interface symbol will be the in/out/inout
parameters of the Verilog module.

To specify a symbol as the interface symbol, edit the properties of the
symbol on the schematics sheet and add a field called `kicad_to_verilog_interface`.
The corresponding value field will be ignored and can be left blank.

The nets that connect to the interface symbol will be analysed.
For each net, it will be checked in what way it connects to the other symbols
on your schematics. If it connects to at least one output pins, that net is
seen as an `out` parameter of the interface, if it connects only to input pins,
it is treated as an input, if it has a `tri_state` connection, it is `inout`.
