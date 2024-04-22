from collections import namedtuple
from enum        import Enum
from dataclasses import dataclass
from typing      import NamedTuple


RegType = Enum('RegType', ['GENERAL', 'PREDICATE', 'LC', 'EC', 'RRB'])
Reg = namedtuple('Reg', ['type', 'idx'])

class Reg(NamedTuple):
    
    type: int
    idx: str
    
    def __str__(self):
        return "LC" if RegType.LC else str(self.type) + str(self.idx)

@dataclass
class Instruction:
    opcode: str
    rd : NamedTuple
    rs1: NamedTuple
    rs2: NamedTuple
    imm: int