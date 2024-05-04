from dataclasses import dataclass

from type import RegType, Reg, Instruction, InstClass
from DependencyTable   import DependencyTable
from SimpleScheduler   import SimpleScheduler
from PipelineScheduler import PipelineScheduler

class VLIW470:
    @dataclass
    class Count:
        ALU: int
        MUL: int
        MEM: int
        BR: int
    
    iCache: list[Instruction]

    rrb: int # rotating register base
    lc : int # loop   count register
    ec : int # epilog count register
    depTable: DependencyTable
    simpleScheduler: SimpleScheduler
    pipelineScheduler: PipelineScheduler

    def __init__(self, insts: list[str]) -> None:
        self.exUnitCount = self.Count(2,1,1,1)
        self.instCount   = self.Count(0,0,0,0)
        
        self.iCache = []
        for inst in insts:
            self.iCache.append(self.decode(inst))
        self.depTable = DependencyTable(self.iCache)
        self.simpleScheduler   = SimpleScheduler(self)
        self.pipelineScheduler = PipelineScheduler(self)

    
    def parseReg(self, reg: str) -> Reg:
        ''' parse a register '''
        if reg[0] == 'x':
            return Reg(RegType.GENERAL, int(reg[1:]))
        elif reg[0] == 'p':
            return Reg(RegType.PREDICATE, int(reg[1:]))
        elif reg == 'LC':
            return Reg(RegType.LC, None)

    def decode(self, inst: str) -> Instruction:
        ''' decode an instruction '''
        opcode, regs = inst.split(' ', 1)
        if opcode == 'add' or \
           opcode == 'sub':
            self.instCount.ALU += 1

            rd, rs1, rs2 = map(lambda x : self.parseReg(x.strip()), regs.split(','))
            return Instruction(opcode = opcode,
                               rd = rd,
                               rs1 = rs1,
                               rs2 = rs2,
                               imm = None,
                               class_ = InstClass.ALU) 
        elif opcode == 'mulu':
            self.instCount.MUL += 1

            rd, rs1, rs2 = map(lambda x : self.parseReg(x.strip()), regs.split(','))
            return Instruction(opcode = opcode,
                               rd = rd,
                               rs1 = rs1,
                               rs2 = rs2,
                               imm = None,
                               class_ = InstClass.Mulu) 
        elif opcode == 'addi':
            self.instCount.ALU += 1

            rd, rs1, imm = map(lambda x : x.strip(), regs.split(','))
            return Instruction(opcode = 'addi',
                               rd = self.parseReg(rd),
                               rs1 = self.parseReg(rs1),
                               rs2 = None,
                               imm = int(imm),
                               class_ = InstClass.ALU)
        elif opcode == 'ld':
            self.instCount.MEM += 1

            rd, addr = regs.split(',', 1)
            offset, base = addr.split('(', 1)
            return Instruction(opcode = 'ld',
                               rd = self.parseReg(rd.strip()),
                               rs1 = self.parseReg(base.strip()[ :-1]), # get rid of ')'
                               rs2 = None,
                               imm = int(offset, 0),
                               class_ = InstClass.Mem) # Offset may be a hex.
        elif opcode == 'st':
            self.instCount.MEM += 1
            # RISC-V semantics of `st rs2, offset(rs1)`: MEM[rs1 + offset] ← rs2
            # VLIW470 adopts the "opposite" convention, i.e,
            #     `st rs1, offset(rs2)`: MEM[rs2 + offset] ← rs1
            content, addr = regs.split(',', 1)
            offset, base = addr.split('(', 1)
            return Instruction(opcode = 'st',
                               rd = None,
                               rs1 = self.parseReg(content.strip()),
                               rs2 = self.parseReg(base.strip()[ :-1]), # get rid of ')'
                               imm = int(offset, 0),
                               class_ = InstClass.Mem) # Offset may be a hex.
        elif opcode == 'loop':
            self.instCount.BR += 1

            return Instruction(opcode = 'loop',
                               rd = None,
                               rs1 = None,
                               rs2 = None,
                               imm = int(regs.strip()),
                               class_ = InstClass.Branch) # jump address
        elif opcode == 'mov':
            self.instCount.ALU += 1 # correct?

            rd, rs1 = map(lambda x : x.strip(), regs.split(','))
            if rs1[0] == 'x' or rs1 == 'LC': # `mov rd, rs1`
                return Instruction(opcode = 'mov',
                                   rd = self.parseReg(rd),
                                   rs1 = self.parseReg(rs1),
                                   rs2 = None,
                                   imm = None,
                                   class_ = InstClass.ALU)
            else: # `mov rd, imm`
                return Instruction(opcode = 'mov',
                                   rd = self.parseReg(rd),
                                   rs1 = None,
                                   rs2 = None,
                                   imm = int(rs1, 0),
                                   class_ = InstClass.ALU)
