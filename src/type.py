from collections import namedtuple
from enum        import Enum
from dataclasses import dataclass, field
from typing      import Union
import sys


RegType = Enum('RegType', ['GENERAL', 'PREDICATE', 'LC', 'EC', 'RRB'])

InstClass = Enum('InstClass', ['ALU', 'Mulu', 'Mem', 'Branch'])

#class RIdx(int):
#    pass

class Reg(namedtuple('Reg', ['type', 'idx'])):
    def __str__(self):
        if self.type == RegType.GENERAL:
            return "x" + str(self.idx)
        elif self.type == RegType.PREDICATE:
            return "p" + str(self.idx)
        else:
            return self.type.name

class RotReg(Reg):
    def __init__(self, _type: RegType, idx: int, iterOffset : int = 0,
                                                 stageOffset: int = 0):
        super().__init__()
        self.iterOffset  = iterOffset
        self.stageOffset = stageOffset
    
    def __str__(self):
        if self.type == RegType.GENERAL:
            return f'x{self.idx + self.iterOffset + self.stageOffset}'
        elif self.type == RegType.PREDICATE:
            return f'p{self.idx + self.iterOffset + self.stageOffset}'
        else:
            raise ValueError(f'rotation register cannot be LC or EC')

@dataclass
class Instruction:
    opcode: str
    rd : Reg
    rs1: Reg
    rs2: Reg
    imm: int
    class_ : InstClass


@dataclass # mutable, since the renameing is done in a later stage
class _Instruction:
    opcode: str
    id: int  # its index in depTable and iCache
    rd: Reg  # destination register after renaming
    rs1: Reg  # source register after renaming
    rs2: Reg
    imm: int

    def __init__(self, opcode: str = None,
                       id : int = None,
                       rd : Reg = None,
                       rs1: Reg = None,
                       rs2: Reg = None,
                       imm: int = None):
        self.opcode = opcode
        self.id = id
        self.rd = rd
        self.rs1 = rs1
        self.rs2 = rs2
        self.imm = imm

    @classmethod
    def from_instruction(cls, instruction: Instruction, id: int):
        return cls(opcode = instruction.opcode,
                   id  = id,
                   rd  = instruction.rd,
                   rs1 = instruction.rs1,
                   rs2 = instruction.rs2,
                   imm = instruction.imm)

    def __str__(self):
        # if (self.opcode == 'mov'):
        #     print(self.rd)
        if self.opcode == 'add' or \
           self.opcode == 'sub' or \
           self.opcode == 'mulu' :
            return f" {self.opcode} {self.rd}, {self.rs1}, {self.rs2}"
        elif self.opcode == 'addi':
            return f" addi {self.rd}, {self.rs1}, {self.imm}"
        elif self.opcode == 'mov':
            if self.rs1 is None:
                return f" mov {self.rd}, {self.imm}"
            else:
                return f" mov {self.rd}, {self.rs1}"
        elif self.opcode == 'ld':
            return f" ld {self.rd}, {self.imm}({self.rs1})"
        elif self.opcode == 'st':
            return f" st {self.rs1}, {self.imm}({self.rs2})"
        elif self.opcode == 'loop':
            return f" loop {self.imm}"


@dataclass
class Bundle:

    insts: list[_Instruction] = field(default_factory=list)
    template: list[InstClass] = field(default_factory=list)

    def insert(self, inst: _Instruction, class_: InstClass):
        ''' try scheduling an instruction '''
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
    def canInsert(self, class_: InstClass):
        if class_ == InstClass.ALU:
            return self.template.count(InstClass.ALU) < 2
        else:
            return class_ not in self.template
    # make both insts and template appear in the following sequence: ALU1, ALU2, Mulu, Mem, Branch
    def sort(self):
        if len(self.insts) <= 1:
            return        
        zipped = zip(self.insts, self.template)
        priority = {InstClass.ALU: 0, InstClass.Mulu: 1, InstClass.Mem: 2, InstClass.Branch: 3}
        zipped = sorted(zipped, key=lambda x: priority[x[1]])
        self.insts, self.template = map(list, zip(*zipped))
    # convert the bundle to a list of strings, in the order of the execution unit, with 'nop' added
    # MUST BE CALLED AFTER sort()!!!
    def to_list(self):
        lst = []
        format = [InstClass.ALU, InstClass.ALU, InstClass.Mulu, InstClass.Mem, InstClass.Branch]
        i = 0
        for cls in format:
            if i < len(self.template) and cls == self.template[i]:
                #lst.append(str(self.insts[i].id) + str(self.insts[i]))
                try:
                    #lst.append(str(self.insts[i].id) + str(self.insts[i]))
                    lst.append(str(self.insts[i]))
                except Exception as e:
                    print(f"An error occurred: {e}")
                    print(self.insts[i].opcode)
                    sys.exit()
                i += 1
            else:
                lst.append('nop')
        assert i == len(self.insts)
        return lst

    def to_list_pip(self, depTable, # `list[DependencyTableEntry]`
                          added: int) -> list:
        lst = []
        format = [InstClass.ALU, InstClass.ALU, InstClass.Mulu, InstClass.Mem, InstClass.Branch]
        i = 0
        for cls in format:
            if i < len(self.template) and cls == self.template[i]:
                try:
                    if self.insts[i].opcode == 'loop':
                        lst.append(f" loop.pip {self.insts[i].imm + added}")
                    elif self.insts[i].id < 0:
                        if self.insts[i].rd.type == RegType.PREDICATE:
                            lst.append(f" mov {self.insts[i].rd}, true")
                        else:
                            lst.append(str(self.insts[i]))
                    elif (s := depTable[self.insts[i].id].stage) is not None:
                        lst.append(f" (p{32 + s}) " + str(self.insts[i]))
                    else:
                        lst.append(str(self.insts[i]))
                except Exception as e:
                    print(f"An error occurred: {e}")
                    print(self.insts[i])
                    sys.exit()
                i += 1
            else:
                lst.append('nop')
        assert i == len(self.insts)
        return lst
    
class AutoExtendList(list):
    def __getitem__(self, index: Union[int, slice]):    
        if isinstance(index, int):
            if index >= len(self):
                self.extend(Bundle() for _ in range(index + 1 - len(self)))
            return super().__getitem__(index)
        elif isinstance(index, slice):
            if index.stop >= len(self):
                self.extend(Bundle() for _ in range(index.stop + 1 - len(self)))
            return AutoExtendList(super().__getitem__(index))
        else:
            raise TypeError(f'invalid index type: {type(index)}')

    def __setitem__(self, index, value):
        if index >= len(self):
            self.extend(Bundle() for _ in range(index + 1 - len(self)))
        super().__setitem__(index, value)
