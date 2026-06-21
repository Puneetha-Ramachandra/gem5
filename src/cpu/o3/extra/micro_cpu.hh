/*
 * Copyright (2026) Google, Inc.
 * All rights reserved.
 */

#ifndef __CPU_O3_MICRO_CPU_HH__
#define __CPU_O3_MICRO_CPU_HH__

#include <fstream>
#include <string>
#include <vector>

#include "base/types.hh"
#include "cpu/o3/cpu.hh"
#include "cpu/o3/dyn_inst_ptr.hh"
#include "cpu/static_inst.hh"
#include "params/MicroCPU.hh"

namespace gem5
{

class OutputStream;

namespace o3
{

class MicroCPU : public CPU
{
  public:
    MicroCPU(const MicroCPUParams &params);

    /**
     * Injected a sequence of StaticInsts into the Rename stage.
     */
    void injectSequence(const std::vector<StaticInstPtr> &insts);

    /** Trace recording and replay */
    void enableDump(const std::string &path);
    void disableDump();
    void dumpInst(const DynInstPtr &inst);
    void playbackStream(const std::string &path);

    /** Injection methods accessible from Python */
    void injectAdd(RegIndex rs1, RegIndex rs2, RegIndex rd);
    void injectSub(RegIndex rs1, RegIndex rs2, RegIndex rd);
    void injectMul(RegIndex rs1, RegIndex rs2, RegIndex rd);
    void injectDiv(RegIndex rs1, RegIndex rs2, RegIndex rd);
    void injectLd(RegIndex rs1, RegIndex rd, int64_t offset);
    void injectSt(RegIndex rs1, RegIndex rs2, int64_t offset);

    /**
     * Squash all in-flight instructions for thread 0 via the commit stage,
     * independent of the branch predictor.  Models the speculative window
     * teardown described in the paper's security fuzzing use-case.
     */
    void injectSquash();

    /**
     * Open a MicroISA binary trace for streaming playback.  Unlike the
     * legacy playbackStream() bulk-load, this keeps the file open and
     * feeds one instruction per Rename slot each tick, preserving O3
     * timing fidelity as described in the paper.
     */
    void startStreamingPlayback(const std::string &path);
    void stopStreamingPlayback();

    /** Feed up to maxInsts injected ops from the open stream this tick. */
    void drainStreamIntoRename(unsigned maxInsts);

    bool isStreamingPlayback() const { return _playbackStream.is_open(); }

  private:
    OutputStream* _dumpStream = nullptr;
    bool _dumpEnabled = false;

    std::ifstream _playbackStream;
};

} // namespace o3
} // namespace gem5

#endif // __CPU_O3_MICRO_CPU_HH__
