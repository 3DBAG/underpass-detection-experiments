#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <time.h>
#include "ptinpoly.h"

#define N 1000000

static double xs[N], ys[N];

/* Simple xoshiro128+ PRNG matching Zig's DefaultPrng(0xdeadbeef) output isn't
   practical, so we just use our own deterministic sequence.  The exact inside
   counts will differ from the Zig benchmark, but timings are comparable. */
static unsigned long long rng_state = 0xdeadbeef;
static double rng_f64(void) {
    rng_state ^= rng_state << 13;
    rng_state ^= rng_state >> 7;
    rng_state ^= rng_state << 17;
    return (double)(rng_state & 0xFFFFFFFFFFFFULL) / (double)0xFFFFFFFFFFFFULL;
}

static void gen_star(double (*out)[2], int n_tips, double outer_r, double inner_r) {
    int total = n_tips * 2;
    for (int i = 0; i < total; i++) {
        double angle = M_PI * 2.0 * i / total - M_PI / 2.0;
        double r = (i % 2 == 0) ? outer_r : inner_r;
        out[i][0] = r * cos(angle);
        out[i][1] = r * sin(angle);
    }
}

typedef struct {
    const char *name;
    double (*pgon)[2];
    int nverts;
} BenchCase;

static void bench_naive(BenchCase *c) {
    struct timespec t0, t1;
    unsigned long hits = 0;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    for (int i = 0; i < N; i++) {
        double pt[2] = { xs[i], ys[i] };
        if (CrossingsMultiplyTest(c->pgon, c->nverts, pt)) hits++;
    }
    clock_gettime(CLOCK_MONOTONIC, &t1);
    double ns = ((t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec)) / N;
    printf("%-24s %-18s %14.1f  %10s  %lu\n", c->name, "C naive", ns, "-", hits);
}

static void bench_grid(BenchCase *c, int res) {
    GridSet gs;
    struct timespec t0, t1;

    clock_gettime(CLOCK_MONOTONIC, &t0);
    GridSetup(c->pgon, c->nverts, res, &gs);
    clock_gettime(CLOCK_MONOTONIC, &t1);
    double prep_us = ((t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec)) / 1000.0;

    /* warm-up */
    volatile unsigned long warmup = 0;
    for (int i = 0; i < N / 10; i++) {
        double pt[2] = { xs[i], ys[i] };
        if (GridTest(&gs, pt)) warmup++;
    }

    unsigned long hits = 0;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    for (int i = 0; i < N; i++) {
        double pt[2] = { xs[i], ys[i] };
        if (GridTest(&gs, pt)) hits++;
    }
    clock_gettime(CLOCK_MONOTONIC, &t1);
    double ns = ((t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec)) / N;

    char label[32];
    snprintf(label, sizeof(label), "C grid res=%d", res);
    printf("%-24s %-18s %14.1f  %10.1f  %lu\n", "", label, ns, prep_us, hits);

    GridCleanup(&gs);
}

int main(void) {
    /* Generate test points in [-1.2, 1.2]^2 */
    for (int i = 0; i < N; i++) {
        xs[i] = rng_f64() * 2.4 - 1.2;
        ys[i] = rng_f64() * 2.4 - 1.2;
    }

    double square[4][2] = {
        {-1.0, -1.0}, {1.0, -1.0}, {1.0, 1.0}, {-1.0, 1.0}
    };

    double star10[20][2];   gen_star(star10, 10, 1.0, 0.45);
    double star100[200][2]; gen_star(star100, 100, 1.0, 0.45);
    double star500[1000][2]; gen_star(star500, 500, 1.0, 0.45);

    BenchCase cases[] = {
        { "square (4 edges)",   square,  4 },
        { "star (20 edges)",    star10,  20 },
        { "star (200 edges)",   star100, 200 },
        { "star (1000 edges)",  star500, 1000 },
    };
    int n_cases = sizeof(cases) / sizeof(cases[0]);

    printf("Benchmarking %d queries per case (original C code)\n", N);
    printf("%-24s %-18s %14s  %10s  %s\n",
        "polygon", "strategy", "ns/query", "prep (us)", "inside");
    for (int i = 0; i < 86; i++) putchar('-');
    putchar('\n');

    int resolutions[] = { 4, 8, 16, 32, 64, 128 };
    int n_res = sizeof(resolutions) / sizeof(resolutions[0]);

    for (int c = 0; c < n_cases; c++) {
        bench_naive(&cases[c]);
        for (int r = 0; r < n_res; r++) {
            bench_grid(&cases[c], resolutions[r]);
        }
        printf("\n");
    }

    return 0;
}
