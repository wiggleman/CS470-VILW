from type import RegType, Reg, Instruction, InstClass, _Instruction, Bundle, AutoExtendList
from itertools import islice
import json
import csv


class SimpleScheduler:

    schedule: AutoExtendList[Bundle]

    def __init__(self, parent):
        self.p = parent
        self.schedule = AutoExtendList()
        self.bb0_finished_cycle = 0
        self.bb1_finished_cycle = 0
        self.bb2_finished_cycle = 0
        self._schedule()


    def sort(self):
        for bundle in self.schedule:
            bundle.sort()

    def to_json(self, output_path):
        self.sort()
        with open(output_path, 'w') as f:
            json.dump([bundle.to_list() for bundle in self.schedule], f,
                      indent=4)
    def to_csv(self, output_path):
        self.sort()
        with open(output_path, 'w') as f:
            fieldnames = ['ALU1', 'ALU2', 'Mulu', 'Mem', 'Branch']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for bundle in self.schedule:
                lst = bundle.to_list()
                writer.writerow({'ALU1': lst[0], 'ALU2': lst[1], 'Mulu': lst[2], 'Mem': lst[3], 'Branch': lst[4]})


    def _schedule(self):

        ''' Step 1.1: schedule Instructions according to ASAP'''
        iCache = self.p.iCache
        finished_cycle = [None] * len(iCache) # record the cycle when each instruction is finished (i.e. visible)
        depTable = self.p.depTable.table

        def schedule_single_bb(range: slice, prev_bb_finished_cycle: int):
            ''' schedule a single basic block '''
            curr_bb_finished_cycle = prev_bb_finished_cycle
            for i, inst in list(enumerate(iCache))[range]:
                deps = depTable[i].localDeps + depTable[i].interLoopDeps + depTable[i].loopInvariantDeps + depTable[i].postLoopDeps
                earliest_cycle = max((finished_cycle[dep.producer_id] for dep in deps if dep.producer_id is not None),
                                     default=prev_bb_finished_cycle)
                if earliest_cycle < prev_bb_finished_cycle:
                    earliest_cycle = prev_bb_finished_cycle
                _inst = _Instruction.from_instruction(inst,i)
                while not self.schedule[earliest_cycle].insert(_inst, inst.class_):
                    earliest_cycle += 1
                inst_finished_cycle = earliest_cycle + 1 if inst.opcode != 'mulu' else earliest_cycle + 3
                finished_cycle[i] = inst_finished_cycle
                if (inst_finished_cycle > curr_bb_finished_cycle):
                    curr_bb_finished_cycle = inst_finished_cycle
            return curr_bb_finished_cycle
        

        self.bb0_finished_cycle = schedule_single_bb(self.p.depTable.bb0, 0)
        bb1 = self.p.depTable.bb1
        if (bb1.stop != bb1.start):
            # schedule bb1 except the last instruction, i.e. the loop instruction, which is to be scheduled using another strategy

            self.bb1_finished_cycle = schedule_single_bb(slice(bb1.start, bb1.stop - 1) , self.bb0_finished_cycle)
            self.bb2_finished_cycle = schedule_single_bb(self.p.depTable.bb2, self.bb1_finished_cycle)

            ''' Step 1.2: properly delay the loop instruction, so that equation 2 is satisfied for all bb1 insts'''
            ii = self.bb1_finished_cycle - self.bb0_finished_cycle
            max_diff = 0

            for cycle, bundle in islice(enumerate(self.schedule), self.bb0_finished_cycle, self.bb1_finished_cycle):
                for inst in bundle.insts:
                    for dep in depTable[inst.id].interLoopDeps:
                        sp_id = dep.producer_id_interloop # a interloop dep is guaranteed to have a produer_id_interloop
                        sp_finished_cycle = finished_cycle[sp_id] # equivalent to S(p) + lambda(p)\
                        diff = sp_finished_cycle - (ii + cycle) # equation 2: S(p) + lambda(p) - (ii + S(c)) should <= 0
                        if diff > max_diff:
                            max_diff = diff
            # we need to delay the loop instruction by max_diff cycles
            for _ in range(max_diff):
                self.schedule.insert(self.bb1_finished_cycle, Bundle())
                self.bb1_finished_cycle += 1
                self.bb2_finished_cycle += 1
 

        ''' Step 2.1: Rename registers'''
        self.sort()
        class FreshRegGenerator:
            ''' fresh register generator '''
            cnt: int = 0
            def __call__(self) -> Reg:
                self.cnt += 1
                return Reg(RegType.GENERAL, self.cnt)
        freshReg = FreshRegGenerator()
        nullReg = Reg(RegType.GENERAL, -1)
        for bundle in self.schedule:
            for inst in bundle.insts:
                if (inst.rd is not None) and inst.rd.type == RegType.GENERAL:
                    inst.rd = freshReg()
                    depTable[inst.id].renamedDest = inst.rd

        ''' Step 2.2: link the operands to the renamed registers'''
        for bundle in self.schedule:
            for inst in bundle.insts:
                deps = depTable[inst.id].localDeps         \
                     + depTable[inst.id].interLoopDeps     \
                     + depTable[inst.id].loopInvariantDeps \
                     + depTable[inst.id].postLoopDeps
                if inst.rs1 is not None:
                    prodId = next((dep.producer_id for dep in deps if dep.consumer_reg == inst.rs1), None)
                    if prodId is None:
                        inst.rs1 = nullReg
                    else:
                        inst.rs1 = depTable[prodId].renamedDest
                if inst.rs2 is not None:
                    prodId = next((dep.producer_id for dep in deps if dep.consumer_reg == inst.rs2), None)
                    if prodId is None:
                        inst.rs2 = nullReg
                    else:
                        inst.rs2 = depTable[prodId].renamedDest

        ''' Step 2.3: fix the interloop dependencies '''
        if (bb1.stop != bb1.start):
            interLoopDeps = [entry.interLoopDeps for entry in depTable[bb1]]
            interLoopDeps = [item for sublist in interLoopDeps for item in sublist] # flatten the list
            interLoopDeps = set(interLoopDeps) # remove duplicates
            movFinishedCycle = self.bb1_finished_cycle
            oldBb1FinishedCycle = self.bb1_finished_cycle # this is the starting point of all added mov instruction
            for dep in interLoopDeps:
                moveInst = _Instruction(id = -1, opcode = "mov", 
                                        rd = depTable[dep.producer_id].renamedDest, 
                                        rs1 = depTable[dep.producer_id_interloop].renamedDest)
                ProdFinishedCycle = finished_cycle[dep.producer_id_interloop]
                currCycle = oldBb1FinishedCycle - 1
                while currCycle < ProdFinishedCycle or \
                   self.schedule[currCycle].canInsert(InstClass.ALU) == False:
                    currCycle += 1
                    if currCycle >= self.bb1_finished_cycle:
                        self.schedule.insert(currCycle, Bundle())
                        self.bb1_finished_cycle += 1
                        self.bb2_finished_cycle += 1
                #print(self.schedule[currCycle])
                self.schedule[currCycle].insert(moveInst, InstClass.ALU)
            # only now do we schedule the loop instruction
            loop_inst = _Instruction.from_instruction(self.p.iCache[bb1.stop - 1], bb1.stop - 1)
            loop_inst.imm = self.bb0_finished_cycle
            self.schedule[self.bb1_finished_cycle - 1].insert(loop_inst, InstClass.Branch) # this is guaranteed to return true

        ''' Step 2.4: rename all null register '''

        for bundle in self.schedule:
            for inst in bundle.insts:
                if inst.rs1 == nullReg:
                    inst.rs1 = freshReg()
                if inst.rs2 == nullReg:
                    inst.rs2 = freshReg()
         

                        





            


    
