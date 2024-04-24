from collections import namedtuple
from enum        import Enum
from dataclasses import dataclass
from typing      import NamedTuple


RegType = Enum('RegType', ['GENERAL', 'PREDICATE', 'LC', 'EC', 'RRB'])

InstClass = Enum('InstClass', ['ALU', 'Mulu', 'Mem', 'Branch'])

class Reg(namedtuple('Reg', ['type', 'idx'])):

    def __str__(self):
        if self.type == RegType.GENERAL:
            return "x" + str(self.idx)
        elif self.type == RegType.PREDICATE:
            return "p" + str(self.idx)
        else:
            return self.type.name

@dataclass
class Instruction:
    opcode: str
    rd : NamedTuple
    rs1: NamedTuple
    rs2: NamedTuple
    imm: int
    class_ : InstClass