#include "BooleanObjWriter.h"

#include <cstdint>
#include <iomanip>
#include <unordered_map>

namespace {

std::string obj_safe_feature_id(std::string_view feature_id) {
    std::string result;
    result.reserve(feature_id.size());
    for (const unsigned char c : feature_id) {
        const bool safe = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                          (c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.';
        result.push_back(safe ? static_cast<char>(c) : '_');
    }
    return result.empty() ? "feature" : result;
}

} // namespace

bool BooleanObjWriter::open(const std::string& path) {
    out_.open(path);
    if (!out_) {
        return false;
    }
    out_ << "# Boolean results from add_underpass\n" << std::setprecision(17);
    return true;
}

bool BooleanObjWriter::append(std::string_view feature_id, const manifold::MeshGL& mesh) {
    if (!out_.is_open()) {
        return true;
    }
    if (mesh.numProp < 3 || mesh.triVerts.size() % 3 != 0) {
        return false;
    }

    out_ << "\no " << obj_safe_feature_id(feature_id) << "\n";
    for (size_t vertex = 0; vertex < mesh.NumVert(); ++vertex) {
        out_ << "v "
             << mesh.vertProperties[vertex * mesh.numProp + 0] << ' '
             << mesh.vertProperties[vertex * mesh.numProp + 1] << ' '
             << mesh.vertProperties[vertex * mesh.numProp + 2] << '\n';
    }
    for (size_t triangle = 0; triangle < mesh.NumTri(); ++triangle) {
        out_ << "f";
        for (size_t corner = 0; corner < 3; ++corner) {
            const uint32_t vertex = mesh.triVerts[triangle * 3 + corner];
            if (vertex >= mesh.NumVert()) {
                return false;
            }
            out_ << ' ' << next_vertex_index_ + vertex;
        }
        out_ << '\n';
    }
    next_vertex_index_ += mesh.NumVert();
    return out_.good();
}

bool BooleanObjWriter::append(std::string_view feature_id, const Surface_mesh& mesh) {
    if (!out_.is_open()) {
        return true;
    }

    out_ << "\no " << obj_safe_feature_id(feature_id) << "\n";
    std::unordered_map<size_t, size_t> obj_indices;
    obj_indices.reserve(mesh.number_of_vertices());
    for (auto vertex : mesh.vertices()) {
        const auto& point = mesh.point(vertex);
        obj_indices.emplace(static_cast<size_t>(vertex), next_vertex_index_ + obj_indices.size());
        out_ << "v " << point.x() << ' ' << point.y() << ' ' << point.z() << '\n';
    }
    for (auto face : mesh.faces()) {
        out_ << "f";
        for (auto vertex : mesh.vertices_around_face(mesh.halfedge(face))) {
            out_ << ' ' << obj_indices.at(static_cast<size_t>(vertex));
        }
        out_ << '\n';
    }
    next_vertex_index_ += mesh.number_of_vertices();
    return out_.good();
}
