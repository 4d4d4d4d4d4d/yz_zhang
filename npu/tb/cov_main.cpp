// Verilator's generated main does not write coverage, so this one does.
// Same run loop, plus a coverage dump at $finish. Build with --prefix Vtop
// so one file serves every testbench.
//
//   ./sim +covfile=<path>   writes the merged-in coverage data there
#include <memory>
#include <cstring>
#include "verilated.h"
#include "verilated_cov.h"
#include "Vtop.h"

int main(int argc, char** argv, char**) {
    Verilated::debug(0);
    const std::unique_ptr<VerilatedContext> ctx{new VerilatedContext};
    ctx->commandArgs(argc, argv);

    const char* cov = "coverage.dat";
    for (int i = 1; i < argc; i++)
        if (!strncmp(argv[i], "+covfile=", 9)) cov = argv[i] + 9;

    const std::unique_ptr<Vtop> top{new Vtop{ctx.get()}};
    while (!ctx->gotFinish()) {
        top->eval();
        if (!top->eventsPending()) break;
        ctx->time(top->nextTimeSlot());
    }
    top->final();
#if VM_COVERAGE
    ctx->coveragep()->write(cov);
#endif
    return 0;
}
