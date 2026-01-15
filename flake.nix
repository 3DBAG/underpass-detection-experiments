{
  description = "A C++ project for 3D intersection testing";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        # Development dependencies matching vcpkg.json
        buildTools = with pkgs; [
          cmake
          pkg-config
        ];
        cppDeps = with pkgs; [
          # manifold - geometry processing library
          manifold
          clipper2

          # CGAL - Computational Geometry Algorithms Library
          cgal

          # geogram - geometry processing library
          geogram

          # nlohmann_json - JSON library
          nlohmann_json

          # GDAL with features
          gdal
          sqlite
          postgresql
          geos

          # eigen3 - linear algebra library
          eigen
        ];

      in
      {
        # Development shell
        devShells.default = pkgs.mkShell {
          buildInputs = cppDeps ++ buildTools;

          # Environment variables
          GDAL_DATA = "${pkgs.gdal}/share/gdal";
          PROJ_LIB = "${pkgs.proj}/share/proj";
          # CMAKE_MODULE_PATH="${pkgs.geogram.dev}/lib/cmake";
          CMAKE_PREFIX_PATH="${pkgs.manifold}/lib/cmake;${pkgs.clipper2}/lib/cmake";

          shellHook = ''
            echo "Entering development environment for test-3d-intersection"
            echo ""
            echo "Use these cmake flags for configuration:"
            echo "  cmake -DCMAKE_BUILD_TYPE=Release \\"
            echo "        -DCMAKE_MODULE_PATH=${pkgs.geogram.dev}/lib/cmake \\"
            echo "        -B build -S ."
            echo ""
            echo "And then to build the project:"
            echo "  cmake --build build"
          '';
        };

        # Package definition
        packages.default = pkgs.stdenv.mkDerivation {
          pname = "test-3d-intersection";
          version = "0.1.0";

          src = ./.;

          nativeBuildInputs = buildTools;

          buildInputs = cppDeps;

          # CMake configuration
          cmakeFlags = [
            "-DCMAKE_BUILD_TYPE=Release"
            "-DCMAKE_MODULE_PATH=${pkgs.geogram.dev}/lib/cmake"
            "-DCMAKE_PREFIX_PATH=${pkgs.manifold}/lib/cmake;${pkgs.clipper2}/lib/cmake"
          ];

          meta = with pkgs.lib; {
            description = "A C++ project for 3D intersection testing";
            license = licenses.mit;
            platforms = platforms.linux ++ platforms.darwin;
          };
        };
      });
}
