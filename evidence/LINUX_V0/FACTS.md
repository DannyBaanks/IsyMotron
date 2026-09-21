# Linux native awareness — V0

Status: `DEMONSTRATED`, scoped.

The native Linux provider reads `CLOCK_BOOTTIME - CLOCK_MONOTONIC` for
retrospective suspend bias and local `/sys/class/net/*/operstate` files for
aggregate interface state. The implementation does not require root or make a
network request.

Controls: the full repository suite passed on the native Ubuntu host; four
provider tests cover clock availability, monotonic bias, mechanism description,
and deterministic interface aggregation.

Not demonstrated: pre-suspend notifications, hibernation, VM pause semantics,
and a Linux desktop avatar when Tk is unavailable. The product host scope
remains Windows 10/11.
