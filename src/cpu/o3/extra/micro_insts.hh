/*
 * Copyright (2026) Google, Inc.
 * All rights reserved.
 */

#ifndef __CPU_O3_MICRO_INSTS_HH__
#define __CPU_O3_MICRO_INSTS_HH__

#include <cstdint>
#include <string>
#include <vector>

#include "arch/generic/memhelpers.hh"
#include "arch/riscv/regs/int.hh"
#include "base/logging.hh"
#include "cpu/reg_class.hh"
#include "cpu/static_inst.hh"
#include "cpu/exec_context.hh"
#include "mem/packet.hh"
#include "mem/request.hh"

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
    virtual RegIndex getRd() const { return 0; }
    virtual RegIndex getRs1() const { return 0; }
    virtual RegIndex getRs2() const { return 0; }
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

    RegIndex rd_idx = 0;
    RegIndex rs1_idx = 0;
    RegIndex rs2_idx = 0;
    int64_t offset = 0;

  public:
    MicroStaticInst(const char *mnem, OpClass op_class)
        : StaticInst(mnem, op_class)
    {
        _numSrcRegs = NumSrcs;
        _numDestRegs = NumDests;
        setRegIdxArrays(
            reinterpret_cast<RegIdArrayPtr>(&MicroStaticInst::srcRegs),
            reinterpret_cast<RegIdArrayPtr>(&MicroStaticInst::destRegs)
        );

        flags[IsMicroop] = true;
        flags[IsLastMicroop] = true;
    }

    virtual MuOpCode getOpCode() const { return MU_NONE; }
    int64_t getOffset() const override { return offset; }
    RegIndex getRd() const override { return rd_idx; }
    RegIndex getRs1() const override { return rs1_idx; }
    RegIndex getRs2() const override { return rs2_idx; }

    void advancePC(PCStateBase &pc) const override { pc.advance(); }

    std::string generateDisassembly(Addr pc, const loader::SymbolTable *symtab)
        const override
    {
        return mnemonic;
    }
};

static inline void
checkMuRegIdx(const char *mnem, const char *field, RegIndex idx)
{
    fatal_if(idx >= RiscvISA::int_reg::NumRegs,
        "%s: register index %s=%u out of range (max %u)",
        mnem, field, idx, RiscvISA::int_reg::NumRegs - 1);
}

/** Integer addition: rd = rs1 + rs2 */
class MuAdd : public MicroStaticInst<2, 1>
{
  public:
    MuAdd(RegIndex rs1, RegIndex rs2, RegIndex rd)
        : MicroStaticInst("mu_add", IntAluOp)
    {
        checkMuRegIdx("mu_add", "rs1", rs1);
        checkMuRegIdx("mu_add", "rs2", rs2);
        checkMuRegIdx("mu_add", "rd",  rd);
        this->rs1_idx = rs1;
        this->rs2_idx = rs2;
        this->rd_idx = rd;
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
        RegVal res = s1 + s2;
        void (ExecContext::*setter)(const StaticInst*, int, RegVal) = 
            &ExecContext::setRegOperand;
        (xc->*setter)(this, 0, res);
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
        checkMuRegIdx("mu_sub", "rs1", rs1);
        checkMuRegIdx("mu_sub", "rs2", rs2);
        checkMuRegIdx("mu_sub", "rd",  rd);
        this->rs1_idx = rs1;
        this->rs2_idx = rs2;
        this->rd_idx = rd;
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
        RegVal res = s1 - s2;
        void (ExecContext::*setter)(const StaticInst*, int, RegVal) = 
            &ExecContext::setRegOperand;
        (xc->*setter)(this, 0, res);
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
        checkMuRegIdx("mu_mul", "rs1", rs1);
        checkMuRegIdx("mu_mul", "rs2", rs2);
        checkMuRegIdx("mu_mul", "rd",  rd);
        this->rs1_idx = rs1;
        this->rs2_idx = rs2;
        this->rd_idx = rd;
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
        RegVal res = s1 * s2;
        void (ExecContext::*setter)(const StaticInst*, int, RegVal) = 
            &ExecContext::setRegOperand;
        (xc->*setter)(this, 0, res);
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
        checkMuRegIdx("mu_div", "rs1", rs1);
        checkMuRegIdx("mu_div", "rs2", rs2);
        checkMuRegIdx("mu_div", "rd",  rd);
        this->rs1_idx = rs1;
        this->rs2_idx = rs2;
        this->rd_idx = rd;
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
        RegVal res = (s2 == 0) ? 0 : (s1 / s2);
        void (ExecContext::*setter)(const StaticInst*, int, RegVal) = 
            &ExecContext::setRegOperand;
        (xc->*setter)(this, 0, res);
        return NoFault;
    }
};

