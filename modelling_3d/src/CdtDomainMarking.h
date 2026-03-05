#ifndef CDT_DOMAIN_MARKING_H
#define CDT_DOMAIN_MARKING_H

#include <list>

namespace cdt_domain_marking {

template <typename CDT>
void mark_domains_from_face(
    CDT& ct,
    typename CDT::Face_handle start,
    int index,
    std::list<typename CDT::Edge>& border) {
    if (start->info().nesting_level != -1) {
        return;
    }
    std::list<typename CDT::Face_handle> queue;
    queue.push_back(start);
    while (!queue.empty()) {
        auto fh = queue.front();
        queue.pop_front();
        if (fh->info().nesting_level == -1) {
            fh->info().nesting_level = index;
            for (int i = 0; i < 3; ++i) {
                typename CDT::Edge e(fh, i);
                auto n = fh->neighbor(i);
                if (n->info().nesting_level == -1) {
                    if (ct.is_constrained(e)) {
                        border.push_back(e);
                    } else {
                        queue.push_back(n);
                    }
                }
            }
        }
    }
}

template <typename CDT>
void mark_domains(CDT& cdt) {
    std::list<typename CDT::Edge> border;
    mark_domains_from_face(cdt, cdt.infinite_face(), 0, border);
    while (!border.empty()) {
        typename CDT::Edge e = border.front();
        border.pop_front();
        auto n = e.first->neighbor(e.second);
        if (n->info().nesting_level == -1) {
            mark_domains_from_face(cdt, n, e.first->info().nesting_level + 1, border);
        }
    }
}

} // namespace cdt_domain_marking

#endif // CDT_DOMAIN_MARKING_H
