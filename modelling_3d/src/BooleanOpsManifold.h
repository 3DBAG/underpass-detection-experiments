#ifndef BOOLEAN_OPS_MANIFOLD_H
#define BOOLEAN_OPS_MANIFOLD_H

#include <manifold/manifold.h>

#include "BooleanOps.h"

enum class ManifoldBooleanError {
    None,
    EmptyInputMesh,
    InvalidInput,
    BooleanFailed
};

bool manifold_boolean_difference(
    Surface_mesh& house_sm,
    std::vector<Surface_mesh>& underpass_sms,
    manifold::MeshGL& result_meshgl,
    BooleanOpTiming* timing = nullptr,
    ManifoldBooleanError* error = nullptr);

#endif // BOOLEAN_OPS_MANIFOLD_H
