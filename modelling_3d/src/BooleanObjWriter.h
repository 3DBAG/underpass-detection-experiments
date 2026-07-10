#ifndef BOOLEAN_OBJ_WRITER_H
#define BOOLEAN_OBJ_WRITER_H

#include <cstddef>
#include <fstream>
#include <string>
#include <string_view>

#include <manifold/manifold.h>

#include "BooleanOps.h"

class BooleanObjWriter {
public:
    bool open(const std::string& path);
    bool append(std::string_view feature_id, const manifold::MeshGL& mesh);
    bool append(std::string_view feature_id, const Surface_mesh& mesh);

private:
    std::ofstream out_;
    size_t next_vertex_index_ = 1;
};

#endif // BOOLEAN_OBJ_WRITER_H