/** Load instruction: rd = Mem[rs1 + offset] (64-bit, little-endian) */
class MuLd : public MicroStaticInst<1, 1>
{
  public:
    Request::Flags memAccessFlags;

    MuLd(RegIndex rs1, RegIndex rd, int64_t offset)
        : MicroStaticInst("mu_ld", MemReadOp), memAccessFlags(0)
    {
        checkMuRegIdx("mu_ld", "rs1", rs1);
        checkMuRegIdx("mu_ld", "rd",  rd);
        this->rs1_idx = rs1;
        this->rd_idx = rd;
        this->offset = offset;
        srcRegs[0] = RiscvISA::intRegClass[rs1];
        destRegs[0] = RiscvISA::intRegClass[rd];
        _numTypedDestRegs[IntRegClass] = 1;
        flags[IsLoad] = true;
        flags[IsMemRef] = true;
    }

    Fault execute(ExecContext *xc, trace::InstRecord *traceData) const override
    {
        Addr EA = xc->getRegOperand(this, 0) + offset;
        uint64_t mem = 0;
        Fault fault = readMemAtomicLE(xc, traceData, EA, mem, memAccessFlags);
        if (fault == NoFault) {
            void (ExecContext::*setter)(const StaticInst*, int, RegVal) =
                &ExecContext::setRegOperand;
            (xc->*setter)(this, 0, mem);
        }
        return fault;
    }

    Fault initiateAcc(ExecContext *xc,
                      trace::InstRecord *traceData) const override
    {
        Addr EA = xc->getRegOperand(this, 0) + offset;
        uint64_t mem = 0;
        return initiateMemRead(xc, traceData, EA, mem, memAccessFlags);
    }

    Fault completeAcc(PacketPtr pkt, ExecContext *xc,
                      trace::InstRecord *traceData) const override
    {
        uint64_t mem = 0;
        getMemLE(pkt, mem, traceData);
        void (ExecContext::*setter)(const StaticInst*, int, RegVal) =
            &ExecContext::setRegOperand;
        (xc->*setter)(this, 0, mem);
        return NoFault;
    }
};

/** Store instruction: Mem[rs1 + offset] = rs2 (64-bit, little-endian) */
class MuSt : public MicroStaticInst<2, 0>
{
  public:
    Request::Flags memAccessFlags;

    MuSt(RegIndex rs1, RegIndex rs2, int64_t offset)
        : MicroStaticInst("mu_st", MemWriteOp), memAccessFlags(0)
    {
        checkMuRegIdx("mu_st", "rs1", rs1);
        checkMuRegIdx("mu_st", "rs2", rs2);
        this->rs1_idx = rs1;
        this->rs2_idx = rs2;
        this->offset = offset;
        srcRegs[0] = RiscvISA::intRegClass[rs1];
        srcRegs[1] = RiscvISA::intRegClass[rs2];
        flags[IsStore] = true;
        flags[IsMemRef] = true;
    }

    MuOpCode getOpCode() const override { return MU_ST; }

    Fault execute(ExecContext *xc, trace::InstRecord *traceData) const override
    {
        Addr EA = xc->getRegOperand(this, 0) + offset;
        uint64_t data = xc->getRegOperand(this, 1);
        return writeMemAtomicLE(xc, traceData, data, EA, memAccessFlags,
                                nullptr);
    }

    Fault initiateAcc(ExecContext *xc,
                      trace::InstRecord *traceData) const override
    {
        Addr EA = xc->getRegOperand(this, 0) + offset;
        uint64_t data = xc->getRegOperand(this, 1);
        return writeMemTimingLE(xc, traceData, data, EA, memAccessFlags,
                                nullptr);
    }

    Fault completeAcc(PacketPtr pkt, ExecContext *xc,
                      trace::InstRecord *traceData) const override
    {
        return NoFault;
    }
};

} // namespace o3
} // namespace gem5

#endif // __CPU_O3_MICRO_INSTS_HH__
