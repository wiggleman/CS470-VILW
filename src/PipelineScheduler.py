from dataclasses import dataclass, astuple
from math        import ceil
from copy        import deepcopy
from csv         import DictWriter
import json

from DependencyTable import Dep
from type import RegType, Reg, RotReg, Instruction, InstClass, _Instruction, Bundle, AutoExtendList


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
        self.finalSchedule: list[Bundle] = []
        self.added = 0
        self.ii = self.ii()
        #self.bb0_finished_cycle = 0
        #self.bb1_finished_cycle = 0
        #self.bb2_finished_cycle = 0
        self._schedule()
        
    
    def ii(self) -> int:
        ''' compute lower bound of II '''        
        def quotient(t: tuple[int, int]) -> int:
            #print(ceil(t[0] / t[1]))
            return ceil(t[0] / t[1])

        tmp =  max(map(quotient,
                       zip(astuple(self.p.instCount),
                           astuple(self.p.exUnitCount))))
        #print('ii:', tmp)
        return tmp
    
    def ii(self):
        instCount = {clss: 0 for clss in InstClass}
        exUnitCount = {InstClass.ALU: 2, InstClass.Mulu: 1, InstClass.Mem: 1, InstClass.Branch: 1}
        for inst in self.p.iCache[self.p.depTable.bb1]:
            instCount[inst.class_] += 1
        return max( ceil(instCount[clss] / exUnitCount[clss]) for clss in InstClass)
        
    
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
                #print('finished_cycle:', finished_cycle)
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
                finished_cycle[ :bb0_finished_cycle].extend([None] * (len(iCache) - bb0_finished_cycle))

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
        
        class FreshRegGenerator:
            base: int = 0

            def __call__(self) -> Reg:
                self.base += 1
                return Reg(RegType.GENERAL, self.base)
        
        class FreshRotGenerator:
            base: int = 32

            def __init__(self, numStage):
                self.numStage = numStage
            
            def __call__(self) -> Reg:
                tmp = self.base
                self.base += (self.numStage + 1)
                return RotReg(RegType.GENERAL, tmp)
        # maintain scheduling order
        self.sort()
        ''' step 2.0 mask independent rs in BB1 '''
        nullReg = RotReg(RegType.GENERAL, -1)
        for bundle in self.schedule:
            for inst in bundle.insts:
                # unconditinally mask rd
                if inst.rd is not None and inst.rd.type == RegType.GENERAL:
                    inst.rd = nullReg
                # mask rs without dependency
                deps = set(map(lambda dep: dep.reg(),
                       set(depTable[inst.id].localDeps)         \
                     | set(depTable[inst.id].interLoopDeps)     \
                     | set(depTable[inst.id].loopInvariantDeps) \
                     | set(depTable[inst.id].postLoopDeps)
                ))
                if inst.rs1 is not None             and \
                   inst.rs1.type == RegType.GENERAL and \
                   inst.rs1 not in deps:
                    inst.rs1 = nullReg
                if inst.rs2 is not None             and \
                   inst.rs2.type == RegType.GENERAL and \
                   inst.rs2 not in deps:
                    inst.rs2 = nullReg     
        ''' step 2.1 rename rd in BB1'''
        freshRot = FreshRotGenerator(numStage)
        # Attention: only rename rd in BB1 now
        for idx, bundle in enumerate(self.schedule[bb0_finished_cycle:bb1_finished_cycle]):
            for inst in bundle.insts:
                depTable[inst.id].stage = idx // self.ii # `idx` is not PC!
                if (inst.rd is not None) and inst.rd.type == RegType.GENERAL:
                    tmp = freshRot()

                    inst.rd = tmp
                    depTable[inst.id].renamedDest = tmp
        ''' step 2.2 rename loop-invariant rs in BB1 '''
        freshReg = FreshRegGenerator()
        
        loopInvariantProducers: dict[int, Reg] = {}
        # 2.2.1 traverse BB1 to assign all loop-invariant dependency with fresh
        #       static register
        for bundle in self.schedule[bb0_finished_cycle:bb1_finished_cycle]:
            for inst in bundle.insts:
                for dep in depTable[inst.id].loopInvariantDeps:
                    if dep.producer_id not in loopInvariantProducers:
                        loopInvariantProducers[dep.producer_id] = freshReg()
        # 2.2.2 rename producer rd of loop-invariant dependency in BB0
        for bundle in self.schedule[ :bb0_finished_cycle]:
            for inst in bundle.insts:
                if inst.id in loopInvariantProducers:
                    inst.rd = loopInvariantProducers[inst.id]
                    depTable[inst.id].renamedDest = loopInvariantProducers[inst.id]                    
        ''' step 2.3 link operands to renamed registers '''
        # 2.3.1 loop invariant dependency: go back to BB1 to replace loop-
        #                                  invariant rs with renamed registers
        for bundle in self.schedule[ bb0_finished_cycle:bb1_finished_cycle ]:
            for inst in bundle.insts:
                for dep in depTable[inst.id].loopInvariantDeps:
                    if (inst.rs1 is not None) and inst.rs1.idx == dep.consumer_reg.idx:
                        inst.rs1 = depTable[dep.producer_id].renamedDest
                    if (inst.rs2 is not None) and inst.rs2.idx == dep.consumer_reg.idx:
                        inst.rs2 = depTable[dep.producer_id].renamedDest
        # local dependency: increment stage offset
        for bundle in self.schedule[bb0_finished_cycle:bb1_finished_cycle]:
            for inst in bundle.insts:
                for dep in depTable[inst.id].localDeps:
                    if (inst.rs1 is not None) and inst.rs1.idx == dep.consumer_reg.idx:
                        tmp: Reg = deepcopy(depTable[dep.producer_id].renamedDest)
                        tmp.stageOffset += depTable[inst.id].stage \
                                        -  depTable[dep.producer_id].stage
                        inst.rs1 = tmp
                    
                    if (inst.rs2 is not None) and inst.rs2.idx == dep.consumer_reg.idx:
                        tmp: Reg = deepcopy(depTable[dep.producer_id].renamedDest)
                        tmp.stageOffset += depTable[inst.id].stage \
                                        -  depTable[dep.producer_id].stage
                        inst.rs2 = tmp
        # interloop dependency: increment stage offset
        bb1bb0ProducerMap: dict[int, int] = {} # key: `producer_id_interloop`; value: `producer_id``
        for idx, bundle in enumerate(self.schedule[bb0_finished_cycle:bb1_finished_cycle]):
            for inst in bundle.insts:
                for dep in depTable[inst.id].interLoopDeps:
                    bb1bb0ProducerMap[dep.producer_id_interloop] = dep.producer_id
                    
                    if (inst.rs1 is not None) and inst.rs1.idx == dep.consumer_reg.idx:                          
                        tmp: Reg = deepcopy(depTable[dep.producer_id_interloop].renamedDest)
                        tmp.stageOffset += depTable[inst.id].stage \
                                         - depTable[dep.producer_id_interloop].stage
                        tmp.iterOffset += 1
                        inst.rs1 = tmp
                    
                    if (inst.rs2 is not None) and inst.rs2.idx == dep.consumer_reg.idx:
                        tmp: Reg = deepcopy(depTable[dep.producer_id_interloop].renamedDest)
                        tmp.stageOffset += depTable[inst.id].stage \
                                        -  depTable[dep.producer_id_interloop].stage
                        tmp.iterOffset += 1
                        inst.rs2 = tmp
        ''' step 2.4 rename registers in BB0 and BB2 '''
        # 2.4.1 interloop dependency: ???
        for producer_id_interloop, producer_id in bb1bb0ProducerMap.items():
            if producer_id is None:
                continue
            producerCycle = finished_cycle[producer_id] - 3 if iCache[producer_id].opcode == 'mulu' else finished_cycle[producer_id] - 1
            flag = False
            for inst in self.schedule[producerCycle].insts:
                if (inst.id == producer_id):
                    tmp = deepcopy(depTable[producer_id_interloop].renamedDest)
                    tmp.iterOffset  = 1
                    tmp.stageOffset = -depTable[producer_id_interloop].stage
                    inst.rd = tmp
                    depTable[inst.id].renamedDest = tmp
                    flag = True
                    break
            assert flag
        # 2.4.2 local dependency: same as non-pipelined scheduling
        for idx in list(range(bb0_finished_cycle)) + \
                   list(range(bb1_finished_cycle, bb2_finished_cycle)):
            bundle = self.schedule[idx]
            for inst in bundle.insts:
                if inst.rd == nullReg:
                    tmp = freshReg()
                    inst.rd = tmp
                    depTable[inst.id].renamedDest = tmp

        for idx in list(range(bb0_finished_cycle)) + \
                   list(range(bb1_finished_cycle, bb2_finished_cycle)):
            bundle = self.schedule[idx]
            for inst in bundle.insts:
                for dep in depTable[inst.id].localDeps:
                    if (inst.rs1 is not None) and inst.rs1.idx == dep.consumer_reg.idx:
                        tmp = depTable[dep.producer_id].renamedDest
                        inst.rs1 = tmp
                    if (inst.rs2 is not None) and inst.rs2.idx == dep.consumer_reg.idx:
                        tmp = depTable[dep.producer_id].renamedDest
                        inst.rs2 = tmp
        # 2.4.3 post dependency
        for bundle in self.schedule[bb1_finished_cycle:bb2_finished_cycle]:
            for inst in bundle.insts:
                for dep in depTable[inst.id].postLoopDeps:
                    if (inst.rs1 is not None) and inst.rs1.idx == dep.consumer_reg.idx:
                        tmp = deepcopy(depTable[dep.producer_id].renamedDest)
                        tmp.iterOffset  = 0
                        tmp.stageOffset = numStage - 1 - depTable[dep.producer_id].stage
                        inst.rs1 = tmp
                    
                    if (inst.rs2 is not None) and inst.rs2.idx == dep.consumer_reg.idx:
                        tmp = deepcopy(depTable[dep.producer_id].renamedDest)
                        tmp.iterOffset  = 0
                        tmp.stageOffset = numStage - 1 - depTable[dep.producer_id].stage
                        inst.rs2 = tmp
        # 2.4.4 loop-invariant dependency
        for bundle in (self.schedule[bb1_finished_cycle:bb2_finished_cycle]): # There shall be no loop-invariant dependency in BB0.
            for inst in bundle.insts:
                for dep in depTable[inst.id].loopInvariantDeps:
                    if (inst.rs1 is not None) and inst.rs1.idx == dep.consumer_reg.idx:
                        inst.rs1 = depTable[dep.producer_id].renamedDest
                    
                    if (inst.rs2 is not None) and inst.rs2.idx == dep.consumer_reg.idx:
                        inst.rs2 = depTable[dep.producer_id].renamedDest
        # 2.4.5 unused register
        for bundle in self.schedule:
            for inst in bundle.insts:
                if (inst.rs1 is not None) and inst.rs1 == nullReg:
                    inst.rs1 = freshReg()
                
                if (inst.rs2 is not None) and inst.rs2 == nullReg:
                    inst.rs2 = freshReg()
        ''' step 3 prepare loop predicate '''
        ''' self.schedule & bb_finished_cycle are read only from here on'''
        bb0Schedule = deepcopy(self.schedule[ :bb0_finished_cycle])
        if bb1.stop - bb1.start == 0:
            while (len(bb0Schedule) > 0 and len(bb0Schedule[-1].insts) ==0 ):
                bb0Schedule.pop()
        #print('BB0 finishes at', bb0_finished_cycle, 'length:', len(bb0Schedule))
        movInst1 = _Instruction(opcode = 'mov', id = -1, rd = Reg(RegType.PREDICATE, 32), imm = 1)
        movInst2 = _Instruction(opcode = 'mov', id = -1, rd = Reg(RegType.EC, None), imm = numStage - 1)
        
        if bb1.stop - bb1.start != 0:
            while bb0Schedule[-1].insert(movInst2, InstClass.ALU) == False:
                bb0Schedule.append(Bundle())
                self.added += 1
            while bb0Schedule[-1].insert(movInst1, InstClass.ALU) == False:
                bb0Schedule.append(Bundle())
                self.added += 1

        
        bb1Schedule: list[Bundle] = []
        print('ii:', self.ii, 'numStage:', numStage)
        for idx in range(self.ii):
            bundle = Bundle()
            for stage in range(numStage):
                bundle.insts.extend(self.schedule[bb0_finished_cycle + stage * self.ii + idx].insts)
                bundle.template.extend(self.schedule[bb0_finished_cycle + stage * self.ii + idx].template)
            bb1Schedule.append(bundle)

        bb2Schedule = deepcopy(self.schedule[bb1_finished_cycle:bb2_finished_cycle])
        while len(bb2Schedule) > 0 and len(bb2Schedule[-1].insts) == 0:
            bb2Schedule.pop()
        
        self.finalSchedule = bb0Schedule
        if bb1.stop - bb1.start != 0:
            self.finalSchedule = self.finalSchedule \
                               + bb1Schedule        \
                               + bb2Schedule

    def sort(self) -> None:
        for bundle in self.schedule:
            bundle.sort()

    # def to_csv(self, output_path: str):
    #     self.sort() # Why
    #     with open(output_path, 'w') as f:
    #         fieldnames = ['ALU1', 'ALU2', 'Mulu', 'Mem', 'Branch']
    #         writer = DictWriter(f, fieldnames=fieldnames)
    #         writer.writeheader()
    #         for bundle in self.schedule:
    #             lst = bundle.to_list()
    #             writer.writerow({'ALU1': lst[0], 'ALU2': lst[1], 'Mulu': lst[2], 'Mem': lst[3], 'Branch': lst[4]})


    def to_csv(self, output_path: str):
        for bundle in self.finalSchedule:
            bundle.sort()
        with open(output_path, 'w') as f:
            fieldnames = ['ALU1', 'ALU2', 'Mulu', 'Mem', 'Branch']
            writer = DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for bundle in self.finalSchedule:
                lst = bundle.to_list_pip(self.p.depTable.table, self.added)
                writer.writerow({'ALU1': lst[0], 'ALU2': lst[1], 'Mulu': lst[2], 'Mem': lst[3], 'Branch': lst[4]})

    def to_json(self, output_path):
        for bundle in self.finalSchedule:
            bundle.sort()
        
        with open(output_path, 'w') as f:
            json.dump([bundle.to_list_pip(self.p.depTable.table, self.added) for bundle in self.finalSchedule], f,
                      indent=4)
