#include <fstream>
#include <ios>
#include <vector>

#include "cpu/o3/extra/micro_cpu.hh"
#include "cpu/o3/extra/micro_insts.hh"
#include "cpu/o3/rename.hh"
#include "cpu/o3/iew.hh"
#include "cpu/o3/lsq.hh"
#include "cpu/o3/lsq_unit.hh"
#include "cpu/o3/dyn_inst.hh"
#include "cpu/o3/cpu.hh"
#include "base/logging.hh"
#include "base/output.hh"
#include "debug/Rename.hh"
#include "sim/sim_exit.hh"

namespace gem5
{
namespace o3
{

MicroCPU::MicroCPU(const MicroCPUParams &params)
    : CPU(params), _dumpStream(nullptr), _dumpEnabled(false)
{
    fatal_if(params.numThreads != 1,
        "MicroCPU only supports single-threaded execution (numThreads=1)");
}

void
MicroCPU::injectSequence(const std::vector<StaticInstPtr> &seq)
{
    for (auto &inst : seq)
        rename.injectedInsts[0].push_back(inst);
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
MicroCPU::startStreamingPlayback(const std::string &path)
{
    if (_playbackStream.is_open())
        _playbackStream.close();
    _playbackStream.open(path, std::ios::binary);
    if (!_playbackStream.is_open())
        warn("MicroCPU: startStreamingPlayback could not open %s", path);
}

void
MicroCPU::stopStreamingPlayback()
{
    if (_playbackStream.is_open())
        _playbackStream.close();
}

void
MicroCPU::drainStreamIntoRename(unsigned maxInsts)
{
    if (!_playbackStream.is_open() || _playbackStream.peek() == EOF)
        return;

    unsigned count = 0;
    while (count < maxInsts && _playbackStream.peek() != EOF) {
        uint8_t opcode;
        int64_t offset;
        uint8_t rd, rs1, rs2;

        _playbackStream.read(reinterpret_cast<char*>(&opcode), 1);
        _playbackStream.read(reinterpret_cast<char*>(&offset), 8);
        _playbackStream.read(reinterpret_cast<char*>(&rd),     1);
        _playbackStream.read(reinterpret_cast<char*>(&rs1),    1);
        _playbackStream.read(reinterpret_cast<char*>(&rs2),    1);

        if (!_playbackStream) {
            warn("MicroCPU: streaming playback truncated; stopping");
            _playbackStream.close();
            break;
        }

        StaticInstPtr inst = nullptr;
        switch (static_cast<MuOpCode>(opcode)) {
            case MU_ADD: inst = new MuAdd(rs1, rs2, rd); break;
            case MU_SUB: inst = new MuSub(rs1, rs2, rd); break;
            case MU_MUL: inst = new MuMul(rs1, rs2, rd); break;
            case MU_DIV: inst = new MuDiv(rs1, rs2, rd); break;
            case MU_LD:  inst = new MuLd(rs1, rd, offset); break;
            case MU_ST:  inst = new MuSt(rs1, rs2, offset); break;
            default: break; // MU_NONE sentinel from native ISA ops — skip
        }

        if (inst) {
            inform("[%lu] Replaying %s from stream\n", curTick(), inst->disassemble(0).c_str());
            rename.injectedInsts[0].push_back(inst);
            rename.hasInjectedInsts = true;
            ++count;
        }
    }

    if (_playbackStream.peek() == EOF)
        _playbackStream.close();
}

void
MicroCPU::injectSquash()
{
    // squashFromTC drives the commit stage to call squashAll() next tick,
    // draining the ROB and all pipeline stages without touching the branch
    // predictor — matching the paper's programmatic squash interface.
    squashFromTC(0);
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
    std::ifstream is(filename, std::ios::binary);
    if (!is.is_open()) {
        warn("MicroCPU: Could not open playback file %s", filename);
        return;
    }

    while (is.peek() != EOF) {
        uint8_t opcode;
        int64_t offset;
        uint8_t rd, rs1, rs2;

        is.read(reinterpret_cast<char*>(&opcode), 1);
        is.read(reinterpret_cast<char*>(&offset), 8);
        is.read(reinterpret_cast<char*>(&rd), 1);
        is.read(reinterpret_cast<char*>(&rs1), 1);
        is.read(reinterpret_cast<char*>(&rs2), 1);

        if (!is) {
            warn("MicroCPU: playbackStream truncated read in %s; "
                 "ignoring partial record", filename);
            break;
        }

        StaticInstPtr inst = nullptr;
        switch (static_cast<MuOpCode>(opcode)) {
            case MU_ADD: inst = new MuAdd(rs1, rs2, rd); break;
            case MU_SUB: inst = new MuSub(rs1, rs2, rd); break;
            case MU_MUL: inst = new MuMul(rs1, rs2, rd); break;
            case MU_DIV: inst = new MuDiv(rs1, rs2, rd); break;
            case MU_LD:  inst = new MuLd(rs1, rd, offset); break;
            case MU_ST:  inst = new MuSt(rs1, rs2, offset); break;
            default: break;
        }

        if (inst) {
            rename.injectedInsts[0].push_back(inst);
        }
    }
    rename.hasInjectedInsts = true;
    is.close();
}

void
MicroCPU::dumpInst(const DynInstPtr &inst)
{
    if (!_dumpEnabled || !_dumpStream)
        return;

    auto mu_inst = dynamic_cast<const MicroStaticInstBase*>(
        inst->staticInst.get());
    if (mu_inst) {
        // MicroISA op: write compact 12-byte binary record.
        uint8_t opcode = mu_inst->getOpCode();
        int64_t offset = mu_inst->getOffset();
        uint8_t rd  = mu_inst->getRd();
        uint8_t rs1 = mu_inst->getRs1();
        uint8_t rs2 = mu_inst->getRs2();

        _dumpStream->stream()->write(
            reinterpret_cast<const char*>(&opcode), 1);
        _dumpStream->stream()->write(
            reinterpret_cast<const char*>(&offset), 8);
        _dumpStream->stream()->write(
            reinterpret_cast<const char*>(&rd),  1);
        _dumpStream->stream()->write(
            reinterpret_cast<const char*>(&rs1), 1);
        _dumpStream->stream()->write(
            reinterpret_cast<const char*>(&rs2), 1);
    } else {
        // Native ISA micro-op: emit opcode=0 sentinel + mnemonic so the
        // trace is not silently incomplete.  playbackStream skips these.
        static constexpr uint8_t NATIVE_SENTINEL = 0;
        static constexpr int64_t zero_offset = 0;
        static constexpr uint8_t zero_reg = 0;
        _dumpStream->stream()->write(
            reinterpret_cast<const char*>(&NATIVE_SENTINEL), 1);
        _dumpStream->stream()->write(
            reinterpret_cast<const char*>(&zero_offset), 8);
        _dumpStream->stream()->write(
            reinterpret_cast<const char*>(&zero_reg), 1);
        _dumpStream->stream()->write(
            reinterpret_cast<const char*>(&zero_reg), 1);
        _dumpStream->stream()->write(
            reinterpret_cast<const char*>(&zero_reg), 1);
        DPRINTF(Rename, "MicroDump: native ISA op '%s' recorded as sentinel\n",
            inst->staticInst->getName());
    }
}

} // namespace o3
} // namespace gem5
