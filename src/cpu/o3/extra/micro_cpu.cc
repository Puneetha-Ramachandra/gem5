#include "cpu/o3/extra/micro_cpu.hh"
#include "cpu/o3/extra/micro_insts.hh"
#include "cpu/o3/rename.hh"
#include "cpu/o3/iew.hh"
#include "cpu/o3/lsq.hh"
#include "cpu/o3/lsq_unit.hh"
#include "cpu/o3/dyn_inst.hh"
#include "cpu/o3/cpu.hh"
#include "base/output.hh"
#include "sim/sim_exit.hh"

namespace gem5
{
namespace o3
{

MicroCPU::MicroCPU(const MicroCPUParams &params)
    : CPU(params), _dumpStream(nullptr), _dumpEnabled(false)
{
}

void
MicroCPU::injectSequence(const std::vector<StaticInstPtr> &seq)
{
    for (auto &inst : seq) {
        rename.injectedInsts[0].push_back(inst);
    }
    rename.hasInjectedInsts = true;
}

void
MicroCPU::injectAdd(RegIndex rs1, RegIndex rs2, RegIndex rd)
{
    rename.injectedInsts[0].push_back(StaticInstPtr(new MuAdd(rs1, rs2, rd)));
    rename.hasInjectedInsts = true;
}

void
MicroCPU::injectSub(RegIndex rs1, RegIndex rs2, RegIndex rd)
{
    rename.injectedInsts[0].push_back(StaticInstPtr(new MuSub(rs1, rs2, rd)));
    rename.hasInjectedInsts = true;
}

void
MicroCPU::injectMul(RegIndex rs1, RegIndex rs2, RegIndex rd)
{
    rename.injectedInsts[0].push_back(StaticInstPtr(new MuMul(rs1, rs2, rd)));
    rename.hasInjectedInsts = true;
}

void
MicroCPU::injectDiv(RegIndex rs1, RegIndex rs2, RegIndex rd)
{
    rename.injectedInsts[0].push_back(StaticInstPtr(new MuDiv(rs1, rs2, rd)));
    rename.hasInjectedInsts = true;
}

void
MicroCPU::injectLd(RegIndex rs1, RegIndex rd, int64_t offset)
{
    rename.injectedInsts[0].push_back(StaticInstPtr(new MuLd(rs1, rd, offset)));
    rename.hasInjectedInsts = true;
}

void
MicroCPU::injectSt(RegIndex rs1, RegIndex rs2, int64_t offset)
{
    rename.injectedInsts[0].push_back(StaticInstPtr(new MuSt(rs1, rs2, offset)));
    rename.hasInjectedInsts = true;
}

void
MicroCPU::enableDump(const std::string &filename)
{
    _dumpStream = simout.create(filename, true);
    _dumpEnabled = true;
}

void
MicroCPU::disableDump()
{
    if (_dumpStream) {
        simout.close(_dumpStream);
        _dumpStream = nullptr;
    }
    _dumpEnabled = false;
}

void
MicroCPU::playbackStream(const std::string &filename)
{
    // TODO: Implement binary playback reader
}

void
MicroCPU::dumpInst(const DynInstPtr &inst)
{
    if (!_dumpEnabled || !_dumpStream)
        return;

    auto mu_inst = dynamic_cast<const MicroStaticInstBase*>(inst->staticInst.get());
    if (mu_inst) {
        uint8_t opcode = mu_inst->getOpCode();
        int64_t offset = mu_inst->getOffset();
        _dumpStream->stream()->write(reinterpret_cast<const char*>(&opcode), 1);
        _dumpStream->stream()->write(reinterpret_cast<const char*>(&offset), 8);
    }
}

} // namespace o3
} // namespace gem5
