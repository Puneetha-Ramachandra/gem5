/*
 * Copyright (2026) Google, Inc.
 * All rights reserved.
 */

#ifndef __CPU_O3_MICRO_CPU_HH__
#define __CPU_O3_MICRO_CPU_HH__

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

  private:
    OutputStream* _dumpStream = nullptr;
    bool _dumpEnabled = false;
};

} // namespace o3
} // namespace gem5

#endif // __CPU_O3_MICRO_CPU_HH__
