
from dataclasses import dataclass
from collections import namedtuple

from type import RegType, Reg, Instruction
import csv

class Dep(namedtuple('Dep', ['consumer_reg', 'producer_id', 'producer_id_interloop'])):
    
    def __str__(self):
        if (self.producer_id_interloop is not None):
            return f"{self.consumer_reg} <- {self.producer_id} or _{self.producer_id_interloop}"
        else:
            return f"{self.consumer_reg} <- {self.producer_id}"
    

@dataclass
class DependencyTableEntry:
    #pc: int
    #id: int # simply the index of the instruction in iCache
    opcode: str
    dest: Reg # produced register
    # consumed registers
    localDeps        : list[Dep]
    interLoopDeps    : list[Dep]
    loopInvariantDeps: list[Dep]
    postLoopDeps     : list[Dep]
    renamedDest      : Reg # unused in this stage, will be used later in scheduling


class DependencyTable:
    bb0  : slice
    bb1  : slice
    bb2  : slice
    table: list[DependencyTableEntry]
    
    def __init__(self, insts: list[Instruction]):
        self.bb0 = slice(0, len(insts))
        self.bb1 = slice(len(insts), len(insts))
        self.bb2 = slice(len(insts), len(insts))
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

        # class FreshIdGenerator:
        #     ''' fresh identifier generator '''
        #     cnt: int = 0
        #     MAX: int = 9999
            
        #     def __call__(self) -> str:
        #         assert self.cnt < self.MAX, 'max number of identifier reached'

        #         token = str(self.cnt).zfill(4)
        #         self.cnt += 1
        #         return token
            
        # freshIdentifier = FreshIdGenerator()
        # initialize table with empty dependency columns
        for inst in insts:
            self.table.append(DependencyTableEntry(inst.opcode,
                                                   inst.rd,
                                                   [],[],[],[], None ))

        # helper function to find dependencies of a register in a certain range
        def findDependencies(reg: Reg, range: slice):
            ''' find dependencies of a register '''
            return next((i for i, entry in reversed(list(enumerate(self.table))[range]) if entry.dest == reg), None)


        # only local dependencies in bb0
        for i in range(10**10)[self.bb0]:
            inst = insts[i]
            entry = self.table[i]
            for rs in set(filter(None, [inst.rs1, inst.rs2])):
                # search ahead of the current instruction for local dependency
                if (p := findDependencies(rs, slice(0, i))) is not None:
                    entry.localDeps.append(Dep(rs, p, None))

        # local, inter-loop, and loop-invariant dependencies in bb1
        bb1Start = self.bb1.start
        bb2Start = self.bb2.start
        for i in range(10**10)[self.bb1]:
            inst = insts[i]
            entry = self.table[i]
            for rs in set(filter(None, [inst.rs1, inst.rs2])):
                if (pbb1Before := findDependencies(rs, slice(bb1Start, i))) is not None:
                    # if there exists a producer ahead of current instruction in bb1, it is a local dependency
                    entry.localDeps.append(Dep(rs, pbb1Before, None))
                elif (pbb1After := findDependencies(rs, slice(i, bb2Start))) is not None:
                    # if there's no producer ahead, but there's one following, it is a inter-loop dependency, note that it's the only case with 2 producers
                    entry.interLoopDeps.append(Dep(rs, findDependencies(rs, self.bb0), pbb1After))
                elif (pbb0 := findDependencies(rs, self.bb0)) is not None:
                    # if there's no producer in bb1, but there's one in bb0, it is a loop-invariant dependency
                    entry.loopInvariantDeps.append(Dep(rs, pbb0, None))

        # local dependency, post-loop dependencies, and loop-invariant dependencies in bb2
        for i in range(10**10)[self.bb2]:
            inst = insts[i]
            entry = self.table[i]
            for rs in set(filter(None, [inst.rs1, inst.rs2])):
                if (pbb2 := findDependencies(rs, slice(bb2Start, i))) is not None:
                    # if there exists a producer ahead of current instruction in bb2, it is a local dependency
                    entry.localDeps.append(Dep(rs, pbb2, None))
                elif (pbb1 := findDependencies(rs, self.bb1)) is not None:
                    # if there's no producer ahead in bb2, but there's one in bb1, it is a post-loop dependency
                    entry.postLoopDeps.append(Dep(rs, pbb1, None))
                elif (pbb0 := findDependencies(rs, self.bb0)) is not None:
                    # if there's no producer in neither bb2 nor bb1, but there's one in bb0, it is a loop-invariant dependency
                    entry.loopInvariantDeps.append(Dep(rs, pbb0, None))


    def to_csv(self, filename: str) -> None:
        ''' output dependency table to a csv file '''
        with open(filename, 'w', newline='') as csvfile:
            fieldnames = ['id', 'opcode', 'dest', 'localDeps', 'interLoopDeps', 'loopInvariantDeps', 'postLoopDeps']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            for i, entry in enumerate(self.table):
                writer.writerow({
                    'id': i,
                    'opcode': entry.opcode,
                    'dest': entry.dest,
                    'localDeps': [str(dep) for dep in entry.localDeps],
                    'interLoopDeps': [str(dep) for dep in entry.interLoopDeps],
                    'loopInvariantDeps': [str(dep) for dep in entry.loopInvariantDeps],
                    'postLoopDeps': [str(dep) for dep in entry.postLoopDeps]
                })
