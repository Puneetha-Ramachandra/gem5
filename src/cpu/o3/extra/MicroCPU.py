from m5.params import *
from m5.proxy import *
from m5.objects.RiscvCPU import RiscvO3CPU
from m5.objects.RiscvMMU import RiscvMMU
from m5.SimObject import cxxMethod

class MicroCPU(RiscvO3CPU):
    type = 'MicroCPU'
    cxx_class = 'gem5::o3::MicroCPU'
    cxx_header = "cpu/o3/extra/micro_cpu.hh"

    # Minimal overrides for O3 subcomponents
    numThreads = 1

    @cxxMethod
    def enableDump(self, filename):
        pass

    @cxxMethod
    def disableDump(self):
        pass

    @cxxMethod
    def playbackStream(self, filename):
        pass

    # Injection methods
    @cxxMethod
    def injectAdd(self, rs1, rs2, rd):
        pass

    @cxxMethod
    def injectSub(self, rs1, rs2, rd):
        pass

    @cxxMethod
    def injectMul(self, rs1, rs2, rd):
        pass

    @cxxMethod
    def injectDiv(self, rs1, rs2, rd):
        pass

    @cxxMethod
    def injectLd(self, rs1, rd, offset):
        pass

    @cxxMethod
    def injectSt(self, rs1, rs2, offset):
        pass
