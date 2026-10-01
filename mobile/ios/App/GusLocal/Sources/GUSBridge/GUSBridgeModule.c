#include "GUSLlamaBridge.h"

// Exposes the pinned bridge header as a SwiftPM Clang module. The app target
// compiles the upstream bridge implementation with llama.cpp's headers.
int gus_bridge_module_available(void) { return 1; }
