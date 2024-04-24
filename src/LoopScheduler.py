from VLIW470 import VLIW470
from type import RegType, Reg, Instruction, InstClass
from DependencyTable import DependencyTableEntry
from dataclasses import dataclass, field


@dataclass # mutable, since the renameing is done in a later stage
class _Instruction:
    opcode: str = field(default=None)
    id: int = field(default=None) # its index in depTable and iCache
    rd : Reg = field(default=None) # destination register after renaming
    rs1: Reg = field(default=None) # source register after renaming
    rs2: Reg = field(default=None)
    imm: int = field(default=None)

    def __init__(self, instruction: Instruction, id: int):
        self.opcode = instruction.opcode
        self.id = id
        self.rd = instruction.rd
        self.rs1 = instruction.rs1
        self.rs2 = instruction.rs2
        self.imm = instruction.imm



@dataclass
class Bundle:

    insts: list[_Instruction] = field(default_factory=list)
    template: list[InstClass] = field(default_factory=list)

    def insert(self, inst: _Instruction, class_: InstClass):
        if class_ == InstClass.ALU:
            if self.template.count(InstClass.ALU) < 2:
                self.insts.append(inst)
                self.template.append(class_)
                return True
            else:
                return False
        else:
            if class_ not in self.template:
                self.insts.append(inst)
                self.template.append(class_)
                return True
            else:
                return False
    # ALU0: _Instruction = field(default=None)
    # ALU1: _Instruction = field(default=None)
    # Mult: _Instruction = field(default=None)
    # Mem: _Instruction = field(default=None)
    # Branch: _Instruction = field(default=None)

    # def insert(self, inst):
    #     opcode = inst.opcode
    #     if opcode == 'add' or \
    #        opcode == 'sub' or \
    #        opcode == 'addi' or \
    #        opcode == 'mov':
    #         if self.ALU0 is None:
    #             self.ALU0 = inst
    #         elif self.ALU1 is None:
    #             self.ALU1 = inst
    #         else:
    #             return False
    #     elif opcode == 'mulu':
    #         if self.Mult is None:
    #             self.Mult = inst
    #         else:
    #             return False
    #     elif opcode == 'ld' or opcode == 'st':
    #         if self.Mem is None:
    #             self.Mem = inst
    #         else:
    #             return False
    #     elif opcode == 'loop':
    #         if self.Branch is None:
    #             self.Branch = inst
    #         else:
    #             return False
    #     return True
            
    
class AutoExtendList(list):
    def __getitem__(self, index):
        if index >= len(self):
            self.extend([Bundle()] * (index + 1 - len(self)))
        return super().__getitem__(index)

    def __setitem__(self, index, value):
        if index >= len(self):
            self.extend([Bundle()] * (index + 1 - len(self)))
        super().__setitem__(index, value)


class Scheduler:

    p: VLIW470
    schedule: AutoExtendList[Bundle]

    def __init__(self, parent):
        self.p = parent
        self.schedule = AutoExtendList()
        self.finished_cycle = [None] * len(iCache) # record the cycle when each instruction is finished (i.e. visible)




    def schedule(self):

        ''' Step 1: Schedule Instructions according to ASAP'''
        def schedule_single_bb(range: slice, prev_bb_finished_cycle: int):
            depTable = self.p.depTable.table
            iCache = self.p.iCache
            curr_bb_finished_cycle = prev_bb_finished_cycle
            for i, inst in list(enumerate(iCache))[range]:
                deps = depTable[i].localDeps + depTable[i].interLoopDeps + depTable[i].loopInvariantDeps + depTable[i].postLoopDeps
                earliest_cycle = max((self.finished_cycle[dep.producer_id] for dep in deps if dep.producer_id is not None), default=prev_bb_finished_cycle)
                _inst = _Instruction(inst,i)
                while (self.schedule[earliest_cycle].insert(_inst) == False):
                    earliest_cycle += 1
                inst_finished_cycle = earliest_cycle + 1 if inst.opcode != 'mulu' else earliest_cycle + 3
                self.finished_cycle[i] = inst_finished_cycle
                if (inst_finished_cycle > curr_bb_finished_cycle):
                    curr_bb_finished_cycle = inst_finished_cycle
            return curr_bb_finished_cycle
        

        bb0_finished_cycle = schedule_single_bb(self.p.depTable.bb0, 0)
        bb1_finished_cycle = schedule_single_bb(self.p.depTable.bb1, bb0_finished_cycle)
        bb2_finished_cycle = schedule_single_bb(self.p.depTable.bb2, bb1_finished_cycle)

            


    
