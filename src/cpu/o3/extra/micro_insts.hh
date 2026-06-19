/*
 * Copyright (2026) Google, Inc.
 * All rights reserved.
 */

#ifndef __CPU_O3_MICRO_INSTS_HH__
#define __CPU_O3_MICRO_INSTS_HH__

#include <cstdint>
#include <string>
#include <vector>

#include "arch/riscv/regs/int.hh"
#include "cpu/static_inst.hh"
#include "cpu/exec_context.hh"
#include "mem/packet.hh"

namespace gem5
{
namespace o3
{

enum MuOpCode : uint8_t
{
    MU_NONE = 0,
    MU_ADD = 1,
    MU_SUB = 2,
    MU_MUL = 3,
    MU_DIV = 4,
    MU_LD = 5,
    MU_ST = 6
};

class MicroStaticInstBase
{
  public:
    virtual MuOpCode getOpCode() const = 0;
    virtual int64_t getOffset() const = 0;
    virtual ~MicroStaticInstBase() {}
};

/**
 * Base class for synthetic micro-ops.
 * Handles register array setup for O3 backend compatibility.
 */
template<int NumSrcs, int NumDests>
class MicroStaticInst : public StaticInst, public MicroStaticInstBase
{
  protected:
    RegId srcRegs[NumSrcs ? NumSrcs : 1];
    RegId destRegs[NumDests ? NumDests : 1];

  public:
    MicroStaticInst(const char *mnem, OpClass op_class)
        : StaticInst(mnem, op_class)
    {
        _numSrcRegs = NumSrcs;
        _numDestRegs = NumDests;
        // Point the base class's index pointers to our local arrays
        setRegIdxArrays(
            reinterpret_cast<RegIdArrayPtr>(&MicroStaticInst::srcRegs),
            reinterpret_cast<RegIdArrayPtr>(&MicroStaticInst::destRegs)
        );
        flags[IsMicroop] = true;
        flags[IsLastMicroop] = true;
    }

    virtual MuOpCode getOpCode() const { return MU_NONE; }
    virtual int64_t getOffset() const { return 0; }

    void advancePC(PCStateBase &pc) const override { pc.advance(); }
    
    std::string generateDisassembly(Addr pc, const loader::SymbolTable *symtab) const override {
        return mnemonic;
    }
};

/** Integer addition: rd = rs1 + rs2 */
class MuAdd : public MicroStaticInst<2, 1>
{
  public:
    MuAdd(RegIndex rs1, RegIndex rs2, RegIndex rd)
        : MicroStaticInst("mu_add", IntAluOp)
    {
        srcRegs[0] = RiscvISA::intRegClass[rs1];
        srcRegs[1] = RiscvISA::intRegClass[rs2];
        destRegs[0] = RiscvISA::intRegClass[rd];
        _numTypedDestRegs[IntRegClass] = 1;
        flags[IsInteger] = true;
    }

    MuOpCode getOpCode() const override { return MU_ADD; }

    Fault execute(ExecContext *xc, trace::InstRecord *traceData) const override
    {
        uint64_t s1 = xc->getRegOperand(this, 0);
        uint64_t s2 = xc->getRegOperand(this, 1);
        xc->setRegOperand(this, 0, s1 + s2);
        return NoFault;
    }
};

/** Integer subtraction: rd = rs1 - rs2 */
class MuSub : public MicroStaticInst<2, 1>
{
  public:
    MuSub(RegIndex rs1, RegIndex rs2, RegIndex rd)
        : MicroStaticInst("mu_sub", IntAluOp)
    {
        srcRegs[0] = RiscvISA::intRegClass[rs1];
        srcRegs[1] = RiscvISA::intRegClass[rs2];
        destRegs[0] = RiscvISA::intRegClass[rd];
        _numTypedDestRegs[IntRegClass] = 1;
        flags[IsInteger] = true;
    }

    MuOpCode getOpCode() const override { return MU_SUB; }

    Fault execute(ExecContext *xc, trace::InstRecord *traceData) const override
    {
        uint64_t s1 = xc->getRegOperand(this, 0);
        uint64_t s2 = xc->getRegOperand(this, 1);
        xc->setRegOperand(this, 0, s1 - s2);
        return NoFault;
    }
};

/** Integer multiplication: rd = rs1 * rs2 */
class MuMul : public MicroStaticInst<2, 1>
{
  public:
    MuMul(RegIndex rs1, RegIndex rs2, RegIndex rd)
        : MicroStaticInst("mu_mul", IntMultOp)
    {
        srcRegs[0] = RiscvISA::intRegClass[rs1];
        srcRegs[1] = RiscvISA::intRegClass[rs2];
        destRegs[0] = RiscvISA::intRegClass[rd];
        _numTypedDestRegs[IntRegClass] = 1;
        flags[IsInteger] = true;
    }

