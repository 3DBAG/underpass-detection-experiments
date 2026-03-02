#include "BooleanOpsManifold.h"

#include <chrono>

#include "MeshConversion.h"

using Clock = std::chrono::steady_clock;

bool manifold_boolean_difference(
    Surface_mesh& house_sm,
    std::vector<Surface_mesh>& underpass_sms,
    manifold::MeshGL& result_meshgl,
    BooleanOpTiming* timing,
    ManifoldBooleanError* error) {
    if (error != nullptr) {
        *error = ManifoldBooleanError::None;
    }

    auto t_conversion_start = Clock::now();
    auto house_meshgl = surface_mesh_to_meshgl(house_sm, false);
    if (house_meshgl.NumTri() == 0) {
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
    if (house.Status() != manifold::Manifold::Error::NoError) {
        if (error != nullptr) {
            *error = ManifoldBooleanError::InvalidInput;
        }
        return false;
    }

    std::vector<manifold::Manifold> underpasses;
    underpasses.reserve(underpass_sms.size());
    for (auto& underpass_sm : underpass_sms) {
        auto underpass_meshgl = surface_mesh_to_meshgl(underpass_sm, false);
        if (underpass_meshgl.NumTri() == 0) {
            continue;
        }
        manifold::Manifold underpass(underpass_meshgl);
        if (underpass.Status() != manifold::Manifold::Error::NoError) {
            if (error != nullptr) {
                *error = ManifoldBooleanError::InvalidInput;
            }
            return false;
        }
        underpasses.push_back(std::move(underpass));
    }
    auto t_conversion_end = Clock::now();
    if (timing != nullptr) {
        timing->conversion_ms += t_conversion_end - t_conversion_start;
    }

    if (underpasses.empty()) {
        if (error != nullptr) {
            *error = ManifoldBooleanError::EmptyInputMesh;
        }
        return false;
    }

    auto t_boolean_start = Clock::now();
    manifold::Manifold merged_underpass = std::move(underpasses.front());
    for (size_t i = 1; i < underpasses.size(); ++i) {
        merged_underpass = merged_underpass + underpasses[i];
        if (merged_underpass.Status() != manifold::Manifold::Error::NoError) {
            if (timing != nullptr) {
                timing->boolean_ms += Clock::now() - t_boolean_start;
            }
            if (error != nullptr) {
                *error = ManifoldBooleanError::BooleanFailed;
            }
            return false;
        }
    }
    auto result = house - merged_underpass;
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
