from dataclasses import dataclass, astuple
from math        import ceil
from csv         import DictWriter

from type import RegType, Reg, Instruction, InstClass, _Instruction, Bundle, AutoExtendList


class PipelineScheduler:
    class ReservedTable:
        def __init__(self, ii: int, bb0_finished_cycle: int) -> None:
            self.ii: int = ii
            self.bb0_finished_cycle: int = bb0_finished_cycle
            
            self.table: list[dict[InstClass, int]] = [{clss: 0 for clss in InstClass} for _ in range(ii)]
        
        def markReserved(self, cycle: int, instCls: InstClass) -> None:
            ''' reserve a slot for the instruction '''
            i: int = (cycle - self.bb0_finished_cycle) % self.ii
            # always call `isReserved` prior to `markReserved`
            if self.isReserved(cycle, instCls):
                raise ValueError('Slot already reserved')
            
            self.table[i][instCls] += 1
        
        def isReserved(self, cycle: int, instCls: InstClass) -> bool:
            ''' determine if an execution slot is occupied '''
            i: int = (cycle - self.bb0_finished_cycle) % self.ii
            if instCls == InstClass.ALU:
                return self.table[i][instCls] >= 2
            else:
                return self.table[i][instCls] >= 1
    
    def __init__(self, parent) -> None:
        self.p = parent
        self.schedule: AutoExtendList[Bundle] = AutoExtendList()
        self.ii = self.ii()
        #self.bb0_finished_cycle = 0
        #self.bb1_finished_cycle = 0
        #self.bb2_finished_cycle = 0
        self._schedule()
    
    def ii(self) -> int:
        ''' compute lower bound of II '''        
        def quotient(t: tuple[int, int]) -> int:
            return ceil(t[0] / t[1])

        return max(map(quotient,
                       zip(astuple(self.p.instCount),
                           astuple(self.p.exUnitCount))))
    def _schedule(self):
        ''' schedule bb0 using old scheme '''
        iCache = self.p.iCache
        finished_cycle = [None] * len(iCache) # record the cycle when each instruction is finished (i.e. visible)
        depTable = self.p.depTable.table
        bb1 = self.p.depTable.bb1
        bb0_finished_cycle = 0
        bb1_finished_cycle = 0
        bb2_finished_cycle = 0
        numStage = 0

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

        def schedule_bb1() -> bool:
            ''' schedule bb1

            There are 2 cases where one has to increment `self.ii` and re-
            schedule BB1:
            1. the schedule does not satisfy Eq. 2, or
            2. instructions across iterations occupy the same `ReservedTable`
               slot
            '''
            nonlocal bb1_finished_cycle

            localBb1FinishedCycle = bb0_finished_cycle
            reservedTbl = self.ReservedTable(self.ii,
                                             bb0_finished_cycle)    
            for i, inst in list(enumerate(iCache))[slice(bb1.start, bb1.stop - 1)]:
                deps = depTable[i].localDeps     \
                     + depTable[i].interLoopDeps \
                     + depTable[i].loopInvariantDeps
                earliest_cycle = max((finished_cycle[dep.producer_id] for dep in deps
                                                                          if dep.producer_id is not None),
                                     default=bb0_finished_cycle)
                if earliest_cycle < bb0_finished_cycle:
                    earliest_cycle = bb0_finished_cycle
                
                failedSchedule = 0
                while reservedTbl.isReserved(cycle = earliest_cycle,
                                             instCls = inst.class_):
                    earliest_cycle += 1
                    failedSchedule += 1
                    if failedSchedule == self.ii:
                        return False
                
                instFinishedCycle = earliest_cycle + 3 if inst.opcode == 'mulu' else earliest_cycle + 1
                finished_cycle[i] = instFinishedCycle
                localBb1FinishedCycle = max(localBb1FinishedCycle, instFinishedCycle)
                # check Eq. 2
                for j in range(self.p.depTable.bb0.stop, i+1): # possibly self-dependent
                    for dep in depTable[j].interLoopDeps:
                        if dep.producer_id_interloop == i:
                            SC = finished_cycle[j] - 3 if iCache[j].opcode == 'mulu' else finished_cycle[j] - 1
                            #  S(P) + λ(P)       > II      + S(C)
                            if instFinishedCycle > self.ii + SC:
                                return False                    
                reservedTbl.markReserved(earliest_cycle, inst.class_)
                _inst = _Instruction.from_instruction(inst, i)
                self.schedule[earliest_cycle].insert(_inst, inst.class_)
            bb1_finished_cycle = localBb1FinishedCycle
            return True

        bb0_finished_cycle = schedule_single_bb(self.p.depTable.bb0, 0)
        if (bb1.stop - bb1.start) != 0:
            while not schedule_bb1():
                print(f'II = {self.ii} is not enough, incrementing II')
                # revert previous changes to self.schedule and finished_cycle
                self.schedule = self.schedule[ :bb0_finished_cycle]
                finished_cycle = finished_cycle[ :bb0_finished_cycle]

                self.ii += 1
            # pad `self.schedule` with empty bundle(s) towards a length of multiple
            # of `self.ii`
            while (bb1_finished_cycle - bb0_finished_cycle) % self.ii:
                bb1_finished_cycle += 1
            loop_inst = _Instruction.from_instruction(self.p.iCache[bb1.stop - 1], bb1.stop - 1)
            loop_inst.imm = bb0_finished_cycle
            self.schedule[bb1_finished_cycle - 1].insert(loop_inst, InstClass.Branch) # this is guaranteed to return true
            bb2_finished_cycle = schedule_single_bb(self.p.depTable.bb2, bb1_finished_cycle)
            numStage = (bb1_finished_cycle - bb0_finished_cycle) // self.ii
        
        ''' rename rd registers'''
        self.sort()
        class FreshRegGenerator:
            cnt: int = 0
            def __call__(self) -> Reg:
                self.cnt += 1
                return Reg(RegType.GENERAL, self.cnt)
        class FreshRotGenerator:
            cnt: int = 32
            def __init__(self, numStage):
                self.numStage = numStage
            def __call__(self) -> Reg:
                tmp = self.cnt
                self.cnt += (self.numStage + 1)
                return Reg(RegType.GENERAL, tmp)
        freshReg = FreshRegGenerator()
        freshRot = FreshRotGenerator(numStage)
        for bundle in self.schedule:
            for inst in bundle.insts:
                if (inst.rd is not None) and inst.rd.type == RegType.GENERAL:
                    inst.rd = freshReg()
                    depTable[inst.id].renamedDest = inst.rd

        


    
    def sort(self) -> None:
        for bundle in self.schedule:
            bundle.sort()

    def to_csv(self, output_path: str):
        self.sort() # Why?
        with open(output_path, 'w') as f:
            fieldnames = ['ALU1', 'ALU2', 'Mulu', 'Mem', 'Branch']
            writer = DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for bundle in self.schedule:
                lst = bundle.to_list()
                writer.writerow({'ALU1': lst[0], 'ALU2': lst[1], 'Mulu': lst[2], 'Mem': lst[3], 'Branch': lst[4]})