    MuOpCode getOpCode() const override { return MU_MUL; }

    Fault execute(ExecContext *xc, trace::InstRecord *traceData) const override
    {
        uint64_t s1 = xc->getRegOperand(this, 0);
        uint64_t s2 = xc->getRegOperand(this, 1);
        xc->setRegOperand(this, 0, s1 * s2);
        return NoFault;
    }
};

/** Integer division: rd = rs1 / rs2 */
class MuDiv : public MicroStaticInst<2, 1>
{
  public:
    MuDiv(RegIndex rs1, RegIndex rs2, RegIndex rd)
        : MicroStaticInst("mu_div", IntDivOp)
    {
        srcRegs[0] = RiscvISA::intRegClass[rs1];
        srcRegs[1] = RiscvISA::intRegClass[rs2];
        destRegs[0] = RiscvISA::intRegClass[rd];
        _numTypedDestRegs[IntRegClass] = 1;
        flags[IsInteger] = true;
    }

    MuOpCode getOpCode() const override { return MU_DIV; }

    Fault execute(ExecContext *xc, trace::InstRecord *traceData) const override
    {
        uint64_t s1 = xc->getRegOperand(this, 0);
        uint64_t s2 = xc->getRegOperand(this, 1);
        if (s2 == 0) {
           xc->setRegOperand(this, 0, -1ULL);
        } else {
           xc->setRegOperand(this, 0, s1 / s2);
        }
        return NoFault;
    }
};

/** Memory Load: rd = MEM[rs1 + offset] */
class MuLd : public MicroStaticInst<1, 1>
{
  public:
    MuLd(RegIndex rs1, RegIndex rd, int64_t offset)
        : MicroStaticInst("mu_ld", MemReadOp), _offset(offset)
    {
        srcRegs[0] = RiscvISA::intRegClass[rs1];
        destRegs[0] = RiscvISA::intRegClass[rd];
        _numTypedDestRegs[IntRegClass] = 1;
        flags[IsLoad] = true;
        flags[IsInteger] = true;
    }

    MuOpCode getOpCode() const override { return MU_LD; }
    int64_t getOffset() const override { return _offset; }

    Fault execute(ExecContext *xc, trace::InstRecord *traceData) const override {
        panic("Execute should not be called for timed Load micro-op!");
    }

    Fault initiateAcc(ExecContext *xc, trace::InstRecord *traceData) const override {
        Addr addr = xc->getRegOperand(this, 0) + _offset;
        return xc->initiateMemRead(addr, 8, Request::Flags(), std::vector<bool>());
    }

    Fault completeAcc(PacketPtr pkt, ExecContext *xc, trace::InstRecord *traceData) const override {
        uint64_t data = pkt->getUintX(ByteOrder::little);
        xc->setRegOperand(this, 0, data);
        return NoFault;
    }
  private:
    int64_t _offset;
};

/** Memory Store: MEM[rs1 + offset] = rs2 */
class MuSt : public MicroStaticInst<2, 0>
{
  public:
    MuSt(RegIndex rs1, RegIndex rs2, int64_t offset)
        : MicroStaticInst("mu_st", MemWriteOp), _offset(offset)
    {
        srcRegs[0] = RiscvISA::intRegClass[rs1];
        srcRegs[1] = RiscvISA::intRegClass[rs2];
        flags[IsStore] = true;
        flags[IsInteger] = true;
    }

    MuOpCode getOpCode() const override { return MU_ST; }
    int64_t getOffset() const override { return _offset; }

    Fault execute(ExecContext *xc, trace::InstRecord *traceData) const override {
        Addr addr = xc->getRegOperand(this, 0) + _offset;
        uint64_t data = xc->getRegOperand(this, 1);
        return xc->writeMem(reinterpret_cast<uint8_t*>(&data), 8, addr, 
                           Request::Flags(), nullptr, std::vector<bool>());
    }
  private:
    int64_t _offset;
};

} // namespace o3
} // namespace gem5

#endif // __CPU_O3_MICRO_INSTS_HH__
