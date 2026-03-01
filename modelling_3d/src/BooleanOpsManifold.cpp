#include "BooleanOpsManifold.h"

#include <chrono>

#include "MeshConversion.h"

using Clock = std::chrono::steady_clock;

bool manifold_boolean_difference(
    Surface_mesh& house_sm,
    Surface_mesh& underpass_sm,
    manifold::MeshGL& result_meshgl,
    BooleanOpTiming* timing,
    ManifoldBooleanError* error) {
    if (error != nullptr) {
        *error = ManifoldBooleanError::None;
    }

    auto t_conversion_start = Clock::now();
    auto house_meshgl = surface_mesh_to_meshgl(house_sm, false);
    auto underpass_meshgl = surface_mesh_to_meshgl(underpass_sm, false);
    if (house_meshgl.NumTri() == 0 || underpass_meshgl.NumTri() == 0) {
        auto t_conversion_end = Clock::now();
        if (timing != nullptr) {
            timing->conversion_ms += t_conversion_end - t_conversion_start;
        }
        if (error != nullptr) {
            *error = ManifoldBooleanError::EmptyInputMesh;
        }
        return false;
    }

    manifold::Manifold house(house_meshgl);
    manifold::Manifold underpass(underpass_meshgl);
    auto t_conversion_end = Clock::now();
    if (timing != nullptr) {
        timing->conversion_ms += t_conversion_end - t_conversion_start;
    }
    if (house.Status() != manifold::Manifold::Error::NoError ||
        underpass.Status() != manifold::Manifold::Error::NoError) {
        if (error != nullptr) {
            *error = ManifoldBooleanError::InvalidInput;
        }
        return false;
    }

    auto t_boolean_start = Clock::now();
    auto result = house - underpass;
    auto t_boolean_end = Clock::now();
    if (timing != nullptr) {
        timing->boolean_ms += t_boolean_end - t_boolean_start;
    }
    if (result.Status() != manifold::Manifold::Error::NoError) {
        if (error != nullptr) {
            *error = ManifoldBooleanError::BooleanFailed;
        }
        return false;
    }

    t_conversion_start = Clock::now();
    result_meshgl = result.GetMeshGL();
    t_conversion_end = Clock::now();
    if (timing != nullptr) {
        timing->conversion_ms += t_conversion_end - t_conversion_start;
    }
    return true;
}
