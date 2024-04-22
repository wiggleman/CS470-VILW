from collections import namedtuple
from dataclasses import dataclass
from typing      import NamedTuple

from VLIW470 import RegType, Reg, Instruction

Dep = namedtuple('Dep', ['consumer_operand', 'producer_isnt', 'producer_inst_interloop'])

@dataclass
class DependencyTableEntry:
    #pc: int
    id: str
    opcode: str
    dest: NamedTuple # produced register
    # consumed registers
    localDeps        : NamedTuple
    interLoopDeps    : NamedTuple
    loopInvariantDeps: NamedTuple
    postLoopDeps     : NamedTuple


class DependencyTable:
    bb0  : slice
    bb1  : slice
    bb2  : slice
    table: list[DependencyTableEntry]
    
    def __init__(self, insts: list[Instruction]):
        self.bb0 = slice(0, len(insts))
        self.bb1 = None
        self.bb2 = None

        self.delineate(insts)
        self.analyze(insts)

    def delineate(self, insts) -> None:
        ''' find basic blocks '''
        for pc, inst in enumerate(insts):
            if inst.opcode == 'loop':
                self.bb0 = slice(0, inst.imm)
                self.bb1 = slice(inst.imm, pc+1)
                self.bb2 = slice(pc+1, len(insts))
                break        

    def analyze(self, insts) -> None:
        ''' analyze dependencies '''

        class FreshIdGenerator:
            ''' fresh identifier generator '''
            cnt: int = 0
            MAX: int = 999
            
            def __call__(self) -> str:
                assert self.cnt < self.MAX, 'max number of identifier reached'

                token = str(self.cnt).zfill(3)
                self.cnt += 1
                return token
            
        freshIdentifier = FreshIdGenerator()

        for inst in insts[self.bb0]:
            if inst.rs1 != None:
                producer = next((entry for entry in self.table if entry.dest == inst.rs1), None)
                if producer is not None:
                    # Do something with existing_entry
            self.table.append(DependencyTableEntry(freshIdentifier(), 
                                                   inst.opcode,
                                                   inst.rd,
                                                   ))