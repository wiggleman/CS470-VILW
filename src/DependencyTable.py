
from dataclasses import dataclass
from typing      import NamedTuple
from collections import namedtuple

from type import RegType, Reg, Instruction

Dep = namedtuple('Dep', ['consumer_reg', 'producer_id', 'producer_id_interloop'])

@dataclass
class DependencyTableEntry:
    #pc: int
    id: str
    opcode: str
    dest: NamedTuple # produced register
    # consumed registers
    localDeps        : list[NamedTuple]
    interLoopDeps    : list[NamedTuple]
    loopInvariantDeps: list[NamedTuple]
    postLoopDeps     : list[NamedTuple]


class DependencyTable:
    bb0  : slice
    bb1  : slice
    bb2  : slice
    table: list[DependencyTableEntry]
    
    def __init__(self, insts: list[Instruction]):
        self.bb0 = slice(0, len(insts))
        self.bb1 = None
        self.bb2 = None
        self.table = []

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
            MAX: int = 9999
            
            def __call__(self) -> str:
                assert self.cnt < self.MAX, 'max number of identifier reached'

                token = str(self.cnt).zfill(4)
                self.cnt += 1
                return token
            
        freshIdentifier = FreshIdGenerator()
        # initialize table with empty dependency columns
        for inst in insts:
            self.table.append(DependencyTableEntry(freshIdentifier(), 
                                                   inst.opcode,
                                                   inst.rd,
                                                   [],[],[],[] ))

        # helper function to find dependencies of a register in a certain range
        def findDependencies(reg: NamedTuple, range: slice) -> list[DependencyTableEntry]:
            ''' find dependencies of a register '''
            producer = next((entry for entry in reversed(self.table[range]) if entry.dest == reg), None)
            return producer.id if producer is not None else None

        # only local dependencies in bb0
        for i in range(10**10)[self.bb0]:
            inst = insts[i]
            entry = self.table[i]
            for rs in [r for r in [inst.rs1, inst.rs2] if r is not None]:
                # search ahead of the current instruction for local dependency
                if (p := findDependencies(rs, slice(0, i))) is not None:
                    entry.localDeps.append(Dep(rs, p, None))

        # local, inter-loop, and loop-invariant dependencies in bb1
        bb1Start = self.bb1.start
        bb2Start = self.bb2.start
        for i in range(10**10)[self.bb1]:
            inst = insts[i]
            entry = self.table[i]
            for rs in [r for r in [inst.rs1, inst.rs2] if r is not None]:
                if (pbb1Before := findDependencies(rs, slice(bb1Start, i))) is not None:
                    # if there exists a producer ahead of current instruction in bb1, it is a local dependency
                    entry.localDeps.append(Dep(rs, pbb1Before, None))
                elif (pbb1After := findDependencies(rs, slice(i, bb2Start))) is not None:
                    # if there's no producer ahead, but there's one following, it is a inter-loop dependency, note that it's the only case with 2 producers
                    entry.interLoopDeps.append(Dep(rs, pbb1After, findDependencies(rs, self.bb0)))
                elif (pbb0 := findDependencies(rs, self.bb0)) is not None:
                    # if there's no producer in bb1, but there's one in bb0, it is a loop-invariant dependency
                    entry.loopInvariantDeps.append(Dep(rs, pbb0, None))

        # local dependency, post-loop dependencies, and loop-invariant dependencies in bb2
        for i in range(10**10)[self.bb2]:
            inst = insts[i]
            entry = self.table[i]
            for rs in [r for r in [inst.rs1, inst.rs2] if r is not None]:
                if (pbb2 := findDependencies(rs, slice(bb2Start, i))) is not None:
                    # if there exists a producer ahead of current instruction in bb2, it is a local dependency
                    entry.localDeps.append(Dep(rs, pbb2, None))
                elif (pbb1 := findDependencies(rs, self.bb1)) is not None:
                    # if there's no producer ahead in bb2, but there's one in bb1, it is a post-loop dependency
                    entry.postLoopDeps.append(Dep(rs, pbb1, None))
                elif (pbb0 := findDependencies(rs, self.bb0)) is not None:
                    # if there's no producer in neither bb2 nor bb1, but there's one in bb0, it is a loop-invariant dependency
                    entry.loopInvariantDeps.append(Dep(rs, pbb0, None))

    def __str__(self) -> str:
        ''' pretty print dependency table '''
        return '\n'.join(str(entry) for entry in self.table)

